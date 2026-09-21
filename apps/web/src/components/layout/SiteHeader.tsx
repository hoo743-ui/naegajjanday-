"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useFeatures } from "@/lib/api/hooks";
import { useAuth } from "@/lib/auth/AuthProvider";
import { cn } from "@/lib/utils";

const ALL_LINKS = [
  { href: "/plan", label: "코스 짜기" },
  { href: "/explore", label: "둘러보기" },
  { href: "/chat", label: "짠이와 대화" },
  { href: "/my", label: "내 코스" },
];

interface SiteHeaderProps {
  /** 랜딩처럼 히어로 위에 투명하게 얹을 때 */
  overlay?: boolean;
}

export function SiteHeader({ overlay = false }: SiteHeaderProps) {
  // 채팅 입구는 쓸 수 있다고 확인된 뒤에만 보인다. 확인 전에 보여 주면, LLM 이 없는 환경(지금의 실제 환경)에서는
  // 입구가 떴다가 1~2초 뒤에 사라진다 — 누르려던 버튼이 손 밑에서 바뀐다(버튼 전수 검사가 잡았다).
  const chatOff = useFeatures().data?.chat !== true;
  const LINKS = chatOff
    ? ALL_LINKS.filter((l) => l.href !== "/chat")
    : ALL_LINKS;
  const pathname = usePathname();
  const { status, me, isStaff } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => setOpen(false), [pathname]);

  const solid = scrolled || open || !overlay;
  // 코스를 짜는 중이거나 결과를 보는 중에는 "무료로 추천받기"를 띄우지 않는다: /plan 에서는 제자리 링크(눌러도 아무 일 없음)이고,
  // 결과 화면에서는 방금 받은 사람에게 또 받으라고 하는 셈이다.
  const showCta = !pathname.startsWith("/plan") && !pathname.startsWith("/course");

  return (
    <header
      className={cn(
        "inset-x-0 top-0 z-50 pt-[env(safe-area-inset-top,0px)] transition-[background,box-shadow] duration-300",
        overlay ? "fixed" : "sticky",
        solid &&
          "bg-paper/85 shadow-[0_1px_0_rgba(16,25,46,.08)] backdrop-blur-xl",
      )}
    >
      <div className="wrap flex h-(--header-h) items-center justify-between gap-4">
        <Link
          href="/"
          className="-ml-1 flex items-center gap-2 rounded-xl px-1 font-round text-[22px] leading-none hover:opacity-80"
          aria-label="내가짠데이 홈"
          aria-current={pathname === "/" ? "page" : undefined}
        >
          <Jjani mood="hi" size={32} animated={false} decorative />
          내가짠데이
        </Link>

        <nav
          aria-label="주요 메뉴"
          className="hidden items-center gap-1 text-[15px] font-semibold md:flex"
        >
          {[
            ...LINKS,
            ...(isStaff ? [{ href: "/admin", label: "관리자" }] : []),
          ].map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname.startsWith(link.href) ? "page" : undefined}
              className="rounded-lg px-3 py-2 text-ink-2/80 hover:bg-ink/[0.05] hover:text-ink aria-[current=page]:bg-blue-soft aria-[current=page]:text-blue-deep"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-1.5">
          {status === "authenticated" && me ? (
            <Link
              href="/my"
              className="hidden rounded-lg px-3 py-2 text-sm font-semibold text-ink-2 hover:bg-ink/[0.05] hover:text-ink sm:block"
            >
              {me.nickname} 님
            </Link>
          ) : status === "anonymous" ? (
            <Link
              href="/login"
              className="hidden rounded-lg px-3 py-2 text-sm font-semibold text-ink-2 hover:bg-ink/[0.05] hover:text-ink sm:block"
            >
              로그인
            </Link>
          ) : null}
          {showCta ? (
            <Button asChild variant="brand" size="md" className="hidden sm:inline-flex">
              <Link href="/plan" onClick={() => track("plan_started", { entry: "nav" })}>
                무료로 추천받기
              </Link>
            </Button>
          ) : null}
          <button
            type="button"
            className="grid size-11 place-items-center rounded-xl text-ink md:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "메뉴 닫기" : "메뉴 열기"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X aria-hidden /> : <Menu aria-hidden />}
          </button>
        </div>
      </div>

      {open ? (
        <nav
          id="mobile-nav"
          aria-label="모바일 메뉴"
          className="wrap grid animate-page gap-1 pb-5 md:hidden"
        >
          {[
            ...LINKS,
            ...(isStaff ? [{ href: "/admin", label: "관리자" }] : []),
            ...(status === "anonymous"
              ? [{ href: "/login", label: "로그인" }]
              : []),
          ].map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname.startsWith(link.href) ? "page" : undefined}
              className="rounded-xl px-3 py-3 text-base font-semibold text-ink-2 hover:bg-soft aria-[current=page]:bg-blue-soft aria-[current=page]:text-blue-deep"
            >
              {link.label}
            </Link>
          ))}
          {showCta ? (
            <Button asChild variant="brand" size="xl" className="mt-2">
              <Link href="/plan" onClick={() => track("plan_started", { entry: "nav" })}>
                무료로 추천받기
              </Link>
            </Button>
          ) : null}
        </nav>
      ) : null}
    </header>
  );
}
