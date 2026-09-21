import { getAccessToken, refreshAccessToken } from "@/lib/auth/token";
import { mockReady } from "./mock-ready";
import type { ErrorCode, ProblemDetails } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/v1").replace(/\/$/, "");
export const IS_MOCKING = process.env.NEXT_PUBLIC_API_MOCKING === "enabled";

const DEFAULT_TIMEOUT_MS = 15_000;

/** 모든 API 실패는 이 타입 하나로 수렴한다. `code` 가 짠이 표정·문구를 고르는 키다. */
export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  readonly detail?: string;
  readonly meta: Record<string, unknown>;
  readonly traceId?: string;
  readonly retryAfter?: number;

  constructor(init: {
    code: ErrorCode;
    status: number;
    title: string;
    detail?: string;
    meta?: Record<string, unknown>;
    traceId?: string;
    retryAfter?: number;
  }) {
    super(init.title);
    this.name = "ApiError";
    this.code = init.code;
    this.status = init.status;
    this.detail = init.detail;
    this.meta = init.meta ?? {};
    this.traceId = init.traceId;
    this.retryAfter = init.retryAfter;
  }

  /** 네트워크 단절·타임아웃·5xx 처럼 "다시 시도"가 의미 있는 실패인지 */
  get retryable(): boolean {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }

  static from(error: unknown): ApiError {
    if (error instanceof ApiError) return error;
    if (error instanceof DOMException && error.name === "AbortError") {
      return new ApiError({ code: "TIMEOUT", status: 0, title: "응답이 너무 늦어요" });
    }
    if (error instanceof TypeError) {
      // fetch 는 DNS/연결 실패를 TypeError 로 던진다
      return new ApiError({ code: "NETWORK_ERROR", status: 0, title: "서버에 연결하지 못했어요" });
    }
    return new ApiError({
      code: "UNKNOWN",
      status: 0,
      title: error instanceof Error ? error.message : "알 수 없는 오류",
    });
  }
}

const STATUS_FALLBACK_CODE: Record<number, ErrorCode> = {
  400: "VALIDATION_ERROR",
  401: "UNAUTHORIZED",
  403: "FORBIDDEN",
  404: "NOT_FOUND",
  422: "VALIDATION_ERROR",
  429: "RATE_LIMITED",
};

export async function parseErrorResponse(res: Response): Promise<ApiError> {
  let problem: Partial<ProblemDetails> = {};
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("json")) {
    try {
      problem = (await res.json()) as Partial<ProblemDetails>;
    } catch {
      // 본문이 깨져 있어도 상태 코드만으로 에러를 만든다
    }
  }
  const retryAfter = Number(res.headers.get("retry-after"));
  return new ApiError({
    code: problem.code ?? STATUS_FALLBACK_CODE[res.status] ?? (res.status >= 500 ? "INTERNAL_ERROR" : "UNKNOWN"),
    status: res.status,
    title: problem.title ?? `요청에 실패했어요 (${res.status})`,
    detail: problem.detail,
    meta: problem.meta,
    traceId: problem.trace_id,
    retryAfter: Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined,
  });
}

type QueryValue = string | number | boolean | null | undefined | readonly (string | number)[];

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, QueryValue>;
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  /** POST 생성 계열의 멱등 키 (Redis 24h) */
  idempotencyKey?: string;
  timeoutMs?: number;
  /** 서버 컴포넌트에서 Next fetch 캐시 옵션을 넘길 때 */
  next?: { revalidate?: number | false; tags?: string[] };
  /** 401 시 refresh 후 1회 재시도 (기본 true) */
  retryOnUnauthorized?: boolean;
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(`${API_URL}${path.startsWith("/") ? path : `/${path}`}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, Array.isArray(value) ? value.join(",") : String(value));
    }
  }
  return url.toString();
}

export function authHeaders(): Record<string, string> {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function rawRequest(path: string, options: RequestOptions): Promise<Response> {
  const { method = "GET", query, body, signal, headers, idempotencyKey, timeoutMs = DEFAULT_TIMEOUT_MS, next } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);

  await mockReady();
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  try {
    return await fetch(buildUrl(path, query), {
      method,
      credentials: "include", // refresh 쿠키(rt)
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
        ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
        ...authHeaders(),
        ...headers,
      },
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      ...(next ? { next } : {}),
    });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let res: Response;
  try {
    res = await rawRequest(path, options);
    if (res.status === 401 && options.retryOnUnauthorized !== false && typeof window !== "undefined") {
      const token = await refreshAccessToken();
      if (token) res = await rawRequest(path, options);
    }
  } catch (error) {
    if (options.signal?.aborted) throw error; // 호출자가 취소한 경우는 그대로 전파 (React Query 가 무시)
    throw ApiError.from(error);
  }
  if (!res.ok) throw await parseErrorResponse(res);
  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("json")) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) => request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T = void>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "DELETE" }),
};

export function newIdempotencyKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
