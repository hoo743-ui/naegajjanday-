"use client";

import { useMemo } from "react";
import { Bookmark, RotateCw, Shuffle, Sparkles, Timer, Wallet } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { StatCard } from "@/components/admin/StatCard";
import { BarsChart, TrendChart, heatStyle } from "@/components/admin/charts";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecommendationAnalytics, useTopPlaces } from "@/lib/api/admin";
import type { TopPlace } from "@/lib/api/types";
import { dateRange, num, percent, won } from "@/lib/format";

const TOP_COLUMNS: Column<TopPlace>[] = [
  { key: "name", header: "장소", cell: (r) => <b className="font-extrabold">{r.name}</b> },
  { key: "region", header: "지역", cell: (r) => r.region_name, hideBelow: "sm" },
  { key: "category", header: "분류", cell: (r) => r.category_name, hideBelow: "md" },
  { key: "impressions", header: "추천 노출", align: "right", cell: (r) => num(r.impressions) },
  { key: "saves", header: "저장", align: "right", cell: (r) => num(r.saves) },
];
/** 교체 집계는 API 가 줄 때만 열을 만든다 (없는 값을 0 으로 보이지 않게) */
const SWAP_COLUMN: Column<TopPlace> = { key: "swap", header: "교체당함", align: "right", cell: (r) => (r.swap_outs === null ? "-" : `${num(r.swap_outs)} (${percent(r.impressions ? r.swap_outs / r.impressions : 0)})`) };

/** 아직 API 가 집계하지 않는 차트 자리 */
const NotReady = ({ what }: { what: string }) => <EmptyState size="sm" title="아직 준비 중인 통계예요" description={`${what}은(는) 아직 집계하지 않아요.`} />;

