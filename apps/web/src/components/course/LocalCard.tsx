"use client";

import { MapPin, Sparkles } from "lucide-react";
import { FOCUS_OFF, type LocalSignature } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface LocalCardProps {
  local: LocalSignature;
  /** 이 코스가 실제로 중심에 둔 명물 (없으면 null) */
  focus?: string | null;
  /** 명물을 누르면 그 명물을 넣어 다시 짠다. 없으면(남의 코스 등) 읽기 전용 */
  onPick?: (focus: string) => void;
  busy?: boolean;
}

const kakaoSearch = (query: string) => `https://map.kakao.com/link/search/${encodeURIComponent(query)}`;

/**
 * "이 동네는요": 이 동네가 무엇으로 알려져 있는지 먼저 말해 준다.
 * 사람이 쓴 소개글이 아니라 간판 통계다 → 문구도 "유명하대요"가 아니라 셀 수 있는 사실("간판 N곳 · 전국의 M배")로 쓴다.
 * 명물을 누르면 같은 예산으로 그 명물을 넣은 코스를 다시 짠다 — 추천을 받기만 하는 게 아니라 고를 수 있어야 한다.
 */
export function LocalCard({ local, focus, onPick, busy }: LocalCardProps) {
  if (local.specialties.length === 0 && local.sights.length === 0) return null;
  return (
    <section aria-labelledby="local-card" className="rule-section gap-3.5">
      <h2 id="local-card" className="flex items-center gap-2 text-body font-extrabold text-ink">
        <Sparkles aria-hidden className="size-4 text-blue-deep" />
        {local.region}, 이런 동네예요
      </h2>

      {local.specialties.length > 0 ? (
        <div className="grid gap-2">
          <p className="text-body-sm text-ink-2">
            간판에 유독 많이 걸린 말이에요. {onPick ? "누르면 같은 예산으로 그걸 넣어 다시 짜 드려요." : ""}
          </p>
          <ul className="flex flex-wrap gap-2">
            {local.specialties.map((s) => {
              const on = s.word === focus;
              const label = (
                <>
                  <b className="font-extrabold">{s.word}</b>
                  <span className={cn("tabular text-caption", on ? "text-white/85" : "text-muted-foreground")}>
                    {s.count}곳 · 전국의 {Math.round(s.lift)}배
                  </span>
                </>
              );
              const shape = cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-body-sm",
                on ? "border-blue-deep bg-blue-deep text-white" : "border-line bg-white text-ink",
              );
              return (
                <li key={s.word}>
                  {onPick ? (
                    <button type="button" disabled={busy} aria-pressed={on} onClick={() => onPick(s.word)} className={cn(shape, !on && "hover:border-blue-deep hover:bg-blue-soft")}>
                      {label}
                    </button>
                  ) : (
                    <span className={shape}>{label}</span>
                  )}
                </li>
              );
            })}
          </ul>
          {focus ? (
            <p className="text-body-sm font-semibold text-blue-deep">
              이 코스에는 &lsquo;{focus}&rsquo; 집을 한 곳 넣었어요.
              {onPick ? (
                <button type="button" disabled={busy} onClick={() => onPick(FOCUS_OFF)} className="ml-2 font-semibold text-muted-foreground underline underline-offset-2 hover:text-ink">
                  빼고 다시 짜기
                </button>
              ) : null}
            </p>
          ) : null}
        </div>
      ) : null}

      {local.sights.length > 0 ? (
        <div className="grid gap-2">
          <p className="text-body-sm text-ink-2">사람들이 보러 오는 곳</p>
          <ul className="flex flex-wrap gap-x-3 gap-y-1.5">
            {local.sights.map((s) => (
              <li key={s.name}>
                <a href={kakaoSearch(s.name)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-body-sm font-semibold text-ink underline decoration-line underline-offset-4 hover:text-blue-deep">
                  <MapPin aria-hidden className="size-3.5 text-blue-deep" />
                  {s.name}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
