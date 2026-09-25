"use client";

import { useState } from "react";
import { MapPin, Plus, ShoppingBag, X } from "lucide-react";
import type { Errand } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { SpotSearch } from "./SpotSearch";

/** 그곳에서 보낼 시간 */
export const ERRAND_MINUTES = [
  { minutes: 30, label: "30분" },
  { minutes: 60, label: "1시간" },
  { minutes: 120, label: "2시간" },
] as const;

export const ERRAND_WHEN = [
  { value: "before", label: "먼저 들르고 시작" },
  { value: "after", label: "끝나고 들르기" },
] as const;

/** 코스 조건 칩 · 요약 한 줄: "먼저 애플 가로수길" · "끝나고 애플 가로수길" */
export function errandLabel(e: Pick<Errand, "name" | "when">): string {
  return `${e.when === "after" ? "끝나고" : "먼저"} ${e.name}`;
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      onClick={onClick}
      className={cn("min-h-11 rounded-full border px-3.5 text-body-sm transition-colors", on ? "border-tomato bg-tomato font-bold text-white" : "border-line bg-white font-medium text-ink-2 hover:border-tomato")}
    >
      {children}
    </button>
  );
}

interface ErrandEditorProps {
  value: Errand | null;
  onChange: (next: Errand | null) => void;
  /** "여기 근처에서 놀래요": 들를 곳이 곧 놀 곳 — 지역을 그 주변으로 바꾼다 (없으면 버튼도 없다) */
  onPlayNear?: (errand: Errand) => void;
  /** 들를 곳이 이미 하루의 중심(지역 대신)이면: 빼기 대신 한 줄 안내 */
  isCentre?: boolean;
}

/**
 * 가는 김에 (docs/51 B1 · 창업자 2026-09-26): 꼭 들를 곳은 노는 곳을 정하는 방법이 아니라 코스의 한 옵션이다.
 * 애플 가로수길에 들렀다가 성수에서 노는 하루처럼 — 먼저 들를지 끝나고 들를지, 거기서 얼마나 있을지만 묻는다.
 */
export function ErrandEditor({ value, onChange, onPlayNear, isCentre }: ErrandEditorProps) {
  const [open, setOpen] = useState(false);

  if (!value) {
    return open ? (
      <div className="grid gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-body-sm text-ink-2">어디에 꼭 들러야 해요?</p>
          <button type="button" onClick={() => setOpen(false)} className="inline-flex min-h-11 shrink-0 items-center px-2 text-body-sm font-semibold text-ink-2 hover:text-ink">
            닫기
          </button>
        </div>
        <SpotSearch
          onPick={(sp) => {
            onChange({ name: sp.name, lat: sp.lat, lng: sp.lng, place_id: sp.place_id, minutes: 30, when: "before" });
            setOpen(false);
          }}
        />
      </div>
    ) : (
      <button type="button" aria-expanded={false} onClick={() => setOpen(true)} className="inline-flex min-h-11 w-fit items-center gap-2 rounded-full border-[1.5px] border-line px-4 text-body font-semibold text-ink transition-colors hover:border-ink-2">
        <Plus aria-hidden className="size-4 text-tomato-deep" />
        꼭 들를 곳이 있어요
      </button>
    );
  }

  const when = value.when ?? "before";
  return (
    <div className="grid min-w-0 gap-3 rounded-lg border-[1.5px] border-tomato bg-tomato-soft p-4">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-white text-tomato-deep">
          <ShoppingBag aria-hidden className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-body font-semibold text-ink">{value.name}</b>
          <span className="block text-body-sm text-ink-2">{isCentre ? "여기 근처에서 놀아요" : when === "after" ? "코스를 마치고 들러요" : "여기 먼저 들르고 코스를 시작해요"}</span>
        </span>
        {isCentre ? null : (
          <button type="button" onClick={() => onChange(null)} aria-label={`${value.name} 빼기`} className="grid size-11 shrink-0 place-items-center rounded-full bg-white text-ink-2 shadow-soft hover:text-ink">
            <X aria-hidden className="size-4" />
          </button>
        )}
      </div>
      {isCentre ? null : (
        <div role="radiogroup" aria-label="언제 들러요" className="flex flex-wrap gap-2">
          {ERRAND_WHEN.map((w) => (
            <Chip key={w.value} on={when === w.value} onClick={() => onChange({ ...value, when: w.value })}>
              {w.label}
            </Chip>
          ))}
        </div>
      )}
      <div role="radiogroup" aria-label="거기서 얼마나 있어요" className="flex flex-wrap items-center gap-2">
        <span className="text-body-sm font-semibold text-ink-2">거기서</span>
        {ERRAND_MINUTES.map((m) => (
          <Chip key={m.minutes} on={value.minutes === m.minutes} onClick={() => onChange({ ...value, minutes: m.minutes })}>
            {m.label}
          </Chip>
        ))}
      </div>
      {onPlayNear && !isCentre ? (
        <button type="button" onClick={() => onPlayNear(value)} className="inline-flex min-h-11 w-fit items-center gap-1.5 rounded-full bg-white px-3.5 text-body-sm font-semibold text-ink-2 shadow-soft hover:text-ink">
          <MapPin aria-hidden className="size-4 text-tomato-deep" />
          여기 근처에서 놀래요
        </button>
      ) : null}
    </div>
  );
}
