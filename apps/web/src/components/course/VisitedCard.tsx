"use client";

import { useState } from "react";
import { Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useCourseFeedback } from "@/lib/api/hooks";
import { mascotCopyForError } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";

const STARS = [1, 2, 3, 4, 5] as const;

/**
 * 저장한 코스를 다녀온 뒤에 남기는 기록. 별점 하나면 된다.
 * 이 기록이 ‘내 코스’의 "다녀옴" 표시가 되고, 다음 추천이 내 취향을 배우는 유일한 길이다.
 */
export function VisitedCard({ courseId, visited }: { courseId: string; visited: boolean }) {
  const feedback = useCourseFeedback(courseId);
  const [rating, setRating] = useState(0);

  if (visited || feedback.isSuccess) {
    return (
      <p role="status" className="rounded-card bg-success-soft px-5 py-4 text-body-sm font-semibold text-success">
        다녀온 코스로 기록했어요. 다음 코스를 짤 때 참고할게요.
      </p>
    );
  }

  return (
    <section aria-labelledby="visited-card" className="rule-section gap-3">
      <h2 id="visited-card" className="text-body font-extrabold text-ink">
        다녀오셨나요?
      </h2>
      <p className="text-body-sm text-ink-2">별점을 남기면 ‘내 코스’에 다녀옴으로 표시하고, 다음 추천에 반영해요.</p>
      <div className="flex flex-wrap items-center gap-3">
        <div role="radiogroup" aria-label="이 코스 별점" className="flex gap-1">
          {STARS.map((n) => (
            <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n}점`} onClick={() => setRating(n)} className="grid size-10 place-items-center rounded-full hover:bg-white">
              <Star aria-hidden className={cn("size-6", n <= rating ? "fill-blue-deep text-blue-deep" : "text-line")} />
            </button>
          ))}
        </div>
        <Button
          type="button"
          size="sm"
          disabled={rating === 0 || feedback.isPending}
          onClick={() => feedback.mutate({ rating, visited: true }, {
              onSuccess: () => {
                track("course_feedback_sent", { course_id: courseId, rating });
                track("visit_marked", { course_id: courseId, rating });
              },
            })
          }
        >
          {feedback.isPending ? "기록하는 중…" : "다녀왔어요"}
        </Button>
      </div>
      {feedback.error ? (
        <p role="alert" className="text-body-sm font-semibold text-pink-deep">
          {mascotCopyForError(feedback.error).description}
        </p>
      ) : null}
    </section>
  );
}
