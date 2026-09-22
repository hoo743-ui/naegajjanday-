"use client";

import { Clock, RotateCw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { RouteIssue } from "@/lib/api/types";

interface RouteIssuesProps {
  issues: RouteIssue[];
  /** 코스를 다시 짠다 (남의 코스면 없음) */
  onReroll?: () => void;
  busy?: boolean;
}

/**
 * 경로 점검 (docs/27 §17): 실제 이동 시간으로 다시 재 보니 일정이 어긋나는 곳을 분명하게 말한다.
 * 오류(그대로 다니기 어려움) → 이유 + [코스 다시 짜기]. 주의(조금 늦음 · 멀다 · 영업시간) → 조용한 목록.
 * 계산하지 못한 구간(info)은 그 구간 줄에서 말하므로 여기서는 다시 말하지 않는다.
 */
export function RouteIssues({ issues, onReroll, busy }: RouteIssuesProps) {
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");
  if (errors.length === 0 && warnings.length === 0) return null;
  return (
    <section aria-label="경로 점검" className="grid gap-2.5">
      {errors.length > 0 ? (
        <div role="alert" className="rounded-2xl bg-pink-soft px-4 py-3.5">
          <p className="flex items-center gap-2 text-body-sm font-bold text-pink-deep">
            <TriangleAlert aria-hidden className="size-4 shrink-0" />이 일정은 이대로 다니기 어려워요
          </p>
          <ul className="mt-1.5 grid gap-1 pl-6 text-body-sm text-ink-2">
            {errors.map((e) => (
              <li key={`${e.code}-${e.stop ?? e.leg ?? ""}`}>{e.message}</li>
            ))}
          </ul>
          {onReroll ? (
            <Button type="button" variant="soft" size="md" className="mt-3 bg-white" onClick={onReroll} disabled={busy}>
              <RotateCw aria-hidden /> 코스 다시 짜기
            </Button>
          ) : null}
        </div>
      ) : null}
      {warnings.length > 0 ? (
        <ul role="status" className="grid gap-1.5 rounded-2xl bg-paper-2 px-4 py-3 text-body-sm text-ink-2">
          {warnings.map((w) => (
            <li key={`${w.code}-${w.stop ?? w.leg ?? ""}`} className="flex gap-2">
              <Clock aria-hidden className="mt-1 size-3.5 shrink-0 text-muted-foreground" />
              {w.message}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
