"use client";

/**
 * 지도 SDK 키가 없을 때 쓰는 약도. 에러 화면이 아니라 "의도된 일러스트"로 보여야 한다.
 * 스톱의 위경도를 등장방형(cos 보정)으로 투영해 컨테이너 크기에 맞추고, 그 위에
 * 장식용 길·녹지(좌표 해시로 결정 → 같은 코스는 항상 같은 그림)와 그라디언트 경로, 번호 핀을 그린다.
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import type { Stop } from "@/lib/api/types";
import { minutes } from "@/lib/format";
import { stopColor } from "./colors";

interface SvgRouteMapProps {
  stops: Stop[];
  activeStop: number | null;
  onSelect: (position: number | null) => void;
}

interface Point {
  x: number;
  y: number;
}

function project(stops: Stop[], width: number, height: number): Point[] {
  if (stops.length === 0) return [];
  const lat0 = stops.reduce((acc, s) => acc + s.place.lat, 0) / stops.length;
  const k = Math.cos((lat0 * Math.PI) / 180);
  const raw = stops.map((s) => ({ x: s.place.lng * k, y: -s.place.lat }));
  const xs = raw.map((p) => p.x);
  const ys = raw.map((p) => p.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const spanX = Math.max(Math.max(...xs) - minX, 1e-5);
  const spanY = Math.max(Math.max(...ys) - minY, 1e-5);
  const padX = Math.min(110, width * 0.2);
  const padTop = Math.min(96, height * 0.24);
  const padBottom = Math.min(64, height * 0.16);
  const scale = Math.min((width - padX * 2) / spanX, (height - padTop - padBottom) / spanY);
  const offX = (width - spanX * scale) / 2;
  const offY = padTop + (height - padTop - padBottom - spanY * scale) / 2;
  return raw.map((p) => ({ x: offX + (p.x - minX) * scale, y: offY + (p.y - minY) * scale }));
}

/** Catmull-Rom → 3차 베지어. 핀 사이를 부드럽게 잇는다. */
function smoothPath(points: Point[]): string {
  const first = points[0];
  if (!first) return "";
  if (points.length === 1) return `M${first.x} ${first.y}`;
  let d = `M${first.x.toFixed(1)} ${first.y.toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i]!;
    const p1 = points[i]!;
    const p2 = points[i + 1]!;
    const p3 = points[i + 2] ?? p2;
    const t = 0.22;
    const c1 = { x: p1.x + (p2.x - p0.x) * t, y: p1.y + (p2.y - p0.y) * t };
    const c2 = { x: p2.x - (p3.x - p1.x) * t, y: p2.y - (p3.y - p1.y) * t };
    d += `C${c1.x.toFixed(1)} ${c1.y.toFixed(1)} ${c2.x.toFixed(1)} ${c2.y.toFixed(1)} ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return d;
}

function seeded(seed: number) {
  let s = seed % 2147483647 || 1;
  return () => ((s = (s * 48271) % 2147483647) - 1) / 2147483646;
}

