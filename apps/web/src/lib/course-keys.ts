/**
 * 계정 없이 만든 코스의 편집 키 (docs/28, 배포 전 점검 P0).
 * 예전에는 주인 없는 코스를 링크만 있으면 누구나 바꿀 수 있었다 — 공유받은 친구가 장소를 바꾸면 만든 사람의 코스가 바뀌었다.
 * 이제 코스를 만든 이 브라우저만 키를 가지고, 그 코스로 가는 요청에 X-Course-Key 로 싣는다(lib/api/client.ts).
 * 저장소를 못 쓰는 환경(사생활 보호 창 등)에서는 이번 방문 동안만 기억한다.
 */
const STORAGE_KEY = "njd_course_keys";
const MAX_KEYS = 200;
let memory: Record<string, string> = {};

function load(): Record<string, string> {
  try {
    return { ...memory, ...(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Record<string, string>) };
  } catch {
    return memory;
  }
}

export function courseKeyFor(courseId: string): string | undefined {
  if (typeof window === "undefined") return undefined;
  return load()[courseId];
}

export function rememberCourseKey(courseIds: string[], key: string | null | undefined): void {
  if (typeof window === "undefined" || !key || courseIds.length === 0) return;
  const all = load();
  for (const id of courseIds) all[id] = key;
  // 오래된 것부터 버린다 (객체는 넣은 순서를 지킨다)
  const kept = Object.fromEntries(Object.entries(all).slice(-MAX_KEYS));
  memory = kept;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(kept));
  } catch {
    // 저장소를 못 쓰면 메모리에만
  }
}

/** 이 요청이 어느 코스를 고치는가: /courses/{id}… 또는 여행 하루를 다시 짜는 generate(replaces) */
export function courseKeyForRequest(path: string, body: unknown): string | undefined {
  const found = /^\/courses\/([0-9a-f-]{36})(?:\/|$)/.exec(path);
  if (found) return courseKeyFor(found[1]!);
  if (path === "/courses/generate" && body && typeof body === "object" && "replaces" in body) {
    const replaces = (body as { replaces?: unknown }).replaces;
    return typeof replaces === "string" ? courseKeyFor(replaces) : undefined;
  }
  return undefined;
}
