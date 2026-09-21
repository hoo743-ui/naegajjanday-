"use client";

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useAddStop, useSuggestions } from "@/lib/api/hooks";
import { distance, minutes, roleLabel, won } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";

interface LeftoverCardProps {
  courseId: string;
  /** 남은 돈이 바뀌면(장소를 바꾸거나 넣으면) 권할 곳도 다시 찾는다 */
  budgetLeft: number;
  /** 친구가 짠 코스(읽기 전용)에서는 권하기만 하고, 넣는 버튼은 없다 */
  editable: boolean;
  onAdded: (name: string, price: number) => void;
}

/**
 * 예산이 남았을 때: "이런 건 어때요?". 남은 돈은 자랑하고 끝낼 숫자가 아니라 권할 거리다.
 * 마지막 장소에서 걸어갈 수 있고, 남은 돈으로 되고, 그 시각에 여는 곳만 온다(서버가 확인한다).
 * 권할 곳이 없으면 아무것도 그리지 않는다.
 */
export function LeftoverCard({ courseId, budgetLeft, editable, onAdded }: LeftoverCardProps) {
  const suggestions = useSuggestions(courseId, budgetLeft);
  const add = useAddStop(courseId);
  const items = suggestions.data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <section aria-labelledby="leftover-card" className="grid gap-3 rounded-card bg-white p-5 shadow-soft">
      <div>
        <h2 id="leftover-card" className="text-[15px] font-extrabold text-ink">
          이런 건 어때요?
        </h2>
        <p className="tabular mt-0.5 text-[13px] text-ink-2">
          남은 돈으로 <b className="font-extrabold text-gold-ink">{won(budgetLeft)}</b>, 마지막 장소에서 걸어갈 수 있는 곳이에요.
        </p>
      </div>
      <ul className="grid gap-2">
        {items.map((item) => (
          <li key={item.place.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-line p-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-[14.5px] font-extrabold text-ink">
                <span className="text-muted-foreground">{roleLabel(item.role)}</span> {item.place.name}
              </p>
              <p className="tabular text-[12.5px] text-muted-foreground">
                도보 {minutes(item.walk_min)} · {distance(item.distance_m)} · {item.line}
              </p>
            </div>
            <p className="tabular shrink-0 text-right text-[14.5px] font-extrabold text-ink">
              {item.est_price === 0 ? "무료" : won(item.est_price)}
              {item.place.price_is_estimated && item.est_price > 0 ? <span className="block text-[11px] font-bold text-gold-ink">평균가</span> : null}
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
        <p role="alert" className="text-[13px] font-bold text-pink-deep">
          {add.error.detail ?? mascotCopyForError(add.error).description}
        </p>
      ) : null}
    </section>
  );
}
