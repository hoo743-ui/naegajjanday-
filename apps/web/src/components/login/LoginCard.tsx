"use client";

import { useEffect, useState, type MouseEvent, type ReactNode } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Jjani } from "@/components/mascot/Jjani";
import { track } from "@/lib/analytics";
import { IS_MOCKING } from "@/lib/api/client";
import { useAuthProviders } from "@/lib/api/hooks";
import type { OAuthProvider } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { oauthLoginUrl, refreshAccessToken } from "@/lib/auth/token";
import { cn } from "@/lib/utils";

/** 오픈 리다이렉트 방지: 사이트 내부 경로만 허용 */
function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") && !raw.includes("\\") ? raw : "/my";
}

const PROVIDERS: { id: OAuthProvider; label: string; className: string; glyph: ReactNode }[] = [
  {
    id: "kakao",
    label: "카카오로 계속하기",
    className: "bg-[#FEE500] text-[#191600] hover:brightness-95",
    glyph: (
      <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
        <path fill="currentColor" d="M12 3.5C6.75 3.5 2.5 6.86 2.5 11c0 2.66 1.76 5 4.41 6.33-.19.7-.7 2.6-.8 3-.13.5.18.5.38.36.16-.1 2.5-1.7 3.5-2.4.65.1 1.32.15 2.01.15 5.25 0 9.5-3.36 9.5-7.5S17.25 3.5 12 3.5Z" />
      </svg>
    ),
  },
  {
    id: "naver",
    label: "네이버로 계속하기",
    className: "bg-[#03C75A] text-[#00240F] hover:brightness-95",
    glyph: (
      <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden>
        <path fill="currentColor" d="M15.2 12.6 8.5 3H3v18h5.8v-9.6l6.7 9.6H21V3h-5.8z" />
      </svg>
    ),
  },
  {
    id: "google",
    label: "Google로 계속하기",
    className: "border border-input bg-white text-ink hover:bg-soft",
    glyph: (
      <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
        <path fill="#4285F4" d="M21.6 12.23c0-.68-.06-1.34-.17-1.97H12v3.73h5.39a4.6 4.6 0 0 1-2 3.02v2.5h3.23c1.9-1.74 2.98-4.3 2.98-7.28Z" />
        <path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.43l-3.23-2.5c-.9.6-2.04.95-3.39.95-2.6 0-4.81-1.76-5.6-4.12H3.06v2.58A10 10 0 0 0 12 22Z" />
        <path fill="#FBBC05" d="M6.4 13.9a6 6 0 0 1 0-3.8V7.52H3.06a10 10 0 0 0 0 8.96L6.4 13.9Z" />
        <path fill="#EA4335" d="M12 5.98c1.47 0 2.79.5 3.83 1.5l2.86-2.87A10 10 0 0 0 3.06 7.52L6.4 10.1C7.19 7.74 9.4 5.98 12 5.98Z" />
      </svg>
    ),
  },
];

/** API 가 OAuth 실패 시 `/login?error=<code>` 로 돌려보낸다 (apps/api/app/api/v1/auth.py 의 코드와 짝) */
const LOGIN_ERRORS: Record<string, string> = {
  oauth_not_configured: "이 로그인은 아직 준비 중이에요. 다른 방법으로 들어와 주세요.",
  oauth_cancelled: "로그인을 중간에 멈췄어요. 준비되면 다시 눌러 주세요.",
  oauth_failed: "로그인하다 길을 잃었어요. 한 번만 다시 시도해 주세요.",
  account_suspended: "이용이 정지된 계정이에요. 다른 계정으로 들어와 주세요.",
};
const LOGIN_ERROR_FALLBACK = "로그인을 마치지 못했어요. 다시 시도해 주세요.";