export default function AdminRecommendationsPage() {
  const q = useRecommendationAnalytics();
  const top = useTopPlaces();
  const d = q.data;
  const t = d?.totals;
  const topColumns = useMemo(() => (top.data?.items.some((r) => r.swap_outs !== null) ? [...TOP_COLUMNS, SWAP_COLUMN] : TOP_COLUMNS), [top.data]);

  // 지역 × 목적 히트맵: 축은 응답에 등장한 값으로 만든다 (하드코딩 없음)
  const heat = useMemo(() => {
    const cells = d?.heatmap ?? [];
    const regions = [...new Map(cells.map((c) => [c.region, c.region_name])).entries()];
    const purposes = [...new Map(cells.map((c) => [c.purpose, c.purpose_name])).entries()];
    const max = Math.max(1, ...cells.map((c) => c.count));
    const at = new Map(cells.map((c) => [`${c.region}|${c.purpose}`, c.count]));
    return { regions, purposes, max, at };
  }, [d]);

  if (q.isError) {
    return (
      <>
        <AdminPageHeader title="추천 결과 통계" />
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </>
    );
  }

  return (
    <>
      <AdminPageHeader title="추천 결과 통계" description={d ? `${dateRange(d.range.from, d.range.to)} · 가중치를 바꾼 뒤에는 저장률과 다시 짜기 비율을 먼저 보세요.` : undefined} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard label="코스 생성" icon={Sparkles} loading={q.isPending} value={t ? num(t.generated) : "-"} />
        <StatCard label="저장률" icon={Bookmark} loading={q.isPending} tone={t && t.save_rate >= 0.25 ? "good" : "warn"} value={t ? percent(t.save_rate, 1) : "-"} hint="목표 25% 이상" />
        <StatCard label="다시 짜기" icon={RotateCw} loading={q.isPending} tone={t && t.reroll_rate <= 0.35 ? "good" : "warn"} value={t ? percent(t.reroll_rate, 1) : "-"} hint="목표 35% 이하" />
        <StatCard label="한 곳 교체" icon={Shuffle} loading={q.isPending} value={t && t.swap_rate !== null ? percent(t.swap_rate, 1) : "-"} hint={t && t.swap_rate === null ? "아직 집계 전" : undefined} />
        <StatCard label="평균 예산" icon={Wallet} loading={q.isPending} value={t ? won(t.avg_budget) : "-"} hint={t ? (t.avg_budget_utilization !== null ? `평균 사용률 ${percent(t.avg_budget_utilization)}` : t.avg_budget_per_person != null ? `1인 평균 ${won(t.avg_budget_per_person)}` : undefined) : undefined} />
        <StatCard label="p95 응답" icon={Timer} loading={q.isPending} tone={t && t.p95_latency_ms !== null && t.p95_latency_ms <= 1800 ? "good" : "warn"} value={t && t.p95_latency_ms !== null ? `${(t.p95_latency_ms / 1000).toFixed(2)}초` : "-"} hint={t?.p50_latency_ms != null ? `p50 ${(t.p50_latency_ms / 1000).toFixed(2)}초 · 목표 1.8초 이하` : "목표 1.8초 이하"} />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Panel title="일별 생성 · 저장 · 다시 짜기">
          {!d ? <Skeleton className="h-[260px] rounded-2xl" /> : d.daily === null ? <NotReady what="일별 추이" /> : d.daily.length === 0 ? <EmptyState size="sm" title="아직 생성된 코스가 없어요" /> : <TrendChart data={d.daily} xKey="date" label="일별 코스 생성, 저장, 다시 짜기 추이" series={[{ key: "generated", label: "생성" }, { key: "saved", label: "저장" }, { key: "rerolled", label: "다시 짜기" }]} />}
        </Panel>
        <Panel title="목적별 생성 수" description="막대에 마우스를 올리면 건수를 볼 수 있어요">
          {!d ? <Skeleton className="h-[260px] rounded-2xl" /> : d.by_purpose.length === 0 ? <EmptyState size="sm" title="목적별 데이터가 없어요" /> : <BarsChart horizontal data={d.by_purpose.map(({ purpose_name, generated }) => ({ purpose_name, generated }))} xKey="purpose_name" label="목적별 코스 생성 수" series={[{ key: "generated", label: "생성" }]} xFormat={(v) => v} />}
        </Panel>
        <Panel title="예산 분포" description="요청 시 입력한 총 예산">
          {!d ? <Skeleton className="h-[260px] rounded-2xl" /> : d.budget_histogram === null ? <NotReady what="예산 분포" /> : d.budget_histogram.length === 0 ? <EmptyState size="sm" title="예산 데이터가 없어요" /> : <BarsChart data={d.budget_histogram} xKey="bucket" label="총 예산 구간별 요청 수" series={[{ key: "count", label: "요청 수", color: "#8E8BFF" }]} xFormat={(v) => v} />}
        </Panel>
        <Panel title="응답 지연" description="코스 생성 API (LLM 설명은 별도 스트림)">
          {!d ? <Skeleton className="h-[260px] rounded-2xl" /> : d.latency === null ? <NotReady what="일별 응답 지연" /> : d.latency.length === 0 ? <EmptyState size="sm" title="지연 데이터가 없어요" /> : <TrendChart data={d.latency} xKey="date" label="일별 응답 지연 p50과 p95" format={(v) => `${Math.round(v)}ms`} series={[{ key: "p50", label: "p50" }, { key: "p95", label: "p95", color: "#E0457F" }]} />}
        </Panel>
      </div>

      <Panel title="지역 × 목적 히트맵" description="어느 동네에서 어떤 약속으로 많이 쓰는지. 빈 칸은 요청이 없던 조합이에요." className="mt-5">
        {!d ? (
          <Skeleton className="h-[220px] rounded-2xl" />
        ) : heat.regions.length === 0 ? (
          <EmptyState size="sm" title="히트맵을 그릴 데이터가 없어요" />
        ) : (
          <div className="overflow-x-auto">
            <table className="tabular w-full min-w-[560px] border-separate border-spacing-1 text-center text-[13px]">
              <caption className="sr-only">지역과 목적 조합별 코스 생성 수</caption>
              <thead>
                <tr className="text-xs font-extrabold text-muted-foreground">
                  <td />
                  {heat.purposes.map(([code, name]) => (
                    <th key={code} scope="col" className="px-2 py-1.5">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heat.regions.map(([slug, name]) => (
                  <tr key={slug}>
                    <th scope="row" className="px-2 py-1.5 text-left font-extrabold whitespace-nowrap">
                      {name}
                    </th>
                    {heat.purposes.map(([code]) => {
                      const count = heat.at.get(`${slug}|${code}`);
                      return count === undefined ? <td key={code} className="rounded-lg bg-soft text-muted-foreground">-</td> : (
                        <td key={code} className="rounded-lg px-2 py-2.5 font-extrabold" style={heatStyle(count / heat.max)}>
                          {num(count)}
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

      <Panel title="많이 추천된 장소" description="추천에 많이 오른 순서예요. 노출에 비해 저장이 적으면 점수에 비해 만족도가 낮다는 신호예요." className="mt-5">
        <DataTable caption="많이 추천된 장소" columns={topColumns} rows={top.data?.items} rowKey={(r) => r.id} isLoading={top.isPending} error={top.error} onRetry={() => void top.refetch()} empty={{ title: "아직 추천된 장소가 없어요" }} />
      </Panel>
    </>
  );
}
