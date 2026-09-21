"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { LottiePlayer } from "@/components/LottiePlayer";
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
        "flex flex-col items-center justify-center gap-5 px-6 text-center",
        fullscreen ? "bg-hero fixed inset-0 z-[80] bg-white" : "min-h-[52vh] py-16",
        className,
      )}
    >
      <div className="relative">
        <span aria-hidden className="absolute inset-x-0 top-5 mx-auto size-40 rounded-full bg-white/80 blur-[2px]" />
        <Jjani mood="think" size={148} floating decorative className="relative" />
        <LottiePlayer
          src="/lottie/coin-spin.json"
          className="absolute -top-1 -right-7 size-14"
          fallback={<span className="block size-full rounded-full border-4 border-gold-deep bg-gold" />}
        />
      </div>

      <div className="h-8 overflow-hidden">
        <AnimatePresence mode="wait" initial={false}>
          <motion.p
            key={stage}
            initial={reduced ? false : { y: 18, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={reduced ? undefined : { y: -18, opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.2, 0.8, 0.2, 1] }}
            className="text-lg font-extrabold tracking-tight text-ink"
          >
            {stage}
          </motion.p>
        </AnimatePresence>
      </div>

      {stages.length > 1 ? (
        <div className="flex gap-1.5" aria-hidden>
          {stages.map((s, i) => (
            <span
              key={s}
              className={cn(
                "h-1.5 rounded-full transition-all duration-500",
                i === index ? "bg-grad w-7" : "w-1.5 bg-line",
              )}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
