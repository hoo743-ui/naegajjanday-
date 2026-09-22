"use client";

import Link from "next/link";
import { CalendarRange, UserPlus, Users } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { StatCard } from "@/components/admin/StatCard";
import { BarsChart, DonutChart, TrendChart, heatStyle } from "@/components/admin/charts";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isNotReady, useUserAnalytics } from "@/lib/api/admin";
import { dateRange, num, percent } from "@/lib/format";

export default function AdminUsersPage() {
  const q = useUserAnalytics();

  // 501 NOT_IMPLEMENTED: 고장이 아니라 아직 없는 통계다 (API DB 는 코스 생성만 본다 — DAU·유입은 제품 분석 도구가 있어야 한다)
  if (isNotReady(q.error)) {
    return (
      <>
        <AdminPageHeader title="사용자 분석" description="활성 사용자, 유입, 주차별 리텐션" />
        <Panel>
          <EmptyState
            mood="think"
            title="아직 준비 중인 통계예요"
            description="사용자 분석은 제품 분석 도구(PostHog·GA4)를 연결한 뒤에 볼 수 있어요. 그동안 코스 생성·저장 지표는 ‘추천 결과 통계’에서 확인해 주세요."
          >
            <Button asChild variant="soft" size="md">
              <Link href="/admin/recommendations">추천 결과 통계 보기</Link>
            </Button>
          </EmptyState>
        </Panel>
      </>
    );
  }
  if (q.isError) {
    return (
      <>
        <AdminPageHeader title="사용자 분석" />
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </>
    );
  }
  const d = q.data;
  const maxWeeks = Math.max(0, ...(d?.cohorts.map((c) => c.retention.length) ?? []));

  return (
    <>
      <AdminPageHeader title="사용자 분석" description={d ? `${dateRange(d.range.from, d.range.to)} · 활성 사용자, 유입, 주차별 리텐션` : "활성 사용자, 유입, 주차별 리텐션"} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="전체 사용자" icon={Users} loading={q.isPending} value={d ? num(d.totals.users) : "-"} />
        <StatCard label="신규 가입" icon={UserPlus} loading={q.isPending} value={d ? num(d.totals.new_users) : "-"} hint="기간 내" />
        <StatCard label="WAU / MAU" icon={CalendarRange} loading={q.isPending} value={d ? `${num(d.totals.wau)} / ${num(d.totals.mau)}` : "-"} />
        <StatCard label="고착도 (DAU/MAU)" icon={Users} loading={q.isPending} tone={d && d.totals.stickiness >= 0.2 ? "good" : "warn"} value={d ? percent(d.totals.stickiness, 1) : "-"} />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Panel title="일별 활성 사용자 (DAU)">
          {!d ? <Skeleton className="h-[260px] rounded-2xl" /> : d.daily.length === 0 ? <EmptyState size="sm" title="아직 데이터가 없어요" /> : <TrendChart area data={d.daily} xKey="date" label="일별 활성 사용자 추이" series={[{ key: "dau", label: "DAU" }]} />}
        </Panel>
        <Panel title="일별 신규 가입">
          {!d ? <Skeleton className="h-[260px] rounded-2xl" /> : d.daily.length === 0 ? <EmptyState size="sm" title="아직 데이터가 없어요" /> : <BarsChart data={d.daily} xKey="date" label="일별 신규 가입자 수" series={[{ key: "new_users", label: "신규 가입", color: "#8E8BFF" }]} />}
        </Panel>
        <Panel title="유입 경로">
          {!d ? <Skeleton className="h-[240px] rounded-2xl" /> : d.acquisition.length === 0 ? <EmptyState size="sm" title="유입 데이터가 없어요" /> : <BarsChart horizontal data={d.acquisition} xKey="channel" label="유입 경로별 사용자 수" series={[{ key: "users", label: "사용자" }]} height={240} xFormat={(v) => v} />}
        </Panel>
        <Panel title="로그인 수단">
          {!d ? <Skeleton className="h-[240px] rounded-2xl" /> : d.providers.length === 0 ? <EmptyState size="sm" title="로그인 데이터가 없어요" /> : <DonutChart data={d.providers} nameKey="provider" valueKey="users" label="로그인 수단별 사용자 비율" />}
        </Panel>
      </div>

      <Panel title="주차별 리텐션 코호트" description="가입 주 기준, N주 뒤에도 코스를 만든 사용자 비율" className="mt-5">
        {!d ? (
          <Skeleton className="h-[220px] rounded-2xl" />
        ) : d.cohorts.length === 0 ? (
          <EmptyState size="sm" title="코호트를 만들 만큼 데이터가 쌓이지 않았어요" />
        ) : (
          <div className="overflow-x-auto">
            <table className="tabular w-full min-w-[640px] border-separate border-spacing-1 text-center text-body-sm">
              <caption className="sr-only">주차별 리텐션 코호트 표</caption>
              <thead>
                <tr className="text-caption font-semibold text-muted-foreground">
                  <th scope="col" className="px-2 py-1.5 text-left">
                    가입 주
                  </th>
                  <th scope="col" className="px-2 py-1.5 text-right">
                    인원
                  </th>
                  {Array.from({ length: maxWeeks }, (_, i) => (
                    <th key={i} scope="col" className="px-2 py-1.5">
                      {i}주차
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.cohorts.map((c) => (
                  <tr key={c.cohort}>
                    <th scope="row" className="px-2 py-1.5 text-left font-extrabold whitespace-nowrap">
                      {c.cohort}
                    </th>
                    <td className="px-2 py-1.5 text-right font-bold text-ink-2">{num(c.size)}</td>
                    {Array.from({ length: maxWeeks }, (_, i) => {
                      const v = c.retention[i];
                      return v === undefined ? <td key={i} aria-label="아직 집계 전" className="rounded-lg bg-soft" /> : (
                        <td key={i} className="rounded-lg px-2 py-2 font-extrabold" style={heatStyle(v)}>
                          {percent(v)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
