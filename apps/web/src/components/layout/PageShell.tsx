import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

interface PageShellProps {
  children: ReactNode;
  /** 은은한 히어로 그라디언트 배경 */
  tinted?: boolean;
  footer?: boolean;
  /** false: 화면이 자기 헤더를 그린다 (코스 결과 화면의 결과용 헤더) */
  header?: boolean;
  className?: string;
}

/** 랜딩·관리자 외의 일반 페이지 골격: sticky 헤더 + main#main + 푸터 */
export function PageShell({ children, tinted = false, footer = true, header = true, className }: PageShellProps) {
  return (
    <div className={cn("flex min-h-dvh flex-col", tinted && "bg-hero")}>
      {header ? <SiteHeader /> : null}
      <main id="main" className={cn("flex-1 animate-page", className)}>
        {children}
      </main>
      {footer ? <SiteFooter /> : null}
    </div>
  );
}
