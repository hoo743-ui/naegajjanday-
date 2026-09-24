import type { ReactNode } from "react";
import { Landmark, Moon, Wine, type LucideIcon } from "lucide-react";
import { toPlaceholderKind } from "@/lib/place-image";
import type { PlaceholderKind } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * 사진이 없을 때의 마지막 단계 (docs/39 · docs/43): 실제 사진 → 분위기 이미지 → **이것**.
 * 빈 회색 상자가 아니라 우리 종이 위의 작은 그림. 식사 · 카페 · 산책 · 놀거리는 저마다 장면이 다르다
 * (그릇과 젓가락 · 김 나는 잔 · 굽은 산책길 · 입장권). 선은 먹색 한 가지, 바탕은 종류마다 다른 종이색.
 * 사진인 척하지 않는다: 출처가 없고, 화면 낭독기에는 읽히지 않는다(장소 이름은 카드가 말한다).
 */
const INK = "#10192e";

/** 네 장면: viewBox 100×100, 가운데 기준으로 잘려도(slice) 알아볼 수 있게 가운데 60% 안에 그린다 */
const SCENES: Partial<Record<PlaceholderKind, ReactNode>> = {
  meal: (
    <g stroke={INK} strokeLinecap="round" strokeLinejoin="round">
      {/* 김 */}
      <path d="M44 30c-3-4 3-6 0-10M52 28c-3-4 3-6 0-10M60 30c-3-4 3-6 0-10" strokeWidth="1.6" opacity=".35" fill="none" />
      {/* 그릇 */}
      <path d="M28 44h48c0 14-10 24-24 24S28 58 28 44z" fill="#fff" fillOpacity=".75" strokeWidth="1.6" opacity=".9" strokeOpacity=".4" />
      <path d="M44 68h16" strokeWidth="1.6" opacity=".4" />
      <path d="M34 44c4-5 10-7 18-7s14 2 18 7" fill="none" strokeWidth="1.3" opacity=".3" />
      {/* 젓가락 · 숟가락 */}
      <path d="M72 76l14-40M77 78l14-40" strokeWidth="1.8" opacity=".4" />
      <ellipse cx="20" cy="56" rx="4.5" ry="6.5" fill="#fff" fillOpacity=".7" strokeWidth="1.4" strokeOpacity=".4" />
      <path d="M20 63v18" strokeWidth="1.8" opacity=".4" />
    </g>
  ),
  cafe: (
    <g stroke={INK} strokeLinecap="round" strokeLinejoin="round">
      <path d="M42 28c-3-4 3-6 0-10M51 26c-3-4 3-6 0-10M60 28c-3-4 3-6 0-10" strokeWidth="1.6" opacity=".35" fill="none" />
      {/* 받침 · 잔 · 손잡이 */}
      <ellipse cx="50" cy="72" rx="28" ry="5" fill="#fff" fillOpacity=".6" strokeWidth="1.3" strokeOpacity=".3" />
      <path d="M33 40h34v12c0 10-8 18-17 18s-17-8-17-18z" fill="#fff" fillOpacity=".8" strokeWidth="1.6" strokeOpacity=".4" />
      <path d="M67 45c7 0 9 3 9 6s-3 7-10 7" fill="none" strokeWidth="1.6" opacity=".4" />
      <ellipse cx="50" cy="40" rx="17" ry="3" fill="#b88a60" fillOpacity=".35" strokeWidth="1.2" strokeOpacity=".35" />
      {/* 원두 */}
      <g opacity=".3" strokeWidth="1.2">
        <ellipse cx="18" cy="24" rx="4" ry="5.5" transform="rotate(-30 18 24)" fill="none" />
        <path d="M16 20c2 3 2 5 4 8" fill="none" />
        <ellipse cx="84" cy="82" rx="4" ry="5.5" transform="rotate(25 84 82)" fill="none" />
        <path d="M82 78c2 3 2 5 4 8" fill="none" />
      </g>
    </g>
  ),
  walk: (
    <g stroke={INK} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="76" cy="22" r="6" fill="#fff" fillOpacity=".7" strokeWidth="1.3" strokeOpacity=".3" />
      <path d="M-5 54c20-10 38-6 55-1s32 2 55-6" fill="none" strokeWidth="1.3" opacity=".25" />
      {/* 멀어질수록 좁아지는 길 + 가운데 점선(걸음) */}
      <path d="M26 105c10-18 26-30 25-50h6c3 20 14 32 22 50z" fill="#fff" fillOpacity=".7" strokeWidth="1.3" strokeOpacity=".3" />
      <path d="M52 104c2-16 3-32 2-48" fill="none" strokeWidth="1.6" strokeDasharray="1 5" opacity=".45" />
      {/* 나무 둘 */}
      <circle cx="22" cy="42" r="9" fill="#a9c49e" fillOpacity=".7" strokeWidth="1.2" strokeOpacity=".3" />
      <path d="M22 51v10" strokeWidth="1.6" opacity=".35" />
      <circle cx="82" cy="46" r="6.5" fill="#a9c49e" fillOpacity=".7" strokeWidth="1.2" strokeOpacity=".3" />
      <path d="M82 52.5v7" strokeWidth="1.6" opacity=".35" />
    </g>
  ),
  activity: (
    <g stroke={INK} strokeLinecap="round" strokeLinejoin="round">
      {/* 입장권: 양옆이 파인 표 + 절취선 + 별 */}
      <g transform="rotate(-10 50 52)">
        <path
          d="M22 36h56v10a6 6 0 0 0 0 12v10H22V58a6 6 0 0 0 0-12z"
          fill="#fff"
          fillOpacity=".8"
          strokeWidth="1.5"
          strokeOpacity=".4"
        />
        <path d="M63 38v28" strokeWidth="1.4" strokeDasharray="2 3" opacity=".4" />
        <path d="M42 43l2.6 5.4 5.9.8-4.3 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z" fill={INK} fillOpacity=".18" strokeWidth="1.2" strokeOpacity=".4" />
      </g>
      {/* 색종이 */}
      <g strokeWidth="1.6" opacity=".35" fill="none">
        <path d="M18 22l5 3M82 18l-3 5M86 76l-5-2M16 80l4-4M50 16v5M30 88l3-4" />
        <circle cx="72" cy="30" r="1.8" />
        <circle cx="26" cy="66" r="1.8" />
      </g>
    </g>
  ),
};

