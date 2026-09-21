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
  className?: string;
}

const SIZE = { sm: 84, md: 120, lg: 156 } as const;

/** 목록이 비었을 때·아직 아무것도 없을 때. 모든 리스트/페이지의 빈 상태는 이 컴포넌트를 쓴다. */
export function EmptyState({ mood = "think", title, description, children, footnote, size = "md", className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        size === "sm" ? "gap-2 px-4 py-8" : "gap-3 px-6 py-14",
        className,
      )}
    >
      <Jjani mood={mood} size={SIZE[size]} floating={size !== "sm"} />
      <h3 className={cn("font-extrabold tracking-tight text-ink", size === "sm" ? "text-base" : "text-xl")}>{title}</h3>
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
