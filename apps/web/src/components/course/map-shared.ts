import type { Stop } from "@/lib/api/types";

/**
 * 지도 공통: 번호 핀 · 겹친 핀 펼치기 · 경로를 구간별로 나누기.
 * Leaflet(OSM) 지도와 카카오 지도가 같은 핀 · 같은 규칙을 쓴다 — 키를 넣어 지도가 바뀌어도 코스가 똑같이 읽혀야 한다.
 */
export const escapeHtml = (text: string) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** 물방울 핀: 끝점이 정확히 좌표를 가리키고, 번호가 지도에서 가장 먼저 읽힌다. 이름표는 아래에 보조로 단다. */
export interface Spread {
  dx: number;
  dy: number;
  crowded: boolean;
}

export function pinHtml(position: number, name: string, color: string, active: boolean, spread: Spread) {
  const { dx, dy, crowded } = spread;
  const classes = ["jj-pin", active ? "is-active" : "", crowded && !active ? "is-crowded" : ""].filter(Boolean).join(" ");
  const moved = dx !== 0 || dy !== 0;
  // 펼친 핀은 제자리에 점을 남기고 선으로 잇는다 → 번호는 떨어져 있어도 "정확히 어디인지"는 잃지 않는다
  const leader = moved
    ? `<span class="jj-pin-stem" style="width:${Math.hypot(dx, dy).toFixed(1)}px;transform:rotate(${Math.atan2(dy, dx).toFixed(4)}rad)"></span><span class="jj-pin-anchor"></span>`
    : "";
  return `
    <div class="${classes}" style="--pin:${color};--dx:${dx}px;--dy:${dy}px">
      ${leader}
      <span class="jj-pin-drop"><b>${position}</b></span>
      <span class="jj-pin-label">${escapeHtml(name)}</span>
    </div>`;
}

// 핀이 화면에서 차지하는 상자(선택된 핀 58px 기준 + 여유). 두 핀의 상자가 겹치면 "묻힌다".
const PIN_BOX_W = 64;
const PIN_BOX_H = 74;
const FAN_GAP = 74; // 펼쳤을 때 이웃 핀 사이 간격 (핀 너비 46px + 숨 쉴 틈)

/**
 * 겹치는 핀을 항상 펼쳐 둔다(Spiderfy 방식이되, 눌러야 펼쳐지는 게 아니라 상시).
 * 구글맵처럼 덜 중요한 마커를 숨기는 방식은 쓸 수 없다 — 코스는 모든 순번이 보여야 한다.
 * 줌을 당겨 떼는 방식도 한계가 있다: 바로 옆 가게(20m)는 최대 줌에서도 40px 로 핀보다 좁다.
 *
 * 1) 핀 상자가 겹치는 것끼리 무리로 묶고(가로만이 아니라 세로 겹침도 본다)
 * 2) 무리의 중심 위쪽에 순번 순서대로 부채꼴로 놓는다 → 왼쪽부터 1, 2, 3 … 으로 읽힌다.
 */
export function spreadOverlaps(points: { x: number; y: number }[]): Spread[] {
  const group = points.map((_, i) => i);
  const find = (i: number): number => (group[i] === i ? i : (group[i] = find(group[i]!)));
  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const overlapX = Math.abs(points[i]!.x - points[j]!.x) < PIN_BOX_W;
      const overlapY = Math.abs(points[i]!.y - points[j]!.y) < PIN_BOX_H;
      if (overlapX && overlapY) group[find(j)] = find(i);
    }
  }
  const members = new Map<number, number[]>();
  points.forEach((_, i) => members.set(find(i), [...(members.get(find(i)) ?? []), i]));
  const out: Spread[] = points.map(() => ({ dx: 0, dy: 0, crowded: false }));
  for (const ids of members.values()) {
    if (ids.length < 2) continue;
    const cx = ids.reduce((acc, id) => acc + points[id]!.x, 0) / ids.length;
    const cy = ids.reduce((acc, id) => acc + points[id]!.y, 0) / ids.length;
    // 부채꼴: 핀 사이 호의 길이가 FAN_GAP 이 되도록 반지름을 정한다 (위쪽 ±55° 안에서)
    const span = Math.min((110 * Math.PI) / 180, (ids.length - 1) * 0.72);
    const radius = Math.max(58, (FAN_GAP * (ids.length - 1)) / Math.max(span, 0.01));
    ids.forEach((id, k) => {
      const angle = ids.length === 1 ? 0 : -span / 2 + (span * k) / (ids.length - 1);
      const tx = cx + radius * Math.sin(angle);
      const ty = cy - radius * Math.cos(angle) + radius * 0.55; // 무리 중심 바로 위에 호가 걸치게 조금 내린다
      out[id] = { dx: Math.round(tx - points[id]!.x), dy: Math.round(ty - points[id]!.y), crowded: true };
    });
  }
  return out;
}

