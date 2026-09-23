import { Coffee, Footprints, Landmark, Moon, PartyPopper, Utensils, Wine, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * 사진이 없을 때의 마지막 단계 (docs/39): 실제 사진 → 같은 업종의 예시 사진("예시") → **이것**.
 * 빈 회색 상자가 아니라 우리 종이 위의 작은 그림 — 따뜻한 종이 · 옅은 지도 선 · 영수증 점선 · 역할 아이콘.
 * 사진인 척하지 않는다: 그림에는 사진 출처가 없고, 화면 낭독기에는 읽히지 않는다(장소 이름은 카드가 말한다).
 */
const KIND: Record<string, { icon: LucideIcon; label: string; tint: string }> = {
  MEAL: { icon: Utensils, label: "식사", tint: "#f6e3d4" },
  CAFE: { icon: Coffee, label: "카페", tint: "#efe4d2" },
  WALK: { icon: Footprints, label: "산책", tint: "#e3ecdf" },
  ACTIVITY: { icon: PartyPopper, label: "놀거리", tint: "#f3e0dc" },
  SIGHT: { icon: Landmark, label: "볼거리", tint: "#e6e6ef" },
  BAR: { icon: Wine, label: "한잔", tint: "#eadbe3" },
  NIGHT: { icon: Moon, label: "야경", tint: "#dfe3ee" },
};

/** 역할 코드(MEAL · CAFE …)나 둘러보기 종류(attraction · park · festival …)를 그림 종류로 */
export function placeholderKind(code: string | null | undefined): keyof typeof KIND {
  const c = (code ?? "").toUpperCase();
  if (c in KIND) return c as keyof typeof KIND;
  if (/CAFE|DESSERT/.test(c)) return "CAFE";
  if (/MEAL|FOOD|RESTAURANT/.test(c)) return "MEAL";
  if (/PARK|WALK|NATURE|TRAIL/.test(c)) return "WALK";
  if (/BAR|PUB|DRINK/.test(c)) return "BAR";
  if (/NIGHT|VIEW/.test(c)) return "NIGHT";
  if (/FESTIVAL|EVENT|PLAY|ACTIVITY|CULTURE|EXHIBIT|SHOW/.test(c)) return "ACTIVITY";
  return "SIGHT";
}

interface PlacePlaceholderProps {
  kind: string | null | undefined;
  /** 작은 썸네일(72~80px)은 아이콘만, 큰 카드는 역할 이름까지 */
  size?: "sm" | "lg";
  className?: string;
}

export function PlacePlaceholder({ kind, size = "sm", className }: PlacePlaceholderProps) {
  const k = KIND[placeholderKind(kind)]!;
  const Icon = k.icon;
  return (
    <span aria-hidden className={cn("place-ph relative grid place-items-center overflow-hidden", className)} style={{ backgroundColor: k.tint }}>
      {/* 옅은 동네 지도 선 + 영수증 점선 */}
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full" fill="none" stroke="#10192e" strokeLinecap="round">
        <path d="M-5 30 C25 22 45 40 70 34 S95 20 105 26" strokeWidth="1.6" opacity=".1" />
        <path d="M22 -5 C30 30 18 60 34 105" strokeWidth="1.2" opacity=".08" />
        <path d="M-5 78 L105 72" strokeWidth="1" opacity=".16" strokeDasharray="2 3" />
        <circle cx="70" cy="34" r="3" strokeWidth="1.2" opacity=".14" />
      </svg>
      <span className="relative grid justify-items-center gap-1 text-ink/55">
        <Icon className={size === "lg" ? "size-9" : "size-6"} strokeWidth={1.6} />
        {size === "lg" ? <span className="text-caption font-semibold text-ink/60">{k.label}</span> : null}
      </span>
    </span>
  );
}
