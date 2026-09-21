"use client";

/**
 * Recharts 얇은 래퍼. 규칙:
 *  - 색은 브랜드 토큰 순서(SERIES)로 고정 → 화면마다 같은 계열이 같은 색
 *  - 모든 차트는 role="img" + aria-label(요약) 을 가진 figure 로 감싼다
 *  - 모션 최소화 설정이면 애니메이션을 끈다
 */
import type { ReactNode } from "react";
import { useReducedMotion } from "motion/react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { num } from "@/lib/format";

export const SERIES = ["#2F6BEA", "#8E8BFF", "#E0457F", "#B7791F", "#12805C"] as const;
const AXIS = { fontSize: 12, fill: "#5F6C87" } as const;
const GRID = "#E6ECF6";

export interface SeriesDef {
  key: string;
  label: string;
  color?: string;
}

type Row = Record<string, string | number>;

interface BaseProps {
  data: Row[];
  xKey: string;
  series: SeriesDef[];
  /** 스크린리더용 요약. 예: "최근 30일 DAU 추이" */
  label: string;
  height?: number;
  format?: (value: number) => string;
  xFormat?: (value: string) => string;
}

function Frame({ label, height, children }: { label: string; height: number; children: ReactNode }) {
  return (
    <figure role="img" aria-label={label} className="m-0 w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </figure>
  );
}

const tooltipStyle = {
  contentStyle: { borderRadius: 14, border: "1px solid #E6ECF6", boxShadow: "0 12px 32px rgba(72,54,24,.12)", fontSize: 13, fontWeight: 700 },
  labelStyle: { color: "#14213D", fontWeight: 800, marginBottom: 4 },
} as const;

const shortDate = (value: string) => (/^\d{4}-\d{2}-\d{2}/.test(value) ? `${Number(value.slice(5, 7))}/${Number(value.slice(8, 10))}` : value);

export function TrendChart({ data, xKey, series, label, height = 260, format = num, xFormat = shortDate, area = false }: BaseProps & { area?: boolean }) {
  const reduced = useReducedMotion() ?? false;
  const common = (
    <>
      <CartesianGrid stroke={GRID} vertical={false} />
      <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} tickFormatter={xFormat} minTickGap={24} />
      <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickFormatter={(v: number) => format(v)} />
      <Tooltip {...tooltipStyle} formatter={(value) => format(Number(value))} labelFormatter={(v) => xFormat(String(v))} />
      {series.length > 1 ? <Legend iconType="circle" wrapperStyle={{ fontSize: 12.5, fontWeight: 700 }} /> : null}
    </>
  );
  return (
    <Frame label={label} height={height}>
      {area ? (
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          {common}
          {series.map((s, i) => {
            const color = s.color ?? SERIES[i % SERIES.length];
            return <Area key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={color} fill={color} fillOpacity={0.14} strokeWidth={2.5} isAnimationActive={!reduced} />;
          })}
        </AreaChart>
      ) : (
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          {common}
          {series.map((s, i) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color ?? SERIES[i % SERIES.length]} strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} isAnimationActive={!reduced} />
          ))}
        </LineChart>
      )}
    </Frame>
  );
}

export function BarsChart({ data, xKey, series, label, height = 260, format = num, xFormat = shortDate, stacked = false, horizontal = false }: BaseProps & { stacked?: boolean; horizontal?: boolean }) {
  const reduced = useReducedMotion() ?? false;
  return (
    <Frame label={label} height={height}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap="28%">
        <CartesianGrid stroke={GRID} vertical={horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v: number) => format(v)} />
            <YAxis type="category" dataKey={xKey} tick={AXIS} tickLine={false} axisLine={false} width={84} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} tickFormatter={xFormat} minTickGap={16} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickFormatter={(v: number) => format(v)} />
          </>
        )}
        <Tooltip {...tooltipStyle} cursor={{ fill: "rgba(47,107,234,.06)" }} formatter={(value) => format(Number(value))} />
        {series.length > 1 ? <Legend iconType="circle" wrapperStyle={{ fontSize: 12.5, fontWeight: 700 }} /> : null}
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} stackId={stacked ? "a" : undefined} fill={s.color ?? SERIES[i % SERIES.length]} radius={stacked ? 0 : horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]} isAnimationActive={!reduced} />
        ))}
      </BarChart>
    </Frame>
  );
}

export function DonutChart({ data, nameKey, valueKey, label, height = 240, format = num }: { data: Row[]; nameKey: string; valueKey: string; label: string; height?: number; format?: (v: number) => string }) {
  const reduced = useReducedMotion() ?? false;
  return (
    <Frame label={label} height={height}>
      <PieChart>
        <Pie data={data} dataKey={valueKey} nameKey={nameKey} innerRadius="58%" outerRadius="86%" paddingAngle={2} stroke="#fff" strokeWidth={2} isAnimationActive={!reduced}>
          {data.map((row, i) => (
            <Cell key={String(row[nameKey])} fill={SERIES[i % SERIES.length]} />
          ))}
        </Pie>
        <Tooltip {...tooltipStyle} formatter={(value) => format(Number(value))} />
        <Legend iconType="circle" wrapperStyle={{ fontSize: 12.5, fontWeight: 700 }} />
      </PieChart>
    </Frame>
  );
}

/** 0~1 값을 파란 농도로. 히트맵·코호트 표의 셀 배경에 쓴다. 0.55 이상이면 글자를 흰색으로. */
export function heatStyle(ratio: number): { background: string; color: string } {
  const t = Math.max(0, Math.min(1, ratio));
  return { background: `rgba(47,107,234,${(0.06 + t * 0.86).toFixed(3)})`, color: t >= 0.55 ? "#fff" : "#14213D" };
}