export function LoginCard() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const errorCode = params.get("error");
  const errorMessage = errorCode ? (LOGIN_ERRORS[errorCode] ?? LOGIN_ERROR_FALLBACK) : null;
  const { status } = useAuth();
  const [pending, setPending] = useState<OAuthProvider | null>(null);
  // 목 모드에는 OAuth 서버가 없다 → 묻지 않고 전부 열어 둔다. 조회에 실패해도 열어 둔다(눌러도 이 화면으로 되돌아온다).
  const providers = useAuthProviders(!IS_MOCKING);
  const isEnabled = (id: OAuthProvider) => providers.data?.items?.find((p) => p.provider === id)?.enabled ?? true;

  useEffect(() => {
    if (status === "authenticated" && pending === null) router.replace(next);
  }, [status, pending, next, router]);

  const onClick = async (event: MouseEvent<HTMLAnchorElement>, provider: OAuthProvider) => {
    track("login_clicked", { provider });
    if (!IS_MOCKING) return; // 실제 환경: 링크 그대로 API 의 OAuth 시작점으로 이동
    // 목 모드: OAuth 서버가 없으므로 "로그아웃 표시"만 지우고 세션을 복원한다
    event.preventDefault();
    setPending(provider);
    try {
      sessionStorage.removeItem("njd_mock_logged_out");
    } catch {
      // 저장소 접근 불가: 그대로 진행
    }
    await refreshAccessToken();
    router.replace(next);
  };

  return (
    <div className="glass mx-auto w-full max-w-[420px] rounded-[32px] p-7 text-center sm:p-9">
      <Jjani mood="hi" size={120} floating className="mx-auto" />
      <h1 className="mt-3 text-2xl font-extrabold tracking-tight">다시 만나서 반가워요</h1>
      <p className="mt-1.5 text-[15px] text-muted-foreground">로그인하면 짠 코스를 저장하고, 다녀온 곳으로 취향을 맞춰 드려요.</p>

      {errorMessage ? (
        <p role="alert" className="mt-5 rounded-xl bg-pink-soft px-3 py-2.5 text-sm font-bold text-pink-deep">
          {errorMessage}
        </p>
      ) : null}

      <ul className={cn("grid gap-2.5", errorMessage ? "mt-4" : "mt-7")}>
        {PROVIDERS.map((p) => {
          const base = "flex h-14 w-full items-center justify-center gap-2.5 rounded-2xl text-base font-extrabold tracking-tight transition-[filter,background]";
          return (
            <li key={p.id}>
              {isEnabled(p.id) ? (
                <a
                  href={oauthLoginUrl(p.id, next)}
                  onClick={(e) => void onClick(e, p.id)}
                  aria-busy={pending === p.id}
                  className={cn(base, p.className, pending && pending !== p.id && "pointer-events-none opacity-50")}
                >
                  {p.glyph}
                  {pending === p.id ? "들어가는 중…" : p.label}
                </a>
              ) : (
                // 서버에 설정되지 않은 로그인: 숨기지 않고 "준비 중"으로 보여 준다 (눌러서 막다른 길에 닿지 않게)
                <button type="button" disabled className={cn(base, p.className, "cursor-not-allowed opacity-45 grayscale hover:brightness-100")}>
                  {p.glyph}
                  {p.label}
                  <span className="rounded-full bg-black/10 px-2 py-0.5 text-xs font-extrabold">준비 중이에요</span>
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {providers.data && PROVIDERS.every((p) => !isEnabled(p.id)) ? (
        <p role="note" className="mt-4 rounded-xl bg-paper-2 text-ink-2 px-3 py-2 text-xs font-bold">
          소셜 로그인을 준비하고 있어요. 그동안은 가입 없이 코스를 짤 수 있어요.
        </p>
      ) : null}

      {IS_MOCKING ? (
        <p role="note" className="mt-4 rounded-xl bg-paper-2 text-ink-2 px-3 py-2 text-xs font-bold">
          목(MOCK) 모드예요. 어떤 버튼을 눌러도 개발용 관리자 계정으로 들어가요.
        </p>
      ) : null}

      <p className="mt-6 text-[13px] text-muted-foreground">
        가입 없이도 코스는 짤 수 있어요.{" "}
        <Link href="/plan" className="font-extrabold text-blue-deep underline-offset-4 hover:underline">
          바로 코스 짜기
        </Link>
      </p>
      {/* 로그인 = 계정 생성이다 → 무엇에 동의하는지 누르기 전에 보여 준다 */}
      <p className="mt-3 text-[12px] leading-relaxed text-muted-foreground">
        로그인하면{" "}
        <Link href="/terms" className="font-bold underline underline-offset-2 hover:text-ink">
          이용약관
        </Link>
        과{" "}
        <Link href="/privacy" className="font-bold underline underline-offset-2 hover:text-ink">
          개인정보처리방침
        </Link>
        에 동의한 것으로 봐요.
      </p>
    </div>
  );
}
