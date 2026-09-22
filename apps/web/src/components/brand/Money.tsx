"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";

const DURATION_MS = 520;
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * 움직이는 금액 — 이 서비스에서 "움직임"은 돈이 바뀔 때 쓴다(모션 원칙 1).
 * 값이 바뀌면 이전 값에서 새 값으로 굴러간다. 화면 낭독기에는 최종 값만 읽힌다.
 */
export function Money({ value, className, suffix = "원", duration = DURATION_MS }: { value: number; className?: string; suffix?: string; /** 첫 등장의 셈(랜딩 시퀀스)은 조금 더 길게 */ duration?: number }) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(value);
  const from = useRef(value);

  useEffect(() => {
    if (reduced || from.current === value) {
      from.current = value;
      setShown(value);
      return;
    }
    const start = performance.now();
    const origin = from.current;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      // 1,000원 단위로 굴러야 영수증처럼 읽힌다 (37,482원 같은 중간값은 가짜 같다)
      setShown(Math.round((origin + (value - origin) * easeOut(t)) / 100) * 100);
      if (t < 1) frame = requestAnimationFrame(tick);
      else from.current = value;
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      from.current = value;
    };
  }, [value, reduced, duration]);

  return (
    <span className={className}>
      <span aria-hidden className="tabular">
        {shown.toLocaleString("ko-KR")}
        {suffix}
      </span>
      <span className="sr-only">
        {value.toLocaleString("ko-KR")}
        {suffix}
      </span>
    </span>
  );
}
