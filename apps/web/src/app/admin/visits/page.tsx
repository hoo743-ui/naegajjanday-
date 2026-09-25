"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { adminTime } from "@/lib/admin-time";
import { useVisitLog, type Who } from "@/lib/api/admin";
import { cn } from "@/lib/utils";

const WHO: { value: Who; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "member", label: "회원" },
  { value: "anonymous", label: "비로그인" },
];
const DEVICE: Record<string, string> = { mobile: "모바일", tablet: "태블릿", desktop: "PC" };

/**
 * 방문 로그 (docs/50): 페이지를 볼 때마다 한 줄 — 최근순. 같은 브라우저는 '방문자' 8자리가 같다.
 * IP 는 부정 이용 확인용으로만, 90일 뒤 지워진다.
 */
export default function AdminVisitsPage() {
  const [who, setWho] = useState<Who>("all");
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const log = useVisitLog(who, q);
  const rows = log.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <AdminPageHeader title="방문 로그" description="페이지를 볼 때마다 한 줄 · 최근순 · IP 는 90일 뒤 지워져요" />
      <Panel>
        <div className="mb-4 flex flex-wrap items-center gap-2">
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
          <form
            role="search"
            className="flex flex-1 gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setQ(draft.trim());
            }}
          >
            <div className="relative min-w-[200px] flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="IP · 경로 · 유입" aria-label="방문 로그 검색" className="h-9 rounded-xl pl-9" />
            </div>
            <Button type="submit" size="sm" variant="outline">
              찾기
            </Button>
          </form>
        </div>

        {log.isError ? (
          <ErrorState error={log.error} onRetry={() => void log.refetch()} />
        ) : log.isPending ? (
          <Skeleton className="h-[320px] rounded-2xl" />
        ) : rows.length === 0 ? (
          <EmptyState size="sm" title="아직 방문 기록이 없어요" />
        ) : (
          <div className="overflow-x-auto">
            <table className="tabular w-full min-w-[860px] text-body-sm">
              <caption className="sr-only">방문 로그</caption>
              <thead>
                <tr className="border-b border-line text-left text-caption font-semibold text-muted-foreground">
                  {["시각", "누구", "방문자", "페이지", "기기", "유입", "IP"].map((h) => (
                    <th key={h} scope="col" className="px-2 py-2 whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((v) => (
                  <tr key={v.id} className="border-b border-line/60">
                    <td className="px-2 py-1.5 whitespace-nowrap">{adminTime(v.at)}</td>
                    <td className={cn("px-2 py-1.5 whitespace-nowrap", v.user ? "font-semibold text-ink" : "text-muted-foreground")}>{v.user ? (v.user.login_id ?? v.user.nickname ?? "회원") : "비로그인"}</td>
                    <td className="px-2 py-1.5 font-mono text-caption text-ink-2">{v.visitor}</td>
                    <td className="max-w-[260px] truncate px-2 py-1.5">{v.path}</td>
                    <td className="px-2 py-1.5 text-ink-2">{DEVICE[v.device] ?? v.device}</td>
                    <td className="px-2 py-1.5 text-ink-2">{v.referrer ?? "-"}</td>
                    <td className="px-2 py-1.5 font-mono text-caption">{v.ip ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {log.hasNextPage ? (
          <div className="mt-4 flex justify-center">
            <Button type="button" variant="outline" disabled={log.isFetchingNextPage} onClick={() => void log.fetchNextPage()}>
              {log.isFetchingNextPage ? "불러오는 중…" : "더 보기"}
            </Button>
          </div>
        ) : null}
      </Panel>
    </>
  );
}