export type LatLngTuple = [number, number];

// ── 경로 그리기 ───────────────────────────────────────────────
// 라우터가 준 선을 그대로 한 줄로 그리면 세 군데서 읽기 어려워진다:
//  1) 같은 길을 갔다가 되돌아오는 코스는 뒤 구간이 앞 구간을 덮는다 → 구간마다 **진행 방향의 오른쪽**으로 비켜 그린다
//     (도로의 우측통행과 같다: 왕복이면 저절로 두 줄로 갈라지고, 어느 쪽이 가는 길인지도 읽힌다).
//  2) 선은 도로 위에서 끝나고 핀은 건물 안에 있다 → 그 사이를 점선으로 잇는다 (점선 = 길찾기가 아니라 "문까지").
//  3) 어느 방향으로 얼마나 걷는지가 선만으로는 안 보인다 → 구간 가운데에 방향과 시간을 단다.
// 선을 매끈하게 다듬거나 돌아가는 길을 직선으로 바꾸지는 않는다 — 없는 길을 있는 것처럼 보이게 된다.
export interface Pt {
  x: number;
  y: number;
}

export interface DrawLeg {
  coords: LatLngTuple[];
  /** 실제 보행 경로인가. 아니면(라우터 실패 · 대중교통/차 구간) 두 지점을 점선으로만 잇는다 */
  routed: boolean;
  label: string;
}

/** 구간별 경로. 도보 구간은 라우터의 구간 경로를, 그 밖(대중교통 · 차 · 라우터 실패)은 두 지점을 곧게 잇는다. */
export function legsOf(
  stops: Stop[],
  route: { source: "osrm" | "straight"; coordinates: LatLngTuple[]; legs: { duration_min: number; coordinates?: LatLngTuple[] }[] } | undefined,
  labelOf: (mode: NonNullable<Stop["from_prev"]>["mode"], minutes: number) => string,
): DrawLeg[] {
  const real = route?.source === "osrm" && route.coordinates.length > 1;
  // 구간 경로가 없는 응답(이전 버전 · 캐시)은 전체 선을 스톱 가까운 꼭짓점에서 끊어 쓴다
  const guessed = real && route.legs.some((leg) => (leg.coordinates?.length ?? 0) < 2) ? splitByStops(route.coordinates, stops) : null;
  return stops.slice(1).map((stop, i) => {
    const from = stops[i]!;
    const mode = stop.from_prev?.mode ?? "walk";
    const walked = real && mode === "walk";
    const path = walked ? (guessed ? guessed[i] : route.legs[i]?.coordinates) : undefined;
    const minutes = (walked ? route.legs[i]?.duration_min : undefined) ?? stop.from_prev?.travel_min ?? 0;
    return {
      coords: path && path.length > 1 ? path : [[from.place.lat, from.place.lng], [stop.place.lat, stop.place.lng]],
      routed: Boolean(path && path.length > 1),
      label: minutes > 0 ? labelOf(mode, minutes) : "",
    };
  });
}

const LANE_PX = 4; // 선 굵기 6px → 왕복 구간이 2px 틈을 두고 나란히 간다
const MIN_GAP_PX = 10; // 선 끝과 핀 사이가 이보다 멀 때만 점선으로 잇는다
const MIN_CHIP_LEG_PX = 110; // 이보다 짧은 구간에는 표시를 달지 않는다 (핀에 묻힌다)
const CHIP_CLEARANCE_PX = 52;

