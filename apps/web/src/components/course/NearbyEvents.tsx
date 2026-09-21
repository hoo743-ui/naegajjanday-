"use client";

import Link from "next/link";
import { PartyPopper } from "lucide-react";
import { track } from "@/lib/analytics";
import type { NearbyEvent } from "@/lib/api/types";
import { dateShort, daysUntil, distance, toKstIso } from "@/lib/format";

/** events 는 코스 날짜 기준으로 온다. startAt 은 그 코스의 출발 시각(ISO). */
export function NearbyEvents({ events: all, region, startAt }: { events: NearbyEvent[]; region?: string; startAt?: string }) {
  const today = toKstIso(new Date()).slice(0, 10);
  const start = startAt ? new Date(startAt) : null;
  const courseDay = start && !Number.isNaN(start.getTime()) ? toKstIso(start).slice(0, 10) : today;
  const upcoming = courseDay > today;
  // 며칠 뒤에 다시 연 링크에서, 이미 끝난 행사를 "열리고 있다"고 하지 않는다
  const events = all.filter((event) => event.ends_on >= today);
  return (
    <section aria-labelledby="nearby-events" className="rounded-card bg-white p-5 shadow-soft">
      <h2 id="nearby-events" className="flex items-center gap-2 text-base font-extrabold">
        <PartyPopper aria-hidden className="size-5 text-pink-deep" />
        {upcoming ? "그날 근처에서 열려요" : "근처에서 지금 열리고 있어요"}
      </h2>
      {events.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">{upcoming ? "그날은" : "오늘은"} 근처에 열리는 행사가 없어요. 코스에만 집중해도 충분해요.</p>
      ) : (
        <ul className="no-scrollbar -mx-5 mt-3 flex snap-x gap-3 overflow-x-auto px-5 pb-1">
          {events.map((event) => {
            const left = daysUntil(event.ends_on);
            return (
              <li key={event.id} className="w-[220px] shrink-0 snap-start">
                <Link
                  href={`/explore?type=festival${region ? `&region=${encodeURIComponent(region)}` : ""}`}
                  onClick={() => track("event_clicked", { event_id: event.id, from: "course" })}
                  className="bg-grad-soft block h-full rounded-2xl p-4 transition-transform duration-200 hover:-translate-y-0.5"
                >
                  <span className="flex flex-wrap gap-1.5 text-[11px] font-extrabold">
                    <span className={event.is_free ? "rounded-full bg-success-soft px-2 py-0.5 text-success" : "rounded-full bg-white px-2 py-0.5 text-ink-2"}>{event.is_free ? "무료" : "유료"}</span>
                    <span className="tabular rounded-full bg-white px-2 py-0.5 text-pink-deep">{left <= 0 ? "오늘까지" : `D-${left}`}</span>
                  </span>
                  <b className="mt-2 line-clamp-2 block text-[15px] leading-snug font-extrabold tracking-tight">{event.title}</b>
                  <span className="tabular mt-1 block text-xs font-bold text-ink-2">
                    {distance(event.distance_m)} · {dateShort(event.ends_on)}까지
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
