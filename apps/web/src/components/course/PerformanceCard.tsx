"use client";

import { Ticket } from "lucide-react";
import { useFeatures, usePerformances } from "@/lib/api/hooks";
import { distance } from "@/lib/format";

interface PerformanceCardProps {
  at: { lat: number; lng: number };
  startAt: string;
  durationMin: number;
}

/**
 * 고른 시간대에 근처에서 **실제로 하는** 공연 (KOPIS 공연예술통합전산망).
 * 키가 없는 환경이면 아예 요청하지 않고, 맞는 공연이 없으면 아무것도 그리지 않는다 — 없는 것을 있는 것처럼 말하지 않는다.
 */
export function PerformanceCard({ at, startAt, durationMin }: PerformanceCardProps) {
  const enabled = useFeatures().data?.performances === true;
  const shows = usePerformances(enabled ? { ...at, start_at: startAt, duration_min: durationMin } : null);
  if (!enabled || !shows.data?.available || shows.data.items.length === 0) return null;

  return (
    <section aria-labelledby="performance-card" className="grid gap-3 rounded-card bg-white p-5 shadow-soft">
      <h2 id="performance-card" className="flex items-center gap-2 text-[15px] font-extrabold text-ink">
        <Ticket aria-hidden className="size-4 text-blue-deep" />이 시간에 근처에서 하는 공연
      </h2>
      <ul className="grid gap-2">
        {shows.data.items.slice(0, 5).map((show) => (
          <li key={show.id} className="rounded-2xl border border-line p-3">
            <a href={show.detail_url ?? undefined} target="_blank" rel="noreferrer" className="block text-[14.5px] font-extrabold text-ink hover:text-blue-deep">
              {show.title}
            </a>
            <p className="tabular mt-0.5 text-[12.5px] text-muted-foreground">
              {show.venue.name} · {distance(show.venue.distance_m)} · {show.show_times.join(", ")} 시작
              {show.runtime_min ? ` · ${show.runtime_min}분` : ""}
            </p>
            {show.price_text ? <p className="mt-0.5 text-[12.5px] text-ink-2">{show.price_text}</p> : null}
          </li>
        ))}
      </ul>
      <p className="text-[11.5px] leading-relaxed text-muted-foreground">
        공연 요금은 코스 예산에 들어 있지 않아요. 남은 좌석은 예매처에서 확인해 주세요. {shows.data.attribution}
      </p>
    </section>
  );
}