/** 장면이 없는 종류는 예전처럼 옅은 지도 선 + 아이콘 */
const ICON: Partial<Record<PlaceholderKind, LucideIcon>> = { sight: Landmark, bar: Wine, night: Moon };

const LOOK: Record<PlaceholderKind, { label: string; tint: string }> = {
  meal: { label: "식사", tint: "#f6e3d4" },
  cafe: { label: "카페", tint: "#efe4d2" },
  walk: { label: "산책", tint: "#e3ecdf" },
  activity: { label: "놀거리", tint: "#f3e0dc" },
  sight: { label: "볼거리", tint: "#e6e6ef" },
  bar: { label: "한잔", tint: "#eadbe3" },
  night: { label: "야경", tint: "#dfe3ee" },
};

/** 역할 코드(MEAL · CAFE …) · 둘러보기 유형(park · festival …) · 업종 코드 · 서버의 placeholder_kind → 그림 종류 */
export function placeholderKind(code: string | null | undefined): PlaceholderKind {
  return toPlaceholderKind(code);
}

interface PlacePlaceholderProps {
  kind: string | null | undefined;
  /** 작은 썸네일(72~80px)은 그림만, 큰 카드는 종류 이름까지 */
  size?: "sm" | "lg";
  className?: string;
}

export function PlacePlaceholder({ kind, size = "sm", className }: PlacePlaceholderProps) {
  const k = placeholderKind(kind);
  const look = LOOK[k];
  const scene = SCENES[k];
  const Icon = ICON[k] ?? Landmark;
  return (
    <span aria-hidden data-placeholder={k} className={cn("place-ph relative grid place-items-center overflow-hidden", className)} style={{ backgroundColor: look.tint }}>
      {/* 옅은 동네 지도 선 + 영수증 점선: 모든 그림에 공통인 우리 종이 */}
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full" fill="none" stroke={INK} strokeLinecap="round">
        <path d="M-5 30 C25 22 45 40 70 34 S95 20 105 26" strokeWidth="1.6" opacity=".07" />
        <path d="M-5 90 L105 86" strokeWidth="1" opacity=".14" strokeDasharray="2 3" />
      </svg>
      {scene ? (
        <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" className={cn("relative", size === "lg" ? "h-[70%] max-h-40 w-auto" : "size-full")}>
          {scene}
        </svg>
      ) : (
        <Icon className={cn("relative text-ink/55", size === "lg" ? "size-9" : "size-6")} strokeWidth={1.6} />
      )}
      {size === "lg" ? <span className="absolute bottom-2.5 left-3 text-caption font-semibold text-ink/60">{look.label}</span> : null}
    </span>
  );
}
