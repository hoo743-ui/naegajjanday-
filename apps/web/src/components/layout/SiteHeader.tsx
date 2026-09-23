"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { Wordmark } from "@/components/brand/Wordmark";
import { Jjani } from "@/components/mascot/Jjani";
import { track } from "@/lib/analytics";
import { useFeatures } from "@/lib/api/hooks";
import { useAuth } from "@/lib/auth/AuthProvider";
import { cn } from "@/lib/utils";
import { TAB_DOCK_AT } from "./TabBar";

const ALL_LINKS = [
  { href: "/plan", label: "코스 짜기" },
  { href: "/explore", label: "둘러보기" },
  { href: "/chat", label: "짠이와 대화" },
  { href: "/my", label: "내 코스" },
];

interface SiteHeaderProps {
  /** 랜딩처럼 히어로 위에 투명하게 얹을 때 */
  overlay?: boolean;
  /** 모바일 아래 탭 바가 있는 화면이면 햄버거 메뉴는 없다(탭 바가 메뉴다). 없는 화면(위저드 · 채팅)만 햄버거 */
  tabBar?: boolean;
}

export function SiteHeader({ overlay = false, tabBar = true }: SiteHeaderProps) {
  // 채팅 입구는 쓸 수 있다고 확인된 뒤에만 보인다. 확인 전에 보여 주면, LLM 이 없는 환경(지금의 실제 환경)에서는
  // 입구가 떴다가 1~2초 뒤에 사라진다 — 누르려던 버튼이 손 밑에서 바뀐다(버튼 전수 검사가 잡았다).
  const chatOff = useFeatures().data?.chat !== true;
  const LINKS = chatOff
    ? ALL_LINKS.filter((l) => l.href !== "/chat")
    : ALL_LINKS;
  const pathname = usePathname();
  const { status, me, isStaff } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  // 아래 탭(넓은 화면의 알약)이 떠오르는 지점 — TabBar 와 같은 값. 거기서부터 헤더의 메뉴는 알약에 자리를 넘긴다
  const [handedOff, setHandedOff] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 12);
      setHandedOff(window.scrollY > TAB_DOCK_AT);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => setOpen(false), [pathname]);

  const solid = scrolled || open || !overlay;
  // 헤더에는 CTA 를 두지 않는다 (docs/31 §10): 행동은 그 행동을 하는 자리(히어로의 예산 · 위저드 · 결과의 저장)에만.
  // "코스 짜기"는 메뉴의 첫 항목이 그 입구다.

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
          className="-ml-1 flex min-h-11 items-center gap-2 rounded-xl px-1 hover:opacity-80"
          aria-label="내가짠데이 홈"
          aria-current={pathname === "/" ? "page" : undefined}
        >
          <Jjani mood="hi" size={30} animated={false} decorative />
          <Wordmark size="sm" />
        </Link>

        {/* 넓은 화면의 메뉴는 여기. 아래 탭(알약)은 이 헤더가 화면 밖으로 나갔을 때만 떠오른다 */}
        <nav
          aria-label="주요 메뉴"
          className={cn(
            "hidden items-center gap-1 text-body font-semibold transition-opacity duration-300 md:flex",
            tabBar && handedOff && "md:invisible md:opacity-0",
          )}
        >
          {[
            ...LINKS,
            ...(isStaff ? [{ href: "/admin", label: "관리자" }] : []),
          ].map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={link.href === "/plan" ? () => track("plan_started", { entry: "nav" }) : undefined}
              aria-current={pathname.startsWith(link.href) ? "page" : undefined}
              // 지금 있는 곳은 상자가 아니라 밑줄 한 줄 (간판 · 지도의 선처럼)
              className="relative inline-flex min-h-11 items-center px-3 text-ink-2/80 after:absolute after:inset-x-3 after:bottom-0.5 after:h-[2px] after:bg-transparent hover:text-ink aria-[current=page]:text-ink aria-[current=page]:after:bg-ink"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-1.5">
          {status === "authenticated" && me ? (
            <Link
              href="/my"
              className="hidden min-h-11 items-center rounded-lg px-3 text-body-sm font-semibold text-ink-2 hover:bg-ink/[0.05] hover:text-ink sm:flex"
            >
              {me.nickname} 님
            </Link>
          ) : status === "anonymous" ? (
            <Link
              href="/login"
              className={cn("min-h-11 items-center rounded-lg px-3 text-body-sm font-semibold text-ink-2 hover:bg-ink/[0.05] hover:text-ink", tabBar ? "flex" : "hidden sm:flex")}
            >
              로그인
            </Link>
          ) : null}
          <button
            type="button"
            className={cn("size-11 place-items-center rounded-xl text-ink md:hidden", tabBar ? "hidden" : "grid")}
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "메뉴 닫기" : "메뉴 열기"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X aria-hidden /> : <Menu aria-hidden />}
          </button>
        </div>
      </div>

      {open && !tabBar ? (
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
              className="rounded-xl px-3 py-3 text-body font-semibold text-ink-2 hover:bg-soft aria-[current=page]:bg-blue-soft aria-[current=page]:text-blue-deep"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      ) : null}
    </header>
  );
}
