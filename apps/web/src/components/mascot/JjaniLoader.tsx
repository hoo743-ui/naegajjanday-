"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";
import { Jjani } from "./Jjani";

const DEFAULT_STAGES = ["짠이가 준비하는 중…"];

interface JjaniLoaderProps {
  /** 순서대로 돌아가며 보여줄 단계 문구. 실제 파이프라인 단계(docs/06 §0)를 넘긴다. */
  stages?: string[];
  /** 단계 전환 간격(ms) */
  interval?: number;
  /** 화면 전체를 덮는 오버레이로 띄울지 */
  fullscreen?: boolean;
  className?: string;
}

export function JjaniLoader({ stages = DEFAULT_STAGES, interval = 1500, fullscreen = false, className }: JjaniLoaderProps) {
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (stages.length <= 1) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % stages.length), interval);
    return () => clearInterval(timer);
  }, [stages.length, interval]);

  const stage = stages[index % stages.length] ?? DEFAULT_STAGES[0];

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "grid place-content-center px-6",
        fullscreen ? "fixed inset-0 z-[80] bg-paper" : "min-h-[52vh] py-16",
        className,
      )}
    >
      {/* 기다리는 동안 보이는 것도 브랜드 언어로 (docs/32 B §21): 스피너 대신 경로가 이어지고 영수증 줄이 찍힌다 */}
      <div className="grid w-[min(400px,calc(100vw-48px))] gap-6">
        <div className="flex items-center gap-3">
          <Jjani mood="think" size={52} decorative className="shrink-0" />
          <div className="h-7 min-w-0 overflow-hidden">
            <AnimatePresence mode="wait" initial={false}>
              <motion.p
                key={stage}
                initial={reduced ? false : { y: 14, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={reduced ? undefined : { y: -14, opacity: 0 }}
                transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                className="truncate text-body-lg font-bold text-ink"
              >
                {stage}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>

        {/* 오늘의 경로가 한 곳씩 이어진다 */}
        <div aria-hidden className="relative flex items-center justify-between">
          <span className="absolute inset-x-1.5 top-1/2 border-t-2 border-dashed border-ink/20" />
          {[0, 1, 2, 3].map((i) => (
            <span key={i} style={{ animationDelay: `${i * 0.35}s` }} className="loader-node relative size-3 rounded-full border-2 border-ink bg-paper" />
          ))}
        </div>

        {/* 영수증 줄이 한 줄씩 찍힌다 */}
        <div aria-hidden className="grid gap-3 border-t-[1.5px] border-dashed border-ink/20 pt-5">
          {[0.55, 0.42, 0.62].map((w, i) => (
            <span key={i} style={{ animationDelay: `${0.2 + i * 0.35}s` }} className="loader-line flex items-end gap-2">
              <span className="h-2.5 rounded-full bg-ink/10" style={{ width: `${w * 100}%` }} />
              <span className="receipt-leader" />
              <span className="h-2.5 w-14 rounded-full bg-gold/35" />
            </span>
          ))}
        </div>

        {stages.length > 1 ? (
          <div className="flex gap-1.5" aria-hidden>
            {stages.map((s, i) => (
              <span key={s} className={cn("h-1 rounded-full transition-all duration-500", i === index ? "w-6 bg-ink" : "w-1.5 bg-line")} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
