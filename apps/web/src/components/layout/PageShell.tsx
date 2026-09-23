import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";
import { TabBar } from "./TabBar";

interface PageShellProps {
  children: ReactNode;
  /** 은은한 히어로 그라디언트 배경 */
  tinted?: boolean;
  footer?: boolean;
  /** false: 화면이 자기 헤더를 그린다 (코스 결과 화면의 결과용 헤더) */
  header?: boolean;
  className?: string;
  /** 모바일 아래 탭 바. 자기 버튼 줄이 아래에 있는 화면(위저드 · 채팅 입력)은 끈다 → 헤더의 메뉴가 대신한다 */
  tabBar?: boolean;
}

/** 랜딩·관리자 외의 일반 페이지 골격: sticky 헤더 + main#main + 푸터 */
export function PageShell({ children, tinted = false, footer = true, header = true, className, tabBar = true }: PageShellProps) {
  return (
    <div className={cn("flex min-h-dvh flex-col", tinted && "bg-hero")}>
      {header ? <SiteHeader tabBar={tabBar} /> : null}
      <main id="main" className={cn("flex-1 animate-page", className)}>
        {children}
      </main>
      {footer ? <SiteFooter /> : null}
      {header && tabBar ? <TabBar /> : null}
    </div>
  );
}
