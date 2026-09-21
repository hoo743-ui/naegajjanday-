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
