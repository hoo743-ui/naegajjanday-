"use client";

import type { ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { JjaniMood } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";
import { Jjani } from "./Jjani";

interface JjaniBubbleProps {
  mood?: JjaniMood;
  title: ReactNode;
  children?: ReactNode;
  /** 말풍선 색. gold = 짠이 기본, white = 컬러 배경 위 */
  tone?: "gold" | "white";
  size?: number;
  /** 내용이 바뀔 때마다 말풍선을 다시 튕긴다 */
  bubbleKey?: string | number;
  /** 스크린리더에 변경을 알릴지 */
  live?: boolean;
  className?: string;
}

/** 짠이 + 말풍선. 짠이가 "말하는" 모든 곳(결과 헤더, 예산 반응, 챗봇 인사)에 쓴다. */
export function JjaniBubble({
  mood = "hi",
  title,
  children,
  tone = "gold",
  size = 76,
  bubbleKey,
  live = false,
  className,
}: JjaniBubbleProps) {
  const reduced = useReducedMotion();
  return (
    <div className={cn("flex items-center gap-3.5", className)}>
      <Jjani mood={mood} size={size} />
      <div className="relative min-w-0 flex-1" aria-live={live ? "polite" : undefined}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={bubbleKey ?? "bubble"}
            initial={reduced ? false : { opacity: 0, scale: 0.94, x: -6 }}
            animate={{ opacity: 1, scale: 1, x: 0 }}
            exit={reduced ? undefined : { opacity: 0, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 380, damping: 26 }}
            style={{ transformOrigin: "left center" }}
            className={cn(
              "relative rounded-[20px] px-4.5 py-3.5",
              tone === "gold" ? "bg-gold-soft text-gold-ink" : "bg-white text-muted-foreground shadow-soft",
            )}
          >
            <span
              aria-hidden
              className={cn(
                "absolute top-1/2 -left-1.5 size-3.5 -translate-y-1/2 rotate-45 rounded-[3px]",
                tone === "gold" ? "bg-gold-soft" : "bg-white",
              )}
            />
            <b className="block text-body-lg leading-snug font-extrabold text-ink">{title}</b>
            {children ? <span className="mt-0.5 block text-body-sm font-semibold">{children}</span> : null}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
