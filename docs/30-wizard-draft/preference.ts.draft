/**
 * 위저드의 세 질문 (docs/30): 사용자는 적게 말하고, 해석은 API 의 선호 해석 레이어가 한다
 * (`POST /v1/courses/interpret`). 여기는 선택지와 화면 문구, 그리고 API 가 늦거나 실패할 때 쓸 같은 모양의 요약.
 */
export type Pace = "relaxed" | "packed" | "foodie" | "special";
export type MoveStyle = "local" | "balanced" | "explorer";
export type Wish = "night" | "walk" | "exhibition" | "value" | "romantic";

export const PACE_LABEL: Record<Pace, string> = {
  relaxed: "여유로운 하루",
  packed: "알찬 하루",
  foodie: "맛있는 거 중심",
  special: "특별한 경험",
};
export const MOVE_LABEL: Record<MoveStyle, string> = {
  local: "가까운 곳 위주",
  balanced: "적당히 이동",
  explorer: "좋은 곳이면 조금 멀리도",
};
export const WISH_LABEL: Record<Wish, string> = {
  night: "야경 포함",
  walk: "산책 넣기",
  exhibition: "전시 · 공연 넣기",
  value: "가성비 있게",
  romantic: "로맨틱한 분위기",
};

export interface SummaryLine {
  kind: "pace" | "move" | "wish" | "detail" | "budget";
  key: string;
  text: string;
}

export interface InterpretInput {
  pace: Pace[];
  move_style: MoveStyle;
  wishes: Wish[];
  liked_tags: string[];
  disliked_tags: string[];
  budget_total: number;
  party_size: number;
}

/** API 와 같은 규칙의 요약 (API 가 답하기 전에도, 실패해도 확인 화면은 비지 않는다) */
export function localSummary(v: InterpretInput): SummaryLine[] {
  const lines: SummaryLine[] = [];
  lines.push(v.pace.length ? { kind: "pace", key: v.pace[0]!, text: v.pace.map((p) => PACE_LABEL[p]).join(" · ") } : { kind: "pace", key: "auto", text: "짠이가 알아서 균형 있게" });
  lines.push({ kind: "move", key: v.move_style, text: MOVE_LABEL[v.move_style] });
  for (const w of v.wishes) lines.push({ kind: "wish", key: w, text: WISH_LABEL[w] });
  if (v.liked_tags.length) lines.push({ kind: "detail", key: "liked", text: `고른 취향 ${v.liked_tags.length}가지 더 반영` });
  if (v.disliked_tags.length) lines.push({ kind: "detail", key: "avoid", text: `피하고 싶은 것 ${v.disliked_tags.length}가지는 빼고` });
  const each = v.party_size > 1 ? ` · 1인 ${Math.floor(v.budget_total / v.party_size).toLocaleString("ko-KR")}원` : "";
  lines.push({ kind: "budget", key: "budget", text: `${v.budget_total.toLocaleString("ko-KR")}원 ${v.wishes.includes("value") ? "아껴서" : "안에서 안정적으로"}${each}` });
  return lines;
}
