"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, Trash2 } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteMyCourse, useMyCourses } from "@/lib/api/hooks";
import type { SavedCourse } from "@/lib/api/types";
import { dateShort, minutes, won } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";

export function SavedCourses() {
  const courses = useMyCourses();
  const remove = useDeleteMyCourse();
  const [target, setTarget] = useState<SavedCourse | null>(null);

  if (courses.isPending) {
    return (
      <div className="grid gap-3 sm:grid-cols-2" aria-busy="true" aria-label="저장한 코스 불러오는 중">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-[148px] rounded-card" />
        ))}
      </div>
    );
  }
  if (courses.isError) return <ErrorState error={courses.error} onRetry={() => void courses.refetch()} className="rounded-card bg-white shadow-soft" />;

  const items = courses.data.pages.flatMap((p) => p.items);
  if (items.length === 0) {
    return (
      <EmptyState mood="think" title="아직 저장한 코스가 없어요" description="마음에 드는 코스를 저장해 두면 약속 날 바로 꺼내 볼 수 있어요." className="border-y border-ink/10">
        <Button asChild variant="brand" size="md">
          <Link href="/plan">첫 코스 짜러 가기</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <>
      <ul className="grid gap-3 sm:grid-cols-2">
        {items.map((c) => (
          // 한 장의 작은 영수증: 저장한 하루가 쌓인다 (docs/25 §5 내 코스)
          <li key={c.id} className="receipt-wrap group relative transition-transform duration-200 hover:-translate-y-0.5">
            <div className="receipt px-5 pt-6 pb-5">
            <p className="tabular text-xs font-extrabold text-blue-deep">
              {[c.region_name, c.purpose_name, `${c.party_size}명`].filter(Boolean).join(" · ")}
              {c.day && c.days && c.days > 1 ? <span className="ml-2 rounded-full bg-blue-soft px-2 py-0.5">{`${c.days - 1}박 ${c.days}일 · ${c.day}일차`}</span> : null}
              {c.visited ? <span className="ml-2 rounded-full bg-success-soft px-2 py-0.5 text-success">다녀옴</span> : null}
            </p>
            <h3 className="mt-1 text-[17px] font-extrabold tracking-tight">
              <Link href={`/course/${encodeURIComponent(c.id)}`} className="after:absolute after:inset-0">
                {c.summary}
              </Link>
            </h3>
            {/* useMyCourses 가 toSavedCourse 로 맞춰 준다: stop_names 는 항상 배열, totals 는 항상 있다 */}
            {c.stop_names.length > 0 ? <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">{c.stop_names.join(" → ")}</p> : null}
            <p className="tabular mt-3 flex items-center justify-between border-t-[1.5px] border-dashed border-ink/15 pt-3 text-sm font-bold text-ink-2">
              <span>
                <b className="text-base font-extrabold text-ink">{won(c.totals.price)}</b>
                {c.totals.duration_min > 0 ? ` · ${minutes(c.totals.duration_min)}` : ""}
                {c.saved_at ? ` · ${dateShort(c.saved_at)} 저장` : ""}
              </span>
              <ChevronRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
            </p>
            </div>
            <button
              type="button"
              onClick={() => {
                remove.reset();
                setTarget(c);
              }}
              aria-label={`${c.summary} 코스 삭제`}
              className="absolute top-4 right-3 z-10 grid size-11 place-items-center rounded-full text-muted-foreground hover:bg-pink-soft hover:text-pink-deep"
            >
              <Trash2 aria-hidden className="size-4" />
            </button>
          </li>
        ))}
      </ul>

      {courses.hasNextPage ? (
        <div className="mt-4 text-center">
          <Button type="button" variant="soft" size="md" onClick={() => void courses.fetchNextPage()} disabled={courses.isFetchingNextPage}>
            {courses.isFetchingNextPage ? "불러오는 중…" : "더 보기"}
          </Button>
        </div>
      ) : null}

      <Dialog open={target !== null} onOpenChange={(open) => !open && setTarget(null)}>
        <DialogContent className="rounded-card">
          <DialogHeader>
            <DialogTitle>이 코스를 지울까요?</DialogTitle>
            <DialogDescription>{target?.summary}</DialogDescription>
          </DialogHeader>
          {remove.error ? (
            <p role="alert" className="text-sm font-bold text-danger">
              {mascotCopyForError(remove.error).description}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="soft" onClick={() => setTarget(null)}>
              그대로 둘게요
            </Button>
            <Button type="button" variant="destructive" disabled={remove.isPending} onClick={() => target && remove.mutate(target.id, { onSuccess: () => setTarget(null) })}>
              {remove.isPending ? "지우는 중…" : "지우기"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
