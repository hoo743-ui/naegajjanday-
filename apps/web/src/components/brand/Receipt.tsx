import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Money } from "./Money";
import { Wordmark } from "./Wordmark";

export interface ReceiptItem {
  /** 순번 뒤에 붙는 역할: 식사 · 카페 · 산책 … */
  label: string;
  name: string;
  price: number;
  /** 가격 옆 작은 주석: "업종 평균가" 등 */
  note?: string;
  /** 그 가게의 메뉴판 가격이 아니라 같은 동네 · 업종의 1인 평균가로 계산했다 → "≈" 를 붙인다 */
  estimated?: boolean;
  /** 가격을 모른다 (0원이지만 무료가 아니다) → "무료"가 아니라 "가격 미정" */
  unknown?: boolean;
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
  /**
   * 합계 · 남은 돈의 단일 출처 (docs/28): 코스 결과는 API 가 계산한 값을 그대로 넘긴다 — 화면이 품목을 따로 더하지 않는다.
   * 없으면(히어로 · 위저드의 예시) 품목을 더한다.
   */
  totals?: { price: number; left: number };
  className?: string;
}

/**
 * 영수증 — 내가짠데이의 시그니처. 코스는 "추천 목록"이 아니라 "예산 안에서 끝나는 하루의 영수증"이다:
 * 품목 · 합계 · 그리고 남은 돈. 히어로, 결과 화면, 공유 이미지가 같은 모양을 쓴다.
 */
export function Receipt({ heading, caption, items, budget, footer, size = "md", totals, className }: ReceiptProps) {
  const total = totals?.price ?? items.reduce((sum, item) => sum + item.price, 0);
  const left = totals?.left ?? budget - total;
  const lg = size === "lg";
  // 평균가 · 가격 미정이 섞였으면 합계를 확정값처럼 부르지 않는다
  const estimated = items.filter((item) => item.estimated).length;
  const unknown = items.filter((item) => item.unknown).length;
  const uncertain = estimated + unknown > 0;
  return (
    <div className={cn("receipt-wrap", className)}>
      <div className={cn("receipt receipt-print", lg ? "px-6 pt-8 pb-7 sm:px-9 sm:pt-9" : "px-6 pt-7 pb-6 sm:px-7")}>
        <p className="text-center">
          <Wordmark size="sm" />
        </p>
        <p className="tabular mt-1 text-center text-caption font-semibold text-muted-foreground">{heading}</p>
        {caption ? <p className="mt-0.5 text-center text-caption text-muted-foreground">{caption}</p> : null}

        <hr className="receipt-rule my-4" />

        <ol className="grid gap-2.5">
          {items.map((item, i) => (
            <li key={`${item.label}-${item.name}`} style={{ "--i": i } as CSSProperties} className="receipt-line flex items-baseline gap-2 text-body">
              <span className="tabular w-5 shrink-0 text-caption font-extrabold text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
              <span className="min-w-0 shrink truncate font-semibold text-ink">
                <span className="text-muted-foreground">{item.label}</span> {item.name}
              </span>
              <span aria-hidden className="receipt-leader" />
              {item.unknown ? (
                <span className="shrink-0 text-body-sm font-semibold text-muted-foreground">가격 미정</span>
              ) : (
                <span className="tabular shrink-0 font-bold text-ink">
                  {item.estimated && item.price > 0 ? (
                    <span className="mr-0.5 font-medium text-muted-foreground" title="업종 평균가">
                      ≈
                    </span>
                  ) : null}
                  {item.price === 0 ? "무료" : `${item.price.toLocaleString("ko-KR")}원`}
                </span>
              )}
            </li>
          ))}
        </ol>

        <hr className="receipt-rule my-4" />

        <dl style={{ "--i": items.length + 1 } as CSSProperties} className="receipt-line grid gap-1.5 text-body-sm">
          <div className="flex items-baseline justify-between">
            <dt className="font-medium text-muted-foreground">예산</dt>
            <dd className="tabular font-semibold text-ink-2">{budget.toLocaleString("ko-KR")}원</dd>
          </div>
          <div className="flex items-baseline justify-between">
            <dt className="font-medium text-muted-foreground">{uncertain ? "예상 합계" : "합계"}</dt>
            <dd className="money text-body-lg text-ink">
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
            <span className="text-body-sm font-semibold">{left >= 0 ? "남은 돈" : "예산 초과"}</span>
            <Money value={Math.abs(left)} className="money text-price-lg" />
          </div>
        ) : (
          <div
            style={{ "--i": items.length + 3 } as CSSProperties}
            className={cn("receipt-line mt-4 flex items-center justify-between rounded-2xl px-4 py-3", left >= 0 ? "coin-gleam bg-gold-soft text-gold-ink" : "bg-pink-soft text-pink-deep")}
          >
            <span className="text-body-sm font-semibold">{left >= 0 ? "남은 돈" : "예산 초과"}</span>
            {/* 남은 돈은 영수증에서도 분명하게 (docs/33 §7) */}
            <Money value={Math.abs(left)} className="money text-price" />
          </div>
        )}

        {uncertain ? (
          <p className="mt-3 text-center text-caption text-muted-foreground">
            {estimated > 0 ? `≈ ${estimated}곳은 같은 동네 · 업종의 1인 평균가예요.` : ""}
            {unknown > 0 ? ` 가격을 모르는 ${unknown}곳은 합계에 넣지 못했어요.` : ""} 실제 금액은 조금 다를 수 있어요.
          </p>
        ) : null}
        {footer ? <div className="mt-4 text-center text-caption text-muted-foreground">{footer}</div> : null}
      </div>
    </div>
  );
}
