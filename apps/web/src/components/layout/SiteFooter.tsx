"use client";

import Link from "next/link";
import { useFeatures } from "@/lib/api/hooks";
import { useAuth } from "@/lib/auth/AuthProvider";
import { Jjani } from "@/components/mascot/Jjani";

const COLUMNS = [
  {
    title: "서비스",
    links: [
      { href: "/plan", label: "코스 짜기" },
      { href: "/explore", label: "둘러보기" },
      { href: "/chat", label: "짠이와 대화" },
    ],
  },
  {
    title: "내 계정",
    links: [
      { href: "/my", label: "내 코스" },
      { href: "/login", label: "로그인" },
    ],
  },
];

export function SiteFooter() {
  const chatOff = useFeatures().data?.chat === false; // 헤더와 같은 규칙
  const signedIn = useAuth().status === "authenticated"; // 로그인한 사람에게 "로그인"을 권하지 않는다
  return (
    <footer className="mt-16 border-t bg-soft/60 text-sm text-muted-foreground">
      <div className="wrap grid gap-10 py-12 md:grid-cols-[1.6fr_1fr_1fr]">
        <div>
          <Link
            href="/"
            className="inline-flex items-center gap-2 font-round text-xl leading-none text-ink"
            aria-label="내가짠데이 홈"
          >
            <Jjani mood="hi" size={28} animated={false} decorative />
            내가짠데이
          </Link>
          <p className="mt-3 max-w-xs leading-relaxed">
            정해진 예산으로 짜는, 알찬 하루.
            <br />
            지역 · 인원 · 예산만 알려 주면 코스는 짠이가 짤게요.
          </p>
        </div>
        {COLUMNS.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <h2 className="text-[13px] font-semibold tracking-normal text-ink">
              {col.title}
            </h2>
            <ul className="mt-3 grid gap-2.5">
              {col.links
                .filter((link) => !(chatOff && link.href === "/chat") && !(signedIn && link.href === "/login"))
                .map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className="hover:text-ink">
                      {link.label}
                    </Link>
                  </li>
                ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="border-t">
        <div className="wrap flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-5 text-[13px]">
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span>© 2026 내가짠데이</span>
            <Link href="/terms" className="hover:text-ink">
              이용약관
            </Link>
            <Link href="/privacy" className="font-bold text-ink-2 hover:text-ink">
              개인정보처리방침
            </Link>
          </p>
          <p>예상 금액과 이동 시간은 실제와 다를 수 있어요.</p>
        </div>
      </div>
    </footer>
  );
}
