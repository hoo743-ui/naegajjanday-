"use client";

import { useState } from "react";
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { adminTime } from "@/lib/admin-time";
import { useCourseRequests, type Who } from "@/lib/api/admin";
import { won } from "@/lib/format";
import { cn } from "@/lib/utils";

const WHO: { value: Who; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "member", label: "회원" },
  { value: "anonymous", label: "비로그인" },
];
const TASTE: Record<string, string> = {
  relaxed: "여유롭게",
  packed: "알차게",
  foodie: "맛집 중심",
  special: "특별한 경험",
  night: "야경",
  walk: "산책",
  exhibition: "전시 · 공연",
  value: "가성비",
  romantic: "로맨틱",
  quiet: "조용한",
  indoor: "실내",
  photo: "사진 좋은 곳",
  free: "무료 더",
  fun: "재미 스타일",
  local: "가까운 곳",
  balanced: "적당히 이동",
  explorer: "멀리도",
};
const WARN: Record<string, string> = {
  SLOT_EMPTY: "빈 자리",
  NIGHT_HOURS_ESTIMATED: "밤 영업 추정",
  DURATION_FIT: "시간에 맞춤",
  TOPPED_UP: "자동으로 더함",
  FOCUS_UNAVAILABLE: "명물 없음",
};

function startLabel(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/**
 * 최근 코스 요청 (docs/50): 누가(회원 · 비로그인 + IP) 무엇을 넣었고, 어떤 코스가 나왔는지. 최근순.
 * 저장하지 않은 코스는 24시간 뒤 지워지지만, 어떤 장소를 권했는지는 추천 기록에 남아 계속 보인다.
 */
export default function AdminCourseRequestsPage() {
  const [who, setWho] = useState<Who>("all");
  const log = useCourseRequests(who);
  const rows = log.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <AdminPageHeader
        title="코스 요청"
        description="누가 어떤 조건으로 짰고, 무엇이 나왔는지 · 최근순"
        actions={
          <div role="group" aria-label="누구" className="flex gap-1">
            {WHO.map((w) => (
              <button
                key={w.value}
                type="button"
                aria-pressed={who === w.value}
                onClick={() => setWho(w.value)}
                className={cn("h-9 rounded-full border px-3 text-body-sm", who === w.value ? "border-tomato bg-tomato font-bold text-white" : "border-line bg-white font-medium text-ink-2 hover:border-tomato")}
              >
                {w.label}
              </button>
            ))}
          </div>
        }
      />

      {log.isError ? (
        <ErrorState error={log.error} onRetry={() => void log.refetch()} />
      ) : log.isPending ? (
        <Skeleton className="h-[400px] rounded-2xl" />
      ) : rows.length === 0 ? (
        <Panel>
          <EmptyState size="sm" title="아직 코스 요청이 없어요" />
        </Panel>
      ) : (
        <ol className="grid gap-3">
          {rows.map((r) => (
            <li key={r.id}>
              <Panel>
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <p className="text-body font-bold text-ink">
                    {r.where} · {r.purpose}
                    <span className="ml-2 text-body-sm font-medium text-ink-2">
                      {r.party_size ?? "-"}명 · {r.budget_total != null ? won(r.budget_total) : "-"} · {startLabel(r.start_at)} 시작
                    </span>
                  </p>
                  <p className="tabular text-body-sm text-ink-2">
                    {adminTime(r.at)} · <span className={r.user ? "font-semibold text-ink" : undefined}>{r.user ? (r.user.login_id ?? r.user.nickname ?? "회원") : "비로그인"}</span>
                    {r.ip ? <span className="ml-1 font-mono text-caption">{r.ip}</span> : null}
                  </p>
                </div>
                {r.taste.length || r.warnings.length ? (
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {r.taste.map((t) => (
                      <li key={t} className="rounded-full bg-soft px-2.5 py-0.5 text-caption font-semibold text-ink-2">
                        {TASTE[t] ?? t}
                      </li>
                    ))}
                    {r.warnings.map((w) => (
                      <li key={w} className="rounded-full border border-line px-2.5 py-0.5 text-caption font-semibold text-muted-foreground">
                        {WARN[w] ?? w}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <ul className="mt-3 grid gap-2">
                  {r.courses.map((c) => (
                    <li key={c.id} className="rounded-2xl border border-line px-3 py-2 text-body-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold text-ink">
                          {c.label}
                          {c.total_price != null ? <span className="tabular ml-2 font-medium text-ink-2">{won(c.total_price)}</span> : null}
                          {c.status && c.status !== "generated" ? <span className="ml-2 text-caption text-success">저장됨</span> : null}
                        </span>
                        {c.exists ? (
                          <Link href={`/course/${encodeURIComponent(c.id)}`} target="_blank" className="inline-flex items-center gap-1 text-caption font-semibold text-blue-deep hover:underline">
                            코스 보기 <ExternalLink className="size-3" aria-hidden />
                          </Link>
                        ) : (
                          <span className="text-caption text-muted-foreground">코스는 정리됨</span>
                        )}
                      </div>
                      <p className="mt-1 text-ink-2">{c.places.join(" → ")}</p>
                    </li>
                  ))}
                </ul>
                <p className="tabular mt-2 text-caption text-muted-foreground">
                  후보 {r.candidates}곳 · {(r.latency_ms / 1000).toFixed(1)}초
                </p>
              </Panel>
            </li>
          ))}
        </ol>
      )}

      {log.hasNextPage ? (
        <div className="mt-4 flex justify-center">
          <Button type="button" variant="outline" disabled={log.isFetchingNextPage} onClick={() => void log.fetchNextPage()}>
            {log.isFetchingNextPage ? "불러오는 중…" : "더 보기"}
          </Button>
        </div>
      ) : null}
    </>
  );
}
