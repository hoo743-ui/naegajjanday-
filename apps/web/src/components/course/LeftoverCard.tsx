"use client";

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useAddStop, useSuggestions } from "@/lib/api/hooks";
import { distance, minutes, roleLabel, won } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";
import type { NearbyPin } from "./map-shared";

interface LeftoverCardProps {
  courseId: string;
  /** 남은 돈이 바뀌면(장소를 바꾸거나 넣으면) 권할 곳도 다시 찾는다 */
  budgetLeft: number;
  budget: number;
  /** 친구가 짠 코스(읽기 전용)에서는 권하기만 하고, 넣는 버튼은 없다 */
  editable: boolean;
  onAdded: (name: string, price: number) => void;
  /** 이름을 누르면 코스 지도에 띄운다 — 마지막 장소에서 어디쯤인지 먼저 보고 넣는다 */
  onShow?: (pin: Omit<NearbyPin, "n">) => void;
}

/**
 * 예산이 남았을 때: "이런 건 어때요?". 남은 돈은 자랑하고 끝낼 숫자가 아니라 권할 거리다.
 * 마지막 장소에서 걸어갈 수 있고, 남은 돈으로 되고, 그 시각에 여는 곳만 온다(서버가 확인한다).
 * 권할 곳이 없으면 아무것도 그리지 않는다.
 */
/** 이만큼(예산 대비) 남았는데 권할 곳이 없으면, 말없이 넘어가지 않고 그렇다고 말한다 */
const WORTH_SAYING = 0.4;

export function LeftoverCard({ courseId, budgetLeft, budget, editable, onAdded, onShow }: LeftoverCardProps) {
  const suggestions = useSuggestions(courseId, budgetLeft);
  const add = useAddStop(courseId);
  const items = suggestions.data?.items ?? [];
  if (items.length === 0) {
    if (!suggestions.isSuccess || budget <= 0 || budgetLeft / budget < WORTH_SAYING) return null;
    return (
      <p role="note" className="tabular border-l-2 border-line pl-3 text-body-sm text-ink-2">
        남은 돈으로 <b className="font-extrabold text-gold-ink">{won(budgetLeft)}</b>이 있어요. 이 시간에 마지막 장소에서 걸어갈 수 있는 거리에는 더 권할 만한 곳을 찾지 못했어요.
      </p>
    );
  }

  return (
    <section aria-labelledby="leftover-card" className="rule-section gap-3">
      <div>
        <h2 id="leftover-card" className="text-body font-extrabold text-ink">
          이런 건 어때요?
        </h2>
        <p className="tabular mt-0.5 text-body-sm text-ink-2">
          남은 돈으로 <b className="font-extrabold text-gold-ink">{won(budgetLeft)}</b>, 마지막 장소에서 걸어갈 수 있는 곳이에요.
        </p>
      </div>
      <ul className="grid gap-2">
        {items.map((item) => (
          <li key={item.place.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-line bg-white/70 p-3">
            <div className="min-w-0 flex-1">
              {onShow ? (
                <button
                  type="button"
                  onClick={() => onShow({ id: item.place.id, name: item.place.name, lat: item.place.lat, lng: item.place.lng, kind: `남은 돈으로 · 도보 ${minutes(item.walk_min)}` })}
                  className="block max-w-full truncate text-left text-body font-extrabold text-ink underline decoration-line underline-offset-4 hover:text-blue-deep"
                >
                  <span className="text-muted-foreground">{roleLabel(item.role)}</span> {item.place.name}
                </button>
              ) : (
                <p className="truncate text-body font-extrabold text-ink">
                  <span className="text-muted-foreground">{roleLabel(item.role)}</span> {item.place.name}
                </p>
              )}
              <p className="tabular text-caption text-muted-foreground">
                도보 {minutes(item.walk_min)} · {distance(item.distance_m)} · {item.line}
              </p>
            </div>
            <p className="tabular shrink-0 text-right text-body font-extrabold text-ink">
              {item.est_price === 0 ? "무료" : won(item.est_price)}
              {item.place.price_is_estimated && item.est_price > 0 ? <span className="block text-caption font-semibold text-gold-ink">평균가</span> : null}
            </p>
            {editable ? (
              <Button
                type="button"
                size="sm"
                variant="soft"
                disabled={add.isPending}
                aria-label={`${item.place.name} 코스에 넣기`}
                onClick={() =>
                  add.mutate(
                    { place_id: item.place.id },
                    {
                      onSuccess: () => {
                        track("suggestion_added", { course_id: courseId, role: item.role, price: item.est_price });
                        onAdded(item.place.name, item.est_price);
                      },
                    },
                  )
                }
              >
                <Plus aria-hidden /> 코스에 넣기
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {add.error ? (
        <p role="alert" className="text-body-sm font-semibold text-pink-deep">
          {add.error.detail ?? mascotCopyForError(add.error).description}
        </p>
      ) : null}
    </section>
  );
}
