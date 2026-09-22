import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Money } from "./Money";

export interface ReceiptItem {
  /** 순번 뒤에 붙는 역할: 식사 · 카페 · 산책 … */
  label: string;
  name: string;
  price: number;
  /** 가격 옆 작은 주석: "업종 평균가" 등 */
  note?: string;
}

interface ReceiptProps {
  /** 영수증 머리: "홍대입구 · 데이트 · 2명" */
  heading: ReactNode;
  caption?: ReactNode;
  items: ReceiptItem[];
  budget: number;
  footer?: ReactNode;
  /** lg: 코스 결과 화면의 주인공. 남은 돈이 화면에서 가장 큰 숫자가 된다 */
  size?: "md" | "lg";
  className?: string;
}

/**
 * 영수증 — 내가짠데이의 시그니처. 코스는 "추천 목록"이 아니라 "예산 안에서 끝나는 하루의 영수증"이다:
 * 품목 · 합계 · 그리고 남은 돈. 히어로, 결과 화면, 공유 이미지가 같은 모양을 쓴다.
 */
export function Receipt({ heading, caption, items, budget, footer, size = "md", className }: ReceiptProps) {
  const total = items.reduce((sum, item) => sum + item.price, 0);
  const left = budget - total;
  const lg = size === "lg";
  return (
    <div className={cn("receipt-wrap", className)}>
      <div className={cn("receipt receipt-print", lg ? "px-6 pt-8 pb-7 sm:px-9 sm:pt-9" : "px-6 pt-7 pb-6 sm:px-7")}>
        <p className="text-center font-round text-[19px] tracking-tight text-ink">내가짠데이</p>
        <p className="tabular mt-1 text-center text-[12.5px] font-bold text-muted-foreground">{heading}</p>
        {caption ? <p className="mt-0.5 text-center text-[11.5px] text-muted-foreground">{caption}</p> : null}

        <hr className="receipt-rule my-4" />

        <ol className="grid gap-2.5">
          {items.map((item, i) => (
            <li key={`${item.label}-${item.name}`} style={{ "--i": i } as CSSProperties} className={cn("receipt-line flex items-baseline gap-2", lg ? "text-[15px]" : "text-[14.5px]")}>
              <span className="tabular w-5 shrink-0 text-[12px] font-extrabold text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
              <span className="min-w-0 shrink truncate font-bold text-ink">
                <span className="text-muted-foreground">{item.label}</span> {item.name}
              </span>
              <span aria-hidden className="receipt-leader" />
              <span className="tabular shrink-0 font-extrabold text-ink">
                {item.price === 0 ? "무료" : `${item.price.toLocaleString("ko-KR")}원`}
              </span>
            </li>
          ))}
        </ol>

        <hr className="receipt-rule my-4" />

        <dl style={{ "--i": items.length + 1 } as CSSProperties} className="receipt-line grid gap-1.5 text-[14px]">
          <div className="flex items-baseline justify-between">
            <dt className="font-bold text-muted-foreground">예산</dt>
            <dd className="tabular font-bold text-ink-2">{budget.toLocaleString("ko-KR")}원</dd>
          </div>
          <div className="flex items-baseline justify-between">
            <dt className="font-bold text-muted-foreground">합계</dt>
            <dd className="text-[17px] font-extrabold text-ink">
              <Money value={total} />
            </dd>
          </div>
        </dl>

        {/* 이 서비스의 약속이 한 줄로 보이는 곳: 예산을 넘지 않고, 얼마가 남는지 */}
        {lg ? (
          // 결과 화면: 이 숫자 하나로 화면의 목적이 읽혀야 한다 (docs/25 §5)
          <div
            style={{ "--i": items.length + 3 } as CSSProperties}
            className={cn("receipt-line mt-5 grid gap-1 rounded-2xl px-5 pt-4 pb-5", left >= 0 ? "coin-gleam bg-gold-soft text-gold-ink" : "bg-pink-soft text-pink-deep")}
          >
            <span className="text-[13px] font-extrabold tracking-wide">{left >= 0 ? "남은 돈" : "예산 초과"}</span>
            <Money value={Math.abs(left)} className="text-[clamp(34px,9vw,44px)] leading-[1.02] font-extrabold tracking-[-0.035em]" />
          </div>
        ) : (
          <div
            style={{ "--i": items.length + 3 } as CSSProperties}
            className={cn("receipt-line mt-4 flex items-center justify-between rounded-2xl px-4 py-3", left >= 0 ? "coin-gleam bg-gold-soft text-gold-ink" : "bg-pink-soft text-pink-deep")}
          >
            <span className="text-[13.5px] font-extrabold">{left >= 0 ? "남은 돈" : "예산 초과"}</span>
            <Money value={Math.abs(left)} className="text-[22px] leading-none font-extrabold tracking-tight" />
          </div>
        )}

        {footer ? <div className="mt-4 text-center text-[11.5px] leading-relaxed text-muted-foreground">{footer}</div> : null}
      </div>
    </div>
  );
}
