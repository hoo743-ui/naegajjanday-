"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

interface RevealProps {
  children: ReactNode;
  delay?: number;
  className?: string;
  as?: "div" | "li" | "article";
}

/** 스크롤로 화면에 들어올 때 한 번 떠오른다. 모션 최소화 설정이면 그냥 보인다. */
export function Reveal({ children, delay = 0, className, as = "div" }: RevealProps) {
  const reduced = useReducedMotion();
  const Tag = motion[as];
  return (
    <Tag
      className={className}
      // docs/19 모션 원칙: 등장은 조용하게(14px · 0.6초 이내 · 한 번). 화면에 들어오기 조금 전에 시작해서,
      // 빠르게 스크롤하거나 앵커로 건너뛰어도 빈 칸을 보는 순간이 없게 한다.
      initial={reduced ? false : { opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px 12% 0px" }}
      transition={{ duration: 0.55, delay: Math.min(delay, 0.16), ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </Tag>
  );
}
