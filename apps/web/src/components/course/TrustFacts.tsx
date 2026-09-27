import { BadgeCheck, Camera, History, Landmark, Receipt, TrendingUp, type LucideIcon } from "lucide-react";
import type { StopTrust, TrustKind } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** 믿을 이유의 종류별 아이콘 (docs/59 #15) — 카드의 한 줄과 결정 시트가 같은 것을 쓴다 */
export const TRUST_ICON: Record<TrustKind, LucideIcon> = {
  designated: BadgeCheck,
  long_run: History,
  menu_price: Receipt,
  draw: Landmark,
  visited: TrendingUp,
  photos: Camera,
};

/**
 * 결정 시트 맨 위: 이 곳을 믿을 이유 전부, 강한 순서로 · 누가 말하는지와 함께.
 * 서버가 저장된 필드에서만 만든 것이라 여기서 덧붙이는 말은 없다 (별점 · "인기" 없음).
 */
export function TrustFacts({ trust, className }: { trust: StopTrust; className?: string }) {
  return (
    <section aria-label="믿을 이유" className={cn("grid gap-1.5 rounded-2xl bg-blue-soft px-3.5 py-3", className)}>
      <ul className="grid gap-1.5">
        {trust.facts.map((f, i) => {
          const Icon = TRUST_ICON[f.kind];
          return (
            <li key={`${f.kind}-${f.text}`} className="flex items-start gap-2 text-body-sm">
              <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-blue-deep" />
              <span className="min-w-0">
                <b className={cn("tabular text-ink", i === 0 ? "font-extrabold" : "font-bold")}>{f.text}</b>{" "}
                <span className="text-caption text-ink-2">· {f.source}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
