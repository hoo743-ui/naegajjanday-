import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: ReactNode;
  /** 값 아래 보조 설명 (목표치, 비교 등) */
  hint?: ReactNode;
  icon?: LucideIcon;
  /** 목표 대비 상태. good=목표 달성, warn=주의 */
  tone?: "default" | "good" | "warn";
  loading?: boolean;
  className?: string;
}

const TONE = {
  default: "bg-blue-soft text-blue-deep",
  good: "bg-success-soft text-success",
  warn: "bg-gold-soft text-gold-ink",
} as const;

export function StatCard({ label, value, hint, icon: Icon, tone = "default", loading = false, className }: StatCardProps) {
  return (
    <div className={cn("rounded-card border bg-white p-5 shadow-soft", className)}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-body-sm font-semibold text-muted-foreground">{label}</p>
        {Icon ? (
          <span className={cn("grid size-9 shrink-0 place-items-center rounded-xl", TONE[tone])}>
            <Icon className="size-[18px]" aria-hidden />
          </span>
        ) : null}
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-9 w-28 rounded-lg" />
      ) : (
        <p className="money mt-1 text-price text-ink">{value}</p>
      )}
      {hint ? <p className="mt-1 text-body-sm font-semibold text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
