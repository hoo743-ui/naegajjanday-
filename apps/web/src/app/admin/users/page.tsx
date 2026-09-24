"use client";

import { useState } from "react";
import { BarChart3, CalendarRange, Eye, UserPlus, Users } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { StatCard } from "@/components/admin/StatCard";
import { BarsChart, DonutChart, heatStyle } from "@/components/admin/charts";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useUserAnalytics } from "@/lib/api/admin";
import { dateRange, num, percent } from "@/lib/format";
import { cn } from "@/lib/utils";

const RANGES = [7, 14, 30, 90] as const;
const DEVICE_LABEL: Record<string, string> = { mobile: "모바일", tablet: "태블릿", desktop: "PC" };
const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];
const COLUMNS = ["날짜", "방문자", "로그인", "비로그인", "페이지 조회", "신규 가입", "로그인 횟수", "코스 생성", "비로그인 생성", "저장"];

function isoDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * 사용자 분석 (docs/50): 우리 DB 의 방문 기록으로 센다 — 로그인한 사람도, 안 한 사람도 모두.
 * 방문자 = 브라우저 수(같은 사람이 폰 · PC 로 오면 둘). 날짜는 한국 날짜.
 */
export default function AdminUsersPage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(14);
  const today = new Date();
  const from = new Date(today);
  from.setDate(today.getDate() - (days - 1));
  const q = useUserAnalytics({ from: isoDay(from), to: isoDay(today) });

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
  const rows = d ? [...d.daily].reverse() : [];
  // 방문 기록은 2026-09-25 부터 모았다: 그 전 날의 방문자 0 은 "아무도 안 왔다"가 아니다
  const firstSeen = d?.daily.find((r) => r.visitors > 0)?.date;
  const before = firstSeen ? d?.daily.some((r) => r.date < firstSeen && r.courses + r.new_users > 0) : false;

  return (
    <>
      <AdminPageHeader
        title="사용자 분석"
        description={d ? `${dateRange(d.range.from, d.range.to)} · 로그인 · 비로그인 방문을 모두 셉니다` : "로그인 · 비로그인 방문을 모두 셉니다"}
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
        <StatCard label="방문자" icon={Users} loading={q.isPending} value={d ? num(d.totals.visitors) : "-"} hint={d ? `로그인 ${num(d.totals.logged_in)} · 비로그인 ${num(d.totals.anonymous)}` : undefined} />
        <StatCard label="페이지 조회" icon={Eye} loading={q.isPending} value={d ? num(d.totals.page_views) : "-"} hint="기간 내" />
        <StatCard label="코스 생성" icon={BarChart3} loading={q.isPending} value={d ? num(d.totals.courses) : "-"} hint={d ? `비로그인 ${num(d.totals.courses_anonymous)}` : undefined} />
        <StatCard label="가입 계정" icon={UserPlus} loading={q.isPending} value={d ? num(d.totals.users) : "-"} hint={d ? `기간 내 신규 ${num(d.totals.new_users)}` : undefined} />
      </div>

      <Panel title="날짜별 사용량" description="방문자는 브라우저 수예요. 같은 날 여러 번 와도 한 번으로 셉니다." className="mt-5">
        {!d ? (
          <Skeleton className="h-[240px] rounded-2xl" />
        ) : (
          <>
            <BarsChart stacked data={d.daily} xKey="date" label="날짜별 로그인 · 비로그인 방문자" series={[{ key: "logged_in", label: "로그인" }, { key: "anonymous", label: "비로그인", color: "#8E8BFF" }]} height={220} />
            {before && firstSeen ? (
              <p className="mt-3 text-body-sm text-ink-2">방문 기록은 {firstSeen.slice(5).replace("-", ".")}부터 모았어요. 그 전 날짜의 방문자 0은 기록이 없다는 뜻이고, 코스 생성 · 가입은 그 전부터 정확해요.</p>
            ) : null}
            <div className="mt-4 overflow-x-auto">
              <table className="tabular w-full min-w-[720px] text-body-sm">
                <caption className="sr-only">날짜별 사용량 표</caption>
                <thead>
                  <tr className="border-b border-line text-left text-caption font-semibold text-muted-foreground">
                    {COLUMNS.map((h, i) => (
                      <th key={h} scope="col" className={cn("px-2 py-2", i > 0 && "text-right")}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const day = new Date(`${r.date}T00:00:00`);
                    const empty = r.visitors + r.courses + r.new_users === 0;
                    return (
                      <tr key={r.date} className={cn("border-b border-line/60", empty && "text-muted-foreground")}>
                        <th scope="row" className="px-2 py-2 text-left font-semibold whitespace-nowrap">
                          {r.date.slice(5).replace("-", ".")} ({WEEKDAY[day.getDay()]})
                        </th>
                        {[r.visitors, r.logged_in, r.anonymous, r.page_views, r.new_users, r.logins, r.courses, r.courses_anonymous, r.saved].map((v, i) => (
                          <td key={i} className={cn("px-2 py-2 text-right", i === 0 && v > 0 && "font-bold text-ink")}>
                            {num(v)}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      <div className="mt-5 grid gap-5 xl:grid-cols-3">
        <Panel title="유입 경로" description="처음 들어올 때 어디서 왔는지">
          {!d ? <Skeleton className="h-[240px] rounded-2xl" /> : d.acquisition.length === 0 ? <EmptyState size="sm" title="유입 데이터가 없어요" /> : <BarsChart horizontal data={d.acquisition} xKey="channel" label="유입 경로별 방문자 수" series={[{ key: "users", label: "방문자" }]} height={240} xFormat={(v) => v} />}
        </Panel>
        <Panel title="기기">
          {!d ? <Skeleton className="h-[240px] rounded-2xl" /> : d.devices.length === 0 ? <EmptyState size="sm" title="아직 데이터가 없어요" /> : <DonutChart data={d.devices.map((x) => ({ ...x, device: DEVICE_LABEL[x.device] ?? x.device }))} nameKey="device" valueKey="users" label="기기별 방문자 비율" />}
        </Panel>
        <Panel title="로그인 수단" description="가입 계정 기준">
          {!d ? <Skeleton className="h-[240px] rounded-2xl" /> : d.providers.length === 0 ? <EmptyState size="sm" title="로그인 데이터가 없어요" /> : <DonutChart data={d.providers} nameKey="provider" valueKey="users" label="로그인 수단별 계정 비율" />}
        </Panel>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-3">
        <StatCard label="오늘 방문자" icon={Users} loading={q.isPending} value={d ? num(d.totals.dau) : "-"} />
        <StatCard label="WAU / MAU" icon={CalendarRange} loading={q.isPending} value={d ? `${num(d.totals.wau)} / ${num(d.totals.mau)}` : "-"} />
        <StatCard label="고착도 (DAU/MAU)" icon={Users} loading={q.isPending} tone={d && d.totals.stickiness >= 0.2 ? "good" : "warn"} value={d ? percent(d.totals.stickiness, 1) : "-"} />
      </div>

      <Panel title="주차별 재방문" description="처음 온 주 기준, N주 뒤에도 다시 온 방문자 비율" className="mt-5">
        {!d ? (
          <Skeleton className="h-[220px] rounded-2xl" />
        ) : d.cohorts.length === 0 ? (
          <EmptyState size="sm" title="코호트를 만들 만큼 데이터가 쌓이지 않았어요" />
        ) : (
          <div className="overflow-x-auto">
            <table className="tabular w-full min-w-[640px] border-separate border-spacing-1 text-center text-body-sm">
              <caption className="sr-only">주차별 재방문 표</caption>
              <thead>
                <tr className="text-caption font-semibold text-muted-foreground">
                  <th scope="col" className="px-2 py-1.5 text-left">
                    처음 온 주
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
