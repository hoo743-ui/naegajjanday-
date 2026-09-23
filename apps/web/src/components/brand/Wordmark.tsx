import { cn } from "@/lib/utils";

interface WordmarkProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

/**
 * 워드마크 "내가 · 짠 · 데이" (2026-09-23): 이름의 세 조각이 서비스의 세 단계다.
 *   내가 — 사용자가 정하는 조건 → 손으로 고른 조건 칩(얇은 잉크 테두리 라벨)
 *   짠   — 예산 안에서 조합이 끝나는 순간 → 토마토 도장(살짝 기울어 찍힘)
 *   데이 — 하루 전체 → 아래로 하루 타임라인(점 셋과 점선)이 이어진다
 * 셋이 따로 놀지 않게 같은 서체(SUIT 800) · 같은 기준선 위에 붙여 한 낱말로 읽힌다.
 * 화면 낭독기에는 "내가짠데이" 한 낱말로 읽힌다.
 */
export function Wordmark({ size = "md", className }: WordmarkProps) {
  return (
    <span className={cn("wordmark", `wordmark-${size}`, className)} role="img" aria-label="내가짠데이">
      <span aria-hidden className="wordmark-nae">내가</span>
      <span aria-hidden className="wordmark-jjan">짠</span>
      <span aria-hidden className="wordmark-day">
        데이
        <svg viewBox="0 0 40 6" preserveAspectRatio="none" className="wordmark-line">
          <line x1="3" y1="3" x2="37" y2="3" />
          <circle cx="3" cy="3" r="2.2" />
          <circle cx="20" cy="3" r="2.2" />
          <circle cx="37" cy="3" r="2.2" />
        </svg>
      </span>
    </span>
  );
}
