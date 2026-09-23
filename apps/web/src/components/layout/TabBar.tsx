"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bookmark, Compass, House, MessageCircle, Route, type LucideIcon } from "lucide-react";
import { track } from "@/lib/analytics";
import { useFeatures } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

interface Tab {
  href: string;
  label: string;
  Icon: LucideIcon;
  /** 이 서비스의 행동 하나: 파란 동그라미로 한 번 더 보인다 */
  primary?: boolean;
}

const TABS: Tab[] = [
  { href: "/", label: "홈", Icon: House },
  { href: "/explore", label: "둘러보기", Icon: Compass },
  { href: "/plan", label: "코스 짜기", Icon: Route, primary: true },
  { href: "/chat", label: "짠이", Icon: MessageCircle },
  { href: "/my", label: "내 코스", Icon: Bookmark },
];

/**
 * 모바일의 아래 탭 바. 햄버거 메뉴를 열어 목록을 내려야 다른 화면으로 가던 것을, 엄지가 닿는 자리의 탭 한 번으로.
 * 넓은 화면은 헤더의 메뉴가 그대로 한다(md 이상에서는 없다). 자기 버튼 줄이 아래에 있는 화면(위저드의 이전 · 다음,
 * 결과의 저장, 채팅 입력)은 쓰지 않는다 — 두 줄이 겹치지 않게 PageShell 이 끈다.
 * 흐름 안에 같은 높이의 빈칸을 둬서 페이지 끝(푸터)이 탭 바 밑에 가리지 않는다.
 */
export function TabBar() {
  const pathname = usePathname();
  // 채팅 입구는 쓸 수 있다고 확인된 뒤에만 (헤더와 같은 규칙: 떴다가 사라지는 탭이 없게)
  const chatOn = useFeatures().data?.chat === true;
  const tabs = TABS.filter((t) => t.href !== "/chat" || chatOn);
  const current = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <>
      <div aria-hidden className="h-[calc(var(--tabbar-h)+env(safe-area-inset-bottom,0px))] md:hidden" />
      <nav
        aria-label="아래 탭"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-ink/[0.08] bg-paper/92 pb-[env(safe-area-inset-bottom,0px)] backdrop-blur-xl md:hidden"
      >
        <ul className="mx-auto grid h-(--tabbar-h) max-w-[560px]" style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}>
          {tabs.map(({ href, label, Icon, primary }) => {
            const active = current(href);
            return (
              <li key={href} className="relative">
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  onClick={href === "/plan" ? () => track("plan_started", { entry: "nav" }) : undefined}
                  className={cn(
                    "flex h-full flex-col items-center justify-center gap-0.5 text-caption font-semibold transition-colors",
                    active ? "text-ink" : "text-muted-foreground hover:text-ink-2",
                  )}
                >
                  {/* 지금 있는 곳은 헤더 메뉴처럼 선 한 줄 (위쪽 가장자리) */}
                  {active && !primary ? <span aria-hidden className="absolute inset-x-[28%] top-0 h-[2px] rounded-full bg-ink" /> : null}
                  {primary ? (
                    <span className={cn("grid size-9 place-items-center rounded-full text-white shadow-soft transition-transform", active ? "bg-ink" : "bg-blue-deep")}>
                      <Icon aria-hidden className="size-[18px]" />
                    </span>
                  ) : (
                    <Icon aria-hidden className={cn("size-[22px]", active && "stroke-[2.4]")} />
                  )}
                  <span>{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
