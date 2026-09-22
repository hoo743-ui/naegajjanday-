"use client";

import type { CSSProperties } from "react";
import { Check } from "lucide-react";
import { Money } from "@/components/brand/Money";
import { sampleCourse } from "@/components/brand/sample-course";
import { Jjani } from "@/components/mascot/Jjani";
import { won } from "@/lib/format";
import type { JjaniMood } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";
import { STEPS } from "./schema";

export interface ReceiptLine {
  /** 이 단계에서 고른 것: "홍대입구", "데이트", "2명 · 50,000원" … 아직 없으면 undefined */
  value?: string;
}

interface ReceiptProgressProps {
  step: number;
  lines: ReceiptLine[];
  /** 예산 단계부터: 이 예산이면 이런 하루(예시) */
  budget?: { total: number; party: number };
  jjani: { mood: JjaniMood; line: string };
  onJump: (index: number) => void;
}

const label = (i: number, step: number) => `${i + 1}단계 ${STEPS[i]!.title}${i < step ? " (완료, 돌아가기)" : i === step ? " (현재)" : ""}`;

/**
 * 위저드의 진행 표시 = 한 줄씩 찍히는 영수증 (docs/25 §5). "폼을 채운다"가 아니라 "오늘의 영수증이 출력된다".
 * 고를 때마다 그 줄이 찍히고, 예산을 정하면 그 예산으로 하는 하루(예시)와 남은 돈이 이어서 찍힌다.
 * 찍힌 줄을 누르면 그 단계로 돌아간다(예전 진행 막대의 버튼과 같은 이름).
 *
 * 데스크톱: 옆에 붙어 있는 영수증. 모바일: 화면 위의 얇은 영수증 띠(네 칸).
 */
export function ReceiptProgress({ step, lines, budget, jjani, onJump }: ReceiptProgressProps) {
  const items = budget ? sampleCourse(Math.floor(budget.total / Math.max(1, budget.party)), budget.party) : [];
  const spent = items.reduce((sum, item) => sum + item.price, 0);

  return (
    <>
      {/* 모바일 · 태블릿: 얇은 영수증 띠 */}
      <div className="receipt-wrap mb-8 lg:hidden">
      <ol aria-label="진행 단계" className="receipt grid grid-cols-4 px-1 py-2">
        {STEPS.map((s, i) => {
          const done = i < step;
          const value = lines[i]?.value;
          return (
            <li key={s.key} aria-current={i === step ? "step" : undefined} className="min-w-0 border-l border-dashed border-ink/15 first:border-l-0">
              <button type="button" disabled={!done} onClick={() => onJump(i)} aria-label={label(i, step)} className="block w-full min-w-0 px-2.5 py-1.5 text-left disabled:cursor-default">
                <span className={cn("tabular flex items-center gap-1 text-[11px] font-extrabold", i === step ? "text-blue-deep" : done ? "text-ink-2" : "text-muted-foreground")}>
                  {done ? <Check aria-hidden className="size-3" /> : null}
                  {String(i + 1).padStart(2, "0")} {s.title.split(" · ")[0]}
                </span>
                <span className={cn("mt-0.5 block truncate text-[12.5px] font-bold", value && i <= step ? "text-ink" : "text-ink/25")}>{value && i <= step ? value : "· · ·"}</span>
              </button>
            </li>
          );
        })}
      </ol>
      </div>

      {/* 데스크톱: 옆에 붙어 있는 영수증 */}
      <aside aria-label="오늘의 영수증" className="hidden lg:sticky lg:top-[calc(var(--header-h)+32px)] lg:col-start-2 lg:row-start-1 lg:block lg:self-start">
        <div className="receipt-wrap">
          <div className="receipt px-6 pt-7 pb-6">
            <p className="text-center font-round text-[19px] tracking-tight text-ink">내가짠데이</p>
            <p className="mt-1 text-center text-[12px] font-bold text-muted-foreground">오늘의 영수증 · 출력 중</p>
            <hr className="receipt-rule my-4" />

            <ol aria-label="진행 단계" className="grid gap-1">
              {STEPS.map((s, i) => {
                const done = i < step;
                const current = i === step;
                const value = lines[i]?.value;
                const printed = Boolean(value) && i <= step;
                return (
                  <li key={s.key} aria-current={current ? "step" : undefined}>
                    <button
                      type="button"
                      disabled={!done}
                      onClick={() => onJump(i)}
                      aria-label={label(i, step)}
                      className={cn("-mx-2 flex w-[calc(100%+16px)] items-baseline gap-2 rounded-lg px-2 py-1.5 text-left text-[14px] disabled:cursor-default", done && "hover:bg-paper-2")}
                    >
                      <span className={cn("tabular w-5 shrink-0 text-[11.5px] font-extrabold", current ? "text-blue-deep" : "text-muted-foreground")}>{String(i + 1).padStart(2, "0")}</span>
                      <span className={cn("shrink-0 font-bold", current ? "text-blue-deep" : "text-muted-foreground")}>{s.title.split(" · ")[0] === "인원" ? "인원 · 예산" : s.title}</span>
                      <span aria-hidden className="receipt-leader" />
                      {printed ? (
                        <span key={value} className="receipt-line min-w-0 max-w-[58%] shrink truncate text-right font-extrabold text-ink" style={{ "--i": 0 } as CSSProperties}>
                          {value}
                        </span>
                      ) : (
                        <span className={cn("shrink-0 font-bold", current ? "animate-pulse text-blue-deep" : "text-ink/25")}>{current ? "고르는 중" : "—"}</span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ol>

            {budget ? (
              <>
                <hr className="receipt-rule my-4" />
                <p className="mb-2 text-[12px] font-extrabold text-muted-foreground">이 예산이면 이런 하루 · 예시</p>
                <ol className="grid gap-1.5">
                  {items.map((item, i) => (
                    <li key={`${item.label}-${item.name}`} className="receipt-line flex items-baseline gap-2 text-[13px]" style={{ "--i": i } as CSSProperties}>
                      <span className="min-w-0 shrink truncate font-semibold text-ink-2">
                        <span className="text-muted-foreground">{item.label}</span> {item.name}
                      </span>
                      <span aria-hidden className="receipt-leader" />
                      <span className="tabular shrink-0 font-bold text-ink">{item.price === 0 ? "무료" : won(item.price)}</span>
                    </li>
                  ))}
                </ol>
                <div className="mt-4 flex items-baseline justify-between rounded-2xl bg-gold-soft px-4 py-3 text-gold-ink">
                  <span className="text-[13px] font-extrabold">남은 돈</span>
                  <Money value={Math.max(0, budget.total - spent)} className="text-[22px] leading-none font-extrabold tracking-tight" />
                </div>
                <p className="mt-2 text-center text-[11px] text-muted-foreground">업종 평균가로 만든 예시예요. 실제 코스는 진짜 가게로 짜요.</p>
              </>
            ) : (
              <p className="mt-5 text-center text-[12px] leading-relaxed text-muted-foreground">
                고를 때마다 한 줄씩 찍혀요.
                <br />
                예산을 정하면 남은 돈이 나와요.
              </p>
            )}
          </div>
        </div>

        {/* 짠이: 고른 것에 한 줄로 반응한다 */}
        <p className="mt-5 flex items-center gap-2.5 text-[14px] font-extrabold text-ink" aria-live="polite">
          <Jjani mood={jjani.mood} size={40} animated={false} decorative />
          <span key={jjani.line} className="animate-page">
            {jjani.line}
          </span>
        </p>
      </aside>
    </>
  );
}
