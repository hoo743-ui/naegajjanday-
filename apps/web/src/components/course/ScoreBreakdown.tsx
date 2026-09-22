"use client";

import { motion, useReducedMotion } from "motion/react";
import { SCORE_FEATURES, type ScoreBreakdown as Scores, type ScoreFeature } from "@/lib/api/types";
import { FEATURE_INFO } from "@/lib/format";
import { cn } from "@/lib/utils";

interface ScoreBreakdownProps {
  scores: Scores;
  total: number;
  /** 이 코스에 실제 자료가 없는 항목 — 자료 없이 채운 중립값을 "분석한 점수"처럼 보여 주지 않는다 */
  hidden?: readonly ScoreFeature[];
  className?: string;
}

/**
 * "왜 여기?" — 점수 항목을 0~100 막대로 보여 준다. 실제 자료가 있는 항목만 그린다(제목의 개수도 그에 맞춘다).
 * 막대는 피처별 적합도(f_k)이고, 종합 점수는 목적별 가중치(w_k)를 곱해 더한 값이라
 * 막대의 단순 평균과는 다르다. 그 점을 화면에 밝혀 둔다.
 */
export function ScoreBreakdown({ scores, total, hidden = [], className }: ScoreBreakdownProps) {
  const reduced = useReducedMotion();
  const shown = SCORE_FEATURES.filter((key) => !hidden.includes(key));
  const top = [...shown].sort((a, b) => (scores[b] ?? 0) - (scores[a] ?? 0)).slice(0, 2);

  return (
    <div className={cn("rounded-2xl bg-soft p-4", className)}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="text-body-sm font-semibold text-ink-2">짠이가 본 {shown.length}가지</p>
        <p className="tabular text-body-sm font-bold text-muted-foreground">
          종합 <b className="text-body font-extrabold text-blue-deep">{Math.round(total * 100)}</b>점
        </p>
      </div>
      <dl className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
        {shown.map((key, i) => {
          const value = Math.max(0, Math.min(1, scores[key] ?? 0));
          const strong = top.includes(key);
          const info = FEATURE_INFO[key];
          return (
            <div key={key} title={info.hint}>
              <div className="flex items-baseline justify-between text-body-sm">
                <dt className={cn("font-bold", strong ? "text-ink" : "text-ink-2")}>
                  {info.label}
                  {strong ? <span className="ml-1.5 rounded-md bg-blue-soft px-1.5 py-0.5 text-caption font-semibold text-blue-deep">강점</span> : null}
                </dt>
                <dd className="tabular font-extrabold text-ink">
                  {Math.round(value * 100)}
                  <span className="sr-only">점. {info.hint}</span>
                </dd>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-paper-2" aria-hidden>
                <motion.div
                  className={cn("h-full origin-left rounded-full", strong ? "bg-blue-deep" : "bg-blue/45")}
                  style={{ width: `${value * 100}%` }}
                  initial={reduced ? false : { scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ duration: 0.6, delay: i * 0.04, ease: [0.2, 0.8, 0.2, 1] }}
                />
              </div>
            </div>
          );
        })}
      </dl>
      <p className="mt-3 text-caption text-muted-foreground">
        막대는 항목별 적합도예요. 종합 점수는 목적에 따라 항목마다 다른 비중을 곱해 더한 값이라 막대의 평균과는 달라요. 점수는 AI가 아니라 정해진 계산식으로 매겨요.
      </p>
    </div>
  );
}
