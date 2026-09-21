"use client";

import Link from "next/link";
import { Activity, Bookmark, ClipboardCheck, RotateCw, Sparkles, Timer, Users } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { StatCard } from "@/components/admin/StatCard";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { BarsChart, TrendChart } from "@/components/admin/charts";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminPlaces, useAdminRegions, useRecommendationAnalytics, useSystemHealth, useUserAnalytics } from "@/lib/api/admin";
import { num, percent } from "@/lib/format";

export default function AdminDashboardPage() {
  const users = useUserAnalytics();
  const recs = useRecommendationAnalytics();
  const pending = useAdminPlaces({ status: "pending", limit: 1 });
  const regions = useAdminRegions();
  const health = useSystemHealth();

  const t = recs.data?.totals;
  const pendingCount = pending.data ? (pending.data.total ?? pending.data.items.length) : undefined;
  const collecting = regions.data?.items.filter((r) => r.status === "collecting").length ?? 0;

  return (
    <>
      <AdminPageHeader title="대시보드" description="최근 30일 기준이에요. 목표치는 추천 알고리즘 문서(06)의 평가 지표를 따릅니다." />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="DAU" icon={Users} loading={users.isPending} value={users.data ? num(users.data.totals.dau) : "-"} hint={users.data ? `MAU ${num(users.data.totals.mau)} · 고착도 ${percent(users.data.totals.stickiness)}` : undefined} />
        <StatCard label="코스 생성" icon={Sparkles} loading={recs.isPending} value={t ? num(t.generated) : "-"} hint="최근 30일" />
        <StatCard label="저장률" icon={Bookmark} loading={recs.isPending} tone={t && t.save_rate >= 0.25 ? "good" : "warn"} value={t ? percent(t.save_rate, 1) : "-"} hint="목표 25% 이상" />
        <StatCard label="다시 짜기 비율" icon={RotateCw} loading={recs.isPending} tone={t && t.reroll_rate <= 0.35 ? "good" : "warn"} value={t ? percent(t.reroll_rate, 1) : "-"} hint="목표 35% 이하" />
        <StatCard label="p95 응답" icon={Timer} loading={recs.isPending} tone={t && t.p95_latency_ms <= 1800 ? "good" : "warn"} value={t ? `${(t.p95_latency_ms / 1000).toFixed(2)}초` : "-"} hint="목표 1.8초 이하" />
        <StatCard label="슬롯 공백률" icon={Activity} loading={recs.isPending} tone={t && t.slot_empty_rate <= 0.05 ? "good" : "warn"} value={t ? percent(t.slot_empty_rate, 1) : "-"} hint="후보가 없어 비운 슬롯" />
        <StatCard
          label="승인 대기 장소"
          icon={ClipboardCheck}
          loading={pending.isPending}
          tone={pendingCount ? "warn" : "good"}
          value={pendingCount !== undefined ? `${num(pendingCount)}${pending.data?.next_cursor && pending.data.total === undefined ? "+" : ""}` : "-"}
          hint={
            <Link href="/admin/places" className="font-extrabold text-blue-deep underline-offset-4 hover:underline">
              승인하러 가기
            </Link>
          }
        />
        <StatCard label="수집 중인 지역" icon={Activity} loading={regions.isPending} value={regions.data ? num(collecting) : "-"} hint={regions.data ? `전체 ${num(regions.data.items.length)}개 지역` : undefined} />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Panel title="일별 활성 사용자" description="DAU 와 신규 가입">
          {users.isPending ? (
            <Skeleton className="h-[260px] rounded-2xl" />
          ) : users.isError ? (
            <ErrorState error={users.error} onRetry={() => void users.refetch()} size="sm" />
          ) : users.data.daily.length === 0 ? (
            <EmptyState size="sm" title="아직 쌓인 데이터가 없어요" />
          ) : (
            <TrendChart area data={users.data.daily} xKey="date" label="최근 30일 DAU와 신규 가입자 추이" series={[{ key: "dau", label: "DAU" }, { key: "new_users", label: "신규" }]} />
          )}
        </Panel>
        <Panel title="코스 생성 · 저장 · 다시 짜기" description="하루 단위">
          {recs.isPending ? (
            <Skeleton className="h-[260px] rounded-2xl" />
          ) : recs.isError ? (
            <ErrorState error={recs.error} onRetry={() => void recs.refetch()} size="sm" />
          ) : recs.data.daily.length === 0 ? (
            <EmptyState size="sm" title="아직 생성된 코스가 없어요" />
          ) : (
            <BarsChart data={recs.data.daily} xKey="date" label="최근 30일 코스 생성, 저장, 다시 짜기 건수" series={[{ key: "generated", label: "생성" }, { key: "saved", label: "저장" }, { key: "rerolled", label: "다시 짜기" }]} />
          )}
        </Panel>
      </div>

      <Panel title="시스템 상태" className="mt-5" actions={health.data ? <StatusBadge status={health.data.status} /> : null}>
        {health.isPending ? (
          <Skeleton className="h-16 rounded-2xl" />
        ) : health.isError ? (
          <ErrorState error={health.error} onRetry={() => void health.refetch()} size="sm" />
        ) : health.data.services.length === 0 ? (
          <EmptyState size="sm" title="보고된 서비스가 없어요" />
        ) : (
          <ul className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {health.data.services.map((s) => (
              <li key={s.name} className="flex items-center justify-between gap-2 rounded-2xl bg-soft px-4 py-3">
                <span className="min-w-0">
                  <b className="block truncate text-sm font-extrabold">{s.name}</b>
                  <span className="tabular text-xs text-muted-foreground">{s.latency_ms !== null ? `${s.latency_ms}ms` : "응답 없음"}</span>
                </span>
                <StatusBadge status={s.status} />
              </li>
            ))}
          </ul>
        )}
        <div className="mt-4">
          <Button asChild variant="soft" size="sm">
            <Link href="/admin/recommendations">추천 통계 자세히</Link>
          </Button>
        </div>
      </Panel>
    </>
  );
}