export function SvgRouteMap({ stops, activeStop, onSelect }: SvgRouteMapProps) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const reduced = useReducedMotion();
  const boxRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 640, h: 480 });

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ w: Math.round(width), h: Math.round(height) });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const points = useMemo(() => project(stops, size.w, size.h), [stops, size]);
  const route = useMemo(() => smoothPath(points), [points]);
  const routeKey = stops.map((s) => s.place.id).join(">");

  const decor = useMemo(() => {
    const seed = Math.abs(Math.round((stops[0]?.place.lat ?? 37.5) * 1e4 + (stops[0]?.place.lng ?? 127) * 1e4));
    const rnd = seeded(seed);
    const { w, h } = size;
    const major = [
      `M-20 ${h * (0.28 + rnd() * 0.1)}L${w + 20} ${h * (0.36 + rnd() * 0.12)}`,
      `M-20 ${h * (0.72 + rnd() * 0.08)}L${w + 20} ${h * (0.64 + rnd() * 0.08)}`,
      `M${w * (0.26 + rnd() * 0.08)} -20L${w * (0.2 + rnd() * 0.1)} ${h + 20}`,
      `M${w * (0.66 + rnd() * 0.08)} -20L${w * (0.74 + rnd() * 0.08)} ${h + 20}`,
    ];
    const minor = Array.from({ length: 7 }, (_, i) =>
      i % 2 ? `M-20 ${h * (0.1 + i * 0.13)}L${w + 20} ${h * (0.1 + i * 0.13 + (rnd() - 0.5) * 0.05)}` : `M${w * (0.08 + i * 0.14)} -20L${w * (0.08 + i * 0.14 + (rnd() - 0.5) * 0.04)} ${h + 20}`,
    );
    return {
      major,
      minor,
      park: { cx: w * (0.72 + rnd() * 0.15), cy: h * (0.22 + rnd() * 0.18), rx: w * 0.16, ry: h * 0.13 },
      park2: { cx: w * (0.12 + rnd() * 0.12), cy: h * (0.78 + rnd() * 0.1), rx: w * 0.12, ry: h * 0.1 },
      water: `M-20 ${h * 0.93}C${w * 0.3} ${h * 0.84} ${w * 0.55} ${h * 1.02} ${w + 20} ${h * 0.88}V${h + 20}H-20Z`,
    };
  }, [size, stops]);

  const summary = stops.map((s) => `${s.position}. ${s.place.name}`).join(", ");

  return (
    <div ref={boxRef} className="relative size-full overflow-hidden bg-[#EAF1FF]">
      <svg viewBox={`0 0 ${size.w} ${size.h}`} width={size.w} height={size.h} className="block size-full" role="group" aria-label={`코스 약도: ${summary || "장소 없음"}`}>
        <defs>
          <linearGradient id={`${uid}-route`} gradientUnits="userSpaceOnUse" x1={points[0]?.x ?? 0} y1={points[0]?.y ?? 0} x2={points[points.length - 1]?.x ?? size.w} y2={points[points.length - 1]?.y ?? 0}>
            <stop offset="0" stopColor="#2F6BEA" />
            <stop offset=".5" stopColor="#8E8BFF" />
            <stop offset="1" stopColor="#FF6FA5" />
          </linearGradient>
          <filter id={`${uid}-shadow`} x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="4" stdDeviation="5" floodColor="#2F50A0" floodOpacity=".28" />
          </filter>
        </defs>

        {/* 바탕: 녹지·물·길 */}
        <g aria-hidden>
          <ellipse {...decor.park} fill="#D9F3E4" />
          <ellipse {...decor.park2} fill="#E1F5EA" />
          <path d={decor.water} fill="#CFE3FF" />
          <g stroke="#fff" strokeWidth="5" fill="none" opacity=".9">
            {decor.minor.map((d) => (
              <path key={d} d={d} />
            ))}
          </g>
          <g stroke="#fff" strokeWidth="13" fill="none" strokeLinecap="round">
            {decor.major.map((d) => (
              <path key={d} d={d} />
            ))}
          </g>
        </g>

        {/* 경로 */}
        {points.length > 1 ? (
          <g aria-hidden>
            <path d={route} fill="none" stroke="#fff" strokeWidth="11" strokeLinecap="round" strokeLinejoin="round" opacity=".95" />
            <motion.path
              key={routeKey}
              d={route}
              fill="none"
              stroke={`url(#${uid}-route)`}
              strokeWidth="6"
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={reduced ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1.4, ease: [0.4, 0, 0.2, 1], delay: 0.25 }}
            />
            <path d={route} fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeDasharray="2 12" className="animate-dash" opacity=".85" />
          </g>
        ) : null}

        {/* 구간 이동시간 */}
        <g aria-hidden fontSize="11.5" fontWeight="800" textAnchor="middle">
          {points.slice(1).map((p, i) => {
            const prev = points[i];
            const leg = stops[i + 1]?.from_prev;
            if (!prev || !leg) return null;
            const mx = (prev.x + p.x) / 2;
            const my = (prev.y + p.y) / 2;
            const label = minutes(leg.travel_min);
            const wLabel = label.length * 9 + 18;
            return (
              <g key={`${mx}-${my}`} transform={`translate(${mx} ${my})`}>
                <rect x={-wLabel / 2} y="-11" width={wLabel} height="22" rx="11" fill="#fff" filter={`url(#${uid}-shadow)`} />
                <text y="4" fill="#34425F">
                  {label}
                </text>
              </g>
            );
          })}
        </g>

        {/* 핀 */}
        {points.map((p, i) => {
          const stop = stops[i];
          if (!stop) return null;
          const on = activeStop === stop.position;
          const color = stopColor(i, stops.length);
          const name = stop.place.name.length > 11 ? `${stop.place.name.slice(0, 10)}…` : stop.place.name;
          const labelW = name.length * 12.5 + 22;
          // 라벨이 화면 밖으로 나가지 않게
          const lx = Math.min(size.w - labelW / 2 - 8, Math.max(labelW / 2 + 8, p.x)) - p.x;
          return (
            <motion.g
              key={stop.place.id}
              initial={reduced ? false : { y: -40, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 14, delay: 0.1 + i * 0.12 }}
            >
              <g
                transform={`translate(${p.x} ${p.y})`}
                tabIndex={0}
                role="button"
                aria-label={`${stop.position}번 ${stop.place.name}`}
                aria-pressed={on}
                onMouseEnter={() => onSelect(stop.position)}
                onMouseLeave={() => onSelect(null)}
                onFocus={() => onSelect(stop.position)}
                onBlur={() => onSelect(null)}
                onClick={() => onSelect(stop.position)}
                className="cursor-pointer outline-none [&:focus-visible_circle.ring]:opacity-100"
              >
                <circle className="ring opacity-0" r="9" cy="0" fill="none" stroke="#4F8CFF" strokeWidth="3" />
                <ellipse cy="2" rx="9" ry="3.5" fill="#14213D" opacity=".18" />
                <g style={{ transform: `scale(${on ? 1.18 : 1})`, transformOrigin: "0 0", transition: "transform .25s cubic-bezier(.2,.8,.2,1)" }} filter={`url(#${uid}-shadow)`}>
                  <path d="M0 0C-5 -10 -18 -18 -18 -31A18 18 0 1 1 18 -31C18 -18 5 -10 0 0Z" fill={color} stroke="#fff" strokeWidth="3.5" />
                  <text y="-25" textAnchor="middle" fontSize="15" fontWeight="800" fill="#fff">
                    {stop.position}
                  </text>
                </g>
                <g transform={`translate(${lx} ${on ? -66 : -60})`} style={{ transition: "transform .25s" }}>
                  <rect x={-labelW / 2} y="-13" width={labelW} height="26" rx="13" fill={on ? "#14213D" : "#fff"} filter={`url(#${uid}-shadow)`} />
                  <text y="4.5" textAnchor="middle" fontSize="12.5" fontWeight="800" fill={on ? "#fff" : "#14213D"}>
                    {name}
                  </text>
                </g>
              </g>
            </motion.g>
          );
        })}
      </svg>
      <p className="glass pointer-events-none absolute right-3 bottom-3 rounded-full px-3 py-1.5 text-[11px] font-bold text-ink-2">약도예요 · 실제 길과는 다를 수 있어요</p>
    </div>
  );
}
