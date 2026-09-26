"use client";

import { useState } from "react";
import { Bookmark, ExternalLink, MousePointerClick, Sparkles, ThumbsUp } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { StatCard } from "@/components/admin/StatCard";
import { BarsChart } from "@/components/admin/charts";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { type RateCount, useUsageMetrics } from "@/lib/api/admin";
import { num, percent } from "@/lib/format";
import { cn } from "@/lib/utils";

const RANGES = [7, 28, 90] as const;
const OPTION_LABEL: Record<string, string> = { BAR: "술 한잔", MOVIE: "영화", BASEBALL: "야구", rain: "비 오는 날", ERRAND: "꼭 들를 곳" };

const rate = (r: RateCount | number | null | undefined, digits = 0) => {
  const v = typeof r === "number" || r == null ? r : r.rate;
  return v == null ? "-" : percent(v, digits);
};
const frac = (r: RateCount) => `${num(r.count)} / ${num(r.total)}`;

/**
 * 사용 지표 (docs/61 §6 · docs/62): 만든 코스가 실제로 쓰였는가.
 * "쓰인 코스" = 코스를 만든 번(대안 포함) 중 7일 안에 저장 · 공유 · 길찾기/장소 링크 · 확정(다녀옴) 중 하나라도 일어난 번.
 * 이벤트는 우리 API 에 직접 쌓인다(외부 분석 도구 없이). 수집 시작 전 주는 저장만 센다.
 */
