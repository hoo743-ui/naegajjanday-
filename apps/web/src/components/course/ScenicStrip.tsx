"use client";

import { PlacePhoto } from "@/components/brand/PlacePhoto";
import { useScenery } from "@/lib/api/hooks";
import type { NearbyPin } from "./map-shared";

/**
 * 오늘 지나갈 길을 사진으로 (2026-09-26 창업자: 코스길 주변의 사진을 결과로 보여 주면 더 각인된다).
 * 코스 장소와 길가 볼거리의 실제 사진만, 걷는 순서대로. 분위기 이미지는 쓰지 않는다 — "그 길"의 사진이 아니니까.
 * 두 장이 안 되면 띠를 그리지 않는다. 누르면 지도에서 그 자리를 보여 준다.
 */
export function ScenicStrip({ courseId, stops, onShow }: { courseId: string; stops: string; onShow?: (pin: Omit<NearbyPin, "n">) => void }) {
  const scenery = useScenery(courseId, stops);
  const items = scenery.data?.items ?? [];
  if (items.length < 2) return null;
  return (
    <section aria-label="오늘 지나갈 길" className="grid gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-h3 font-bold text-ink">오늘 지나갈 길</h2>
        <span className="shrink-0 text-caption text-muted-foreground">걷는 순서대로</span>
      </div>
      <ul className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-1 [scrollbar-width:none]">
        {items.map((item) => (
          <li key={item.place_id} className="w-[min(15rem,72vw)] shrink-0 snap-start">
            <button
              type="button"
              onClick={() => onShow?.({ id: item.place_id, name: item.name, lat: item.lat, lng: item.lng, kind: item.caption })}
              className="grid w-full gap-1.5 text-left"
            >
              <PlacePhoto image={item.image} size="lg" sizes="240px" className="block aspect-[4/3] w-full rounded-2xl photo-edge" />
              <span className="grid gap-0.5 px-0.5">
                <span className={item.is_stop ? "text-caption font-semibold text-blue-deep" : "text-caption text-muted-foreground"}>{item.caption}</span>
                <span className="truncate text-body-sm font-semibold text-ink">{item.name}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
