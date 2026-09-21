"use client";

import { useEffect, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import { useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

// lottie-web 은 window 를 만지므로 SSR 에서 빼고, 필요할 때만 청크를 받는다.
const Lottie = dynamic(() => import("lottie-react"), { ssr: false });

const cache = new Map<string, Promise<unknown>>();

function loadAnimation(src: string): Promise<unknown> {
  let pending = cache.get(src);
  if (!pending) {
    pending = fetch(src).then((res) => {
      if (!res.ok) throw new Error(`lottie ${res.status}`);
      return res.json() as Promise<unknown>;
    });
    pending.catch(() => cache.delete(src));
    cache.set(src, pending);
  }
  return pending;
}

interface LottiePlayerProps {
  /** `/public` 기준 경로. 예: "/lottie/coin-spin.json" */
  src: string;
  loop?: boolean;
  autoplay?: boolean;
  className?: string;
  /** JSON 로딩 전·실패 시·모션 최소화 설정일 때 보여줄 정적 대체물 */
  fallback?: ReactNode;
  label?: string;
}

export function LottiePlayer({ src, loop = true, autoplay = true, className, fallback = null, label }: LottiePlayerProps) {
  const reduced = useReducedMotion();
  const [data, setData] = useState<unknown>(null);

  useEffect(() => {
    if (reduced) return;
    let alive = true;
    loadAnimation(src)
      .then((json) => alive && setData(json))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [src, reduced]);

  return (
    <div className={cn("pointer-events-none", className)} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      {data && !reduced ? <Lottie animationData={data} loop={loop} autoplay={autoplay} className="size-full" /> : fallback}
    </div>
  );
}