export default function AdminUsagePage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(28);
  const q = useUsageMetrics(days);

  if (q.isError) {
    return (
      <>
        <AdminPageHeader title="사용 지표" />
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </>
    );
  }
  const d = q.data;
  const since = d?.collecting_since ? d.collecting_since.slice(0, 10) : null;
  const weeks = d ? [...d.north_star].reverse() : [];
  const latestDone = d?.north_star.filter((w) => w.complete && w.generated > 0).at(-1);

  return (
    <>
      <AdminPageHeader
        title="사용 지표"
        description={`만든 코스가 실제로 쓰였는지 봅니다. ${since ? `이벤트 수집 시작 ${since}.` : "아직 수집된 이벤트가 없어요."} 주간 표는 최근 8주, 아래 지표는 최근 ${days}일.`}
        actions={
          <div role="group" aria-label="기간" className="flex gap-1">
            {RANGES.map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={days === n}
                onClick={() => setDays(n)}
                className={cn("h-9 rounded-full border px-3 text-body-sm", days === n ? "border-tomato bg-tomato font-bold text-white" : "border-line bg-white font-medium text-ink-2 hover:border-tomato")}
              >
                {n}일
              </button>
            ))}
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="쓰인 코스 비율"
          icon={Sparkles}
          loading={q.isPending}
          value={d ? rate(d.used, 1) : "-"}
          hint={d ? `${frac(d.used)} · 지난 완결 주 ${latestDone ? rate(latestDone.rate, 1) : "-"}` : undefined}
        />
        <StatCard label="첫 코스 채택" icon={ThumbsUp} loading={q.isPending} value={d ? rate(d.first_course_accepted, 1) : "-"} hint={d ? `쓰인 ${num(d.first_course_accepted.total)}번 중 다시 짜기 · 바꾸기 없이` : undefined} />
        <StatCard label="길찾기 · 장소 링크" icon={ExternalLink} loading={q.isPending} value={d ? rate(d.outbound, 1) : "-"} hint={d ? `${frac(d.outbound)} 번` : undefined} />
        <StatCard
          label="이벤트가 잡힌 코스"
          icon={MousePointerClick}
          loading={q.isPending}
          tone={d && d.generated > 0 && (d.with_events.rate ?? 0) < 0.5 ? "warn" : "default"}
          value={d ? rate(d.with_events) : "-"}
          hint="낮으면 수집이 막힌 것 (차단 · 설정)"
        />
      </div>

      <Panel title="쓰인 코스 비율 — 주간" description="그 주에 만든 코스가 7일 안에 저장 · 공유 · 길찾기/링크 · 확정 중 하나라도 된 비율. '집계 중'은 7일이 아직 안 지나 오를 수 있어요." className="mt-5">
        {!d ? (
          <Skeleton className="h-[260px] rounded-2xl" />
        ) : d.north_star.every((w) => w.generated === 0) ? (
          <EmptyState size="sm" title="최근 8주 동안 만든 코스가 없어요" />
        ) : (
          <>
            <BarsChart data={d.north_star.map((w) => ({ week: w.week, generated: w.generated, used: w.used }))} xKey="week" label="주별 만든 코스와 쓰인 코스" series={[{ key: "generated", label: "만든 번" }, { key: "used", label: "쓰인 번", color: "#2BB673" }]} height={220} />
            <div className="mt-4 overflow-x-auto">
              <table className="tabular w-full min-w-[640px] text-body-sm">
                <caption className="sr-only">주별 쓰인 코스 표</caption>
                <thead>
                  <tr className="border-b border-line text-left text-caption font-semibold text-muted-foreground">
                    {["주 (월요일)", "만든 번", "쓰인 번", "비율", "저장", "공유", "길찾기 · 링크", "확정 · 다녀옴"].map((h, i) => (
                      <th key={h} scope="col" className={cn("px-2 py-2", i > 0 && "text-right")}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {weeks.map((w) => (
                    <tr key={w.week} className={cn("border-b border-line/60", w.generated === 0 && "text-muted-foreground")}>
                      <th scope="row" className="px-2 py-2 text-left font-semibold whitespace-nowrap">
                        {w.week.slice(5).replace("-", ".")}
                        {w.complete ? null : <span className="ml-1.5 text-caption font-medium text-gold-ink">집계 중</span>}
                      </th>
                      {[num(w.generated), num(w.used), rate(w.rate, 1), num(w.signals.saved), num(w.signals.shared), num(w.signals.outbound), num(w.signals.confirmed)].map((v, i) => (
                        <td key={i} className={cn("px-2 py-2 text-right", i === 2 && "font-bold text-ink")}>
                          {v}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Panel title="업종별 바꾸기" description="사람들이 본 코스의 칸 중, 그 업종의 칸을 다른 곳으로 바꾼 비율 — 높을수록 그 업종 추천을 덜 믿는다">
          {!d ? (
            <Skeleton className="h-[200px] rounded-2xl" />
          ) : d.swap_by_category.length === 0 ? (
            <EmptyState size="sm" title="아직 데이터가 없어요" />
          ) : (
            <table className="tabular w-full text-body-sm">
              <caption className="sr-only">업종별 바꾸기 비율</caption>
              <thead>
                <tr className="border-b border-line text-left text-caption font-semibold text-muted-foreground">
                  <th scope="col" className="px-2 py-2">업종</th>
                  <th scope="col" className="px-2 py-2 text-right">칸</th>
                  <th scope="col" className="px-2 py-2 text-right">바꾼 수</th>
                  <th scope="col" className="px-2 py-2 text-right">비율</th>
                </tr>
              </thead>
              <tbody>
                {d.swap_by_category.map((c) => (
                  <tr key={c.category} className="border-b border-line/60">
                    <th scope="row" className="px-2 py-2 text-left font-semibold">{c.name}</th>
                    <td className="px-2 py-2 text-right">{num(c.stops)}</td>
                    <td className="px-2 py-2 text-right">{num(c.swaps)}</td>
                    <td className="px-2 py-2 text-right font-bold text-ink">{rate(c.rate, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="옵션 칩 · 한 줄 말" description={d ? `한 줄 말: ${frac(d.option_text)}번 옵션을 알아들음 (${rate(d.option_text)}). 안 쓰는 옵션은 치운다(docs/59 #2)` : undefined}>
          {!d ? (
            <Skeleton className="h-[200px] rounded-2xl" />
          ) : d.options.length === 0 ? (
            <EmptyState size="sm" title="아직 옵션을 쓴 기록이 없어요" />
          ) : (
            <table className="tabular w-full text-body-sm">
              <caption className="sr-only">옵션별 사용</caption>
              <thead>
                <tr className="border-b border-line text-left text-caption font-semibold text-muted-foreground">
                  {["옵션", "켬", "끔", "칩", "한 줄 말", "설정"].map((h, i) => (
                    <th key={h} scope="col" className={cn("px-2 py-2", i > 0 && "text-right")}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.options.map((o) => (
                  <tr key={o.option} className="border-b border-line/60">
                    <th scope="row" className="px-2 py-2 text-left font-semibold">{OPTION_LABEL[o.option] ?? o.option}</th>
                    {[o.on, o.off, o.chip, o.text, o.settings].map((v, i) => (
                      <td key={i} className="px-2 py-2 text-right">
                        {num(v)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-3">
        <StatCard label="공유 → 친구가 엶" icon={ExternalLink} loading={q.isPending} value={d ? rate(d.share_opened) : "-"} hint={d ? `공유된 ${num(d.share_opened.total)}개 중 다른 브라우저에서 열린 ${num(d.share_opened.count)}개` : undefined} />
        <StatCard label="다녀옴" icon={Bookmark} loading={q.isPending} value={d ? frac(d.visited) : "-"} hint="피드백 중 다녀왔어요" />
        <StatCard label="예산 정확도" icon={Bookmark} loading={q.isPending} value={d ? rate(d.spend_within_20) : "-"} hint={d ? `실제 지출이 ±20% 안 (${frac(d.spend_within_20)})` : undefined} />
      </div>

      <Panel title="들어온 이벤트" description="이름별 건수와 브라우저 수. 0 이면 그 행동이 아직 없거나 웹이 보내지 않는 것" className="mt-5">
        {!d ? (
          <Skeleton className="h-[160px] rounded-2xl" />
        ) : d.events.length === 0 ? (
          <EmptyState size="sm" title="아직 들어온 이벤트가 없어요" description="배포 뒤 첫 방문부터 쌓여요." />
        ) : (
          <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
            {d.events.map((e) => (
              <li key={e.name} className="flex items-center justify-between gap-3 border-b border-line/60 py-1.5 text-body-sm">
                <code className="truncate">{e.name}</code>
                <span className="tabular shrink-0 text-ink-2">
                  {num(e.count)} · <span className="text-muted-foreground">{num(e.devices)}명</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
