import { cn } from "@/lib/utils";

type Tone = "neutral" | "blue" | "gold" | "green" | "pink";

const TONE: Record<Tone, string> = {
  neutral: "bg-[#EEF1F7] text-ink-2",
  blue: "bg-blue-soft text-blue-deep",
  gold: "bg-gold-soft text-gold-ink",
  green: "bg-success-soft text-success",
  pink: "bg-pink-soft text-pink-deep",
};

/** API enum 값 → 표시 라벨·색. 모르는 값이 와도 그대로 보여준다. */
const STATUS: Record<string, { label: string; tone: Tone; pulse?: boolean }> = {
  // 장소
  pending: { label: "승인 대기", tone: "gold" },
  approved: { label: "승인됨", tone: "green" },
  rejected: { label: "반려", tone: "pink" },
  hidden: { label: "숨김", tone: "neutral" },
  closed: { label: "폐업", tone: "neutral" },
  // 지역
  draft: { label: "초안", tone: "neutral" },
  collecting: { label: "수집 중", tone: "blue", pulse: true },
  ready: { label: "준비됨", tone: "gold" },
  active: { label: "활성", tone: "green" },
  failed: { label: "실패", tone: "pink" },
  paused: { label: "일시 중지", tone: "neutral" },
  // 수집 잡
  queued: { label: "대기", tone: "neutral" },
  running: { label: "진행 중", tone: "blue", pulse: true },
  succeeded: { label: "완료", tone: "green" },
  // 이벤트
  published: { label: "게시 중", tone: "green" },
  ended: { label: "종료", tone: "neutral" },
  // 시스템
  ok: { label: "정상", tone: "green" },
  degraded: { label: "느려짐", tone: "gold" },
  down: { label: "중단", tone: "pink" },
  disabled: { label: "꺼 둠", tone: "neutral" },
};

/** 배지 없이 글자만 필요할 때 (수정 이력의 상태 값 등) */
export const statusLabel = (status: string): string => STATUS[status]?.label ?? status;

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const info = STATUS[status] ?? { label: status, tone: "neutral" as const };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-caption font-semibold whitespace-nowrap",
        TONE[info.tone],
        className,
      )}
    >
      {info.pulse ? <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-current" /> : null}
      {info.label}
    </span>
  );
}