/** 화면 좌표의 선을 진행 방향 오른쪽으로 px 만큼 옮긴다. 꺾이는 곳은 이음매를 맞추고, 되돌아오는 곳(U턴)은 각지게 돈다. */
export function offsetRight(points: Pt[], px: number): Pt[] {
  const line = points.filter((p, i) => i === 0 || Math.hypot(p.x - points[i - 1]!.x, p.y - points[i - 1]!.y) > 0.5);
  if (line.length < 2) return line;
  // 화면은 y 가 아래로 자란다 → 진행 방향 (dx, dy) 의 오른쪽은 (-dy, dx)
  const normals = line.slice(1).map((p, i) => {
    const dx = p.x - line[i]!.x;
    const dy = p.y - line[i]!.y;
    const len = Math.hypot(dx, dy);
    return { x: -dy / len, y: dx / len };
  });
  const out: Pt[] = [];
  line.forEach((p, i) => {
    const before = normals[i - 1];
    const after = normals[i];
    if (!before || !after) {
      const n = (before ?? after)!;
      out.push({ x: p.x + n.x * px, y: p.y + n.y * px });
      return;
    }
    const dot = before.x * after.x + before.y * after.y;
    if (dot < -0.2) {
      // 거의 되돌아가는 꺾임: 이음매가 무한히 뻗으므로 두 점으로 나눠 돈다
      out.push({ x: p.x + before.x * px, y: p.y + before.y * px }, { x: p.x + after.x * px, y: p.y + after.y * px });
      return;
    }
    const mx = before.x + after.x;
    const my = before.y + after.y;
    const mlen = Math.hypot(mx, my);
    const scale = px / Math.max(0.5, (mx / mlen) * before.x + (my / mlen) * before.y); // 이음매는 최대 2배까지만
    out.push({ x: p.x + (mx / mlen) * scale, y: p.y + (my / mlen) * scale });
  });
  return out;
}

export interface LegLayout {
  line: Pt[];
  /** 선의 양 끝 ↔ 실제 지점. 충분히 떨어져 있을 때만 */
  connectors: [Pt, Pt][];
  chip: (Pt & { angle: number }) | null;
}

/** 한 구간을 화면에 어떻게 놓을지: 비켜 그린 선 · 핀까지의 점선 · 방향/시간 표시 자리(핀에서 가장 먼 곳) */
export function layoutLeg(path: Pt[], from: Pt, to: Pt, pins: Pt[]): LegLayout {
  const line = offsetRight(path, LANE_PX);
  if (line.length < 2) return { line, connectors: [], chip: null };
  const gap = (a: Pt, b: Pt) => Math.hypot(a.x - b.x, a.y - b.y);
  const connectors: [Pt, Pt][] = [];
  if (gap(from, line[0]!) > MIN_GAP_PX) connectors.push([from, line[0]!]);
  if (gap(to, line[line.length - 1]!) > MIN_GAP_PX) connectors.push([line[line.length - 1]!, to]);

  const lengths = line.slice(1).map((p, i) => gap(p, line[i]!));
  const total = lengths.reduce((a, b) => a + b, 0);
  let chip: LegLayout["chip"] = null;
  if (total >= MIN_CHIP_LEG_PX) {
    let best = 0;
    for (const t of [0.5, 0.38, 0.62, 0.28, 0.72]) {
      let remaining = total * t;
      let k = 0;
      while (k < lengths.length - 1 && remaining > lengths[k]!) remaining -= lengths[k++]!;
      const a = line[k]!;
      const b = line[k + 1]!;
      const f = lengths[k]! > 0 ? remaining / lengths[k]! : 0;
      const at = { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f };
      // 핀은 좌표 위로 솟고 이름표는 아래에 달린다 → 핀 몸통의 가운데쯤과의 거리를 본다
      const clearance = Math.min(...pins.map((p) => Math.min(gap(at, { x: p.x, y: p.y - 28 }), gap(at, { x: p.x, y: p.y + 16 }))));
      if (clearance > best) {
        best = clearance;
        chip = { ...at, angle: (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI };
      }
    }
    if (best < CHIP_CLEARANCE_PX) chip = null;
  }
  return { line, connectors, chip };
}

export function legChipHtml(label: string, color: string, angle: number) {
  return `<span class="jj-leg" style="--leg:${color}"><svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true" style="transform:rotate(${angle.toFixed(1)}deg)"><path d="M2 6h7M6 2.5 9.5 6 6 9.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>${escapeHtml(label)}</span>`;
}

/** 한 줄로 온 경로를 스톱에 가장 가까운 꼭짓점에서 끊어 구간별로 나눈다 → 구간마다 도착 스톱의 색으로 칠한다 */
export function splitByStops(path: LatLngTuple[], stops: Stop[]): LatLngTuple[][] {
  if (path.length < 2 || stops.length < 2) return [path];
  const cuts: number[] = [0];
  for (let s = 1; s < stops.length - 1; s += 1) {
    const stop = stops[s]!;
    let best = cuts[cuts.length - 1]!;
    let bestD = Infinity;
    for (let i = best; i < path.length; i += 1) {
      const d = (path[i]![0] - stop.place.lat) ** 2 + (path[i]![1] - stop.place.lng) ** 2;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    cuts.push(best);
  }
  cuts.push(path.length - 1);
  return cuts.slice(1).map((end, i) => path.slice(cuts[i]!, end + 1)).filter((seg) => seg.length > 1);
}
