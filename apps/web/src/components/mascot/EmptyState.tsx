"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { mascotCopyForError, type JjaniMood } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";
import { Jjani } from "./Jjani";

interface EmptyStateProps {
  mood?: JjaniMood;
  title: string;
  description?: ReactNode;
  /** 버튼 등 */
  children?: ReactNode;
  /** 맨 아래 작은 글씨 (오류 코드 등) */
  footnote?: ReactNode;
  size?: "sm" | "md" | "lg";
  /** lost: 짠이 옆에 끊긴 경로 한 줄 (404 · 없는 코스) */
  scene?: "lost";
  className?: string;
}

/** 콘텐츠 80 : 캐릭터 20 (docs/25 §6) — 짠이는 문장보다 크지 않게 */
const SIZE = { sm: 72, md: 96, lg: 120 } as const;

/** 길을 잃은 장면: 하루의 선(경로)이 가다가 끊기고 물음표가 남는다 */
function LostRoute() {
  return (
    <svg aria-hidden viewBox="0 0 220 70" className="h-auto w-[180px] text-ink/30">
      <path d="M4 52 C 40 52 48 18 86 18 S 132 56 160 40" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeDasharray="2 7" />
      <circle cx="4" cy="52" r="4" fill="currentColor" />
      <text x="176" y="48" fontSize="30" fontWeight="800" fill="var(--blue-deep)" fontFamily="Pretendard Variable, sans-serif">?</text>
    </svg>
  );
}

/** 목록이 비었을 때·아직 아무것도 없을 때. 모든 리스트/페이지의 빈 상태는 이 컴포넌트를 쓴다. */
export function EmptyState({ mood = "think", title, description, children, footnote, size = "md", scene, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        size === "sm" ? "gap-2 px-4 py-8" : "gap-3 px-6 py-14",
        className,
      )}
    >
      {scene === "lost" ? (
        <div className="flex items-end gap-1">
          <LostRoute />
          <Jjani mood={mood} size={SIZE[size]} />
        </div>
      ) : (
        <Jjani mood={mood} size={SIZE[size]} />
      )}
      <h3 className={cn("font-extrabold tracking-tight text-ink", size === "sm" ? "text-base" : size === "lg" ? "mt-1 font-serif text-[clamp(24px,3vw,32px)] font-bold" : "text-xl")}>{title}</h3>
      {description ? (
        <p className={cn("max-w-md text-muted-foreground", size === "sm" ? "text-sm" : "text-[15px]")}>{description}</p>
      ) : null}
      {children ? <div className="mt-3 flex flex-wrap items-center justify-center gap-2.5">{children}</div> : null}
      {footnote ? <p className="mt-2 text-xs text-muted-foreground/80">{footnote}</p> : null}
    </div>
  );
}

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  size?: EmptyStateProps["size"];
  className?: string;
}

/** API 에러 → `code` 로 짠이 표정·문구를 골라 보여준다. 가짜 데이터로 대체하지 않는다. */
export function ErrorState({ error, onRetry, size = "md", className }: ErrorStateProps) {
  const copy = mascotCopyForError(error);
  return (
    <div role="alert" className={className}>
      <EmptyState
        mood={copy.mood}
        title={copy.title}
        description={copy.description}
        size={size}
        footnote={`오류 코드 ${copy.code}${copy.traceId ? ` · ${copy.traceId}` : ""}`}
      >
        {copy.retry && onRetry ? (
          <Button variant="brand" size="md" onClick={onRetry}>
            <RotateCw aria-hidden /> 다시 시도
          </Button>
        ) : null}
        {copy.action ? (
          <Button asChild variant={copy.retry && onRetry ? "soft" : "brand"} size="md">
            <Link href={copy.action.href}>{copy.action.label}</Link>
          </Button>
        ) : null}
        {!copy.retry && !copy.action && onRetry ? (
          <Button variant="soft" size="md" onClick={onRetry}>
            <RotateCw aria-hidden /> 다시 시도
          </Button>
        ) : null}
      </EmptyState>
    </div>
  );
}
