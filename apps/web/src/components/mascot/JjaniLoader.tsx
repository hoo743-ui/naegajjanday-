"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Jjani } from "./Jjani";

const DEFAULT_STAGES = ["짠이가 준비하는 중이에요"];

interface JjaniLoaderProps {
  /** 차례로 찍히는 단계 문구(한 줄씩). 마지막 단계에서 멈춘다 — 돌고 돌지 않는다 */
  stages?: string[];
  /** 단계 사이 간격(ms) */
  interval?: number;
  /** 보조 한 줄 (짧게) */
  note?: string;
  /** 화면 위에 얹는 전환 패널로 띄울지. 아니면 그 자리(페이지 로딩)에 */
  fullscreen?: boolean;
  /** 5초가 넘으면 보여 줄 행동 (예: 다시 시도 · 조건 수정). 없으면 말만 한다 */
  actions?: ReactNode;
  className?: string;
}

/** 기다림이 길어질 때: 2초 → 안심 한 줄, 5초 → 행동 */
const PATIENT_MS = 2000;
const STUCK_MS = 5000;

/**
 * 전환 패널 (docs/41): 기다리는 화면이 아니라 "코스가 만들어지는 중"을 보여 주는 작은 영수증.
 * 단계가 영수증 줄처럼 한 줄씩 찍히고(끝난 줄은 민트 체크), 마지막 단계에 작은 "짠" 도장이 찍힌다.
 * 스피너 · 큰 캐릭터 · 화면 전체를 가리는 무거운 덮개 없이 — 종이색 오버레이 위 360~440px 패널 하나.
 * 규격: 패널 등장 180ms · 줄 출력 150ms · 도장 200ms (globals.css `.jj-loader`). 모션 최소화면 움직이지 않는다.
 */
export function JjaniLoader({ stages = DEFAULT_STAGES, interval = 900, note, fullscreen = false, actions, className }: JjaniLoaderProps) {
  const [index, setIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (stages.length <= 1) return;
    const timer = setInterval(() => setIndex((i) => Math.min(i + 1, stages.length - 1)), interval);
    return () => clearInterval(timer);
  }, [stages.length, interval]);

  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Date.now() - started), 500);
    return () => clearInterval(timer);
  }, []);

  const printed = stages.slice(0, index + 1);
  const last = index >= stages.length - 1;
  const current = stages[index] ?? DEFAULT_STAGES[0];

  const panel = (
    <div className="jj-loader relative w-[min(420px,calc(100vw-32px))] rounded-lg bg-white px-5 pt-5 pb-4 shadow-[0_14px_32px_rgba(40,32,20,.14)]">
      {/* 머리: 지금 하는 일 한 줄 + 보조 한 줄 */}
      <p className="text-body-lg font-bold text-ink" aria-live="polite">
        {current}
      </p>
      <p className="mt-0.5 min-h-[1.5em] text-body-sm text-muted-foreground">
        {elapsed >= STUCK_MS ? "조건이 넓으면 조금 더 걸려요." : elapsed >= PATIENT_MS ? "조금만 기다려 주세요. 예산을 넘는 곳은 빼고 있어요." : (note ?? "")}
      </p>

      {/* 영수증 줄: 지나간 단계는 민트 체크, 지금 단계는 점선이 이어진다 */}
      <ol aria-hidden className="mt-3 grid gap-1.5 border-t-[1.5px] border-dashed border-ink/20 pt-3">
        {printed.map((s, i) => {
          const done = i < index;
          return (
            <li key={s} className="jj-loader-line flex items-center gap-2 text-body-sm">
              <span className={cn("grid size-4 shrink-0 place-items-center rounded-full", done ? "bg-mint text-white" : "border-[1.5px] border-ink/30")}>
                {done ? <Check strokeWidth={3.5} className="size-2.5" /> : null}
              </span>
              <span className={cn("min-w-0 truncate", done ? "text-ink-2" : "font-semibold text-ink")}>{s}</span>
              {done ? null : <span className="jj-loader-leader receipt-leader min-w-6 flex-1" />}
            </li>
          );
        })}
      </ol>

      {elapsed >= STUCK_MS && actions ? <div className="mt-3 flex flex-wrap gap-2">{actions}</div> : null}

      {/* 짠이는 모서리에 작게, 도장은 마지막 단계에서 한 번 */}
      <Jjani mood="think" size={30} decorative className="absolute -top-3 -right-2" />
      {last && stages.length > 1 ? (
        <span aria-hidden className="jj-loader-stamp">
          짠
        </span>
      ) : null}
    </div>
  );

  return (
    <div
      role="status"
      className={cn(
        "grid justify-items-center px-4",
        // 화면 위에 얹을 때: 종이색 오버레이 위, 가운데보다 조금 위(모바일에서 버튼 · 탭 바를 가리지 않게)
        fullscreen ? "paper-map fixed inset-0 z-[80] content-start bg-paper/92 pt-[22vh] sm:content-center sm:pt-0" : "min-h-[52vh] content-center py-16",
        className,
      )}
    >
      {panel}
    </div>
  );
}
