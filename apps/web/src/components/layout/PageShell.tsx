import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

interface PageShellProps {
  children: ReactNode;
  /** 은은한 히어로 그라디언트 배경 */
  tinted?: boolean;
  footer?: boolean;
  className?: string;
}

/** 랜딩·관리자 외의 일반 페이지 골격: sticky 헤더 + main#main + 푸터 */
export function PageShell({ children, tinted = false, footer = true, className }: PageShellProps) {
  return (
    <div className={cn("flex min-h-dvh flex-col", tinted && "bg-hero")}>
      <SiteHeader />
      <main id="main" className={cn("flex-1 animate-page", className)}>
        {children}
      </main>
      {footer ? <SiteFooter /> : null}
    </div>
  );
}
