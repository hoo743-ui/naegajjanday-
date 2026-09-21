/** 이벤트 카탈로그 — 이름과 속성을 여기서만 정의한다. track() 은 이 타입으로만 호출할 수 있다. */
export interface AnalyticsEvents {
  plan_started: { entry: "landing_hero" | "landing_cta" | "nav" | "result_reroll" | "direct" | "chat" };
  plan_step_completed: { step: 1 | 2 | 3 | 4; step_name: "region" | "purpose" | "budget" | "taste"; value?: string };
  plan_abandoned: { step: number };
  course_generate_requested: {
    region?: string;
    purpose: string;
    party_size: number;
    budget_total: number;
    transport: string;
  };
  course_generated: {
    course_id: string;
    purpose: string;
    budget_total: number;
    price: number;
    stops: number;
    candidates?: number;
    latency_ms?: number;
  };
  course_generate_failed: { code: string; purpose?: string; budget_total?: number };
  course_viewed: { course_id: string; label: string; shared: boolean };
  course_saved: { course_id: string; price: number };
  alternative_selected: { course_id: string; label: string };
  stop_swapped: { course_id: string; position: number; strategy: string };
  stop_reason_opened: { course_id: string; position: number };
  /** 스톱 카드에서 지도 앱의 장소 페이지(실제 사진·메뉴)로 나간 클릭 */
  place_link_clicked: { course_id: string; position: number; to: "kakaomap" | "roadview" };
  /** from_shared: 친구가 짠 코스에서 "이 코스로 내 코스 만들기"를 누른 경우 */
  /** focus: 동네 명물을 골라(또는 빼고) 다시 짠 경우 그 말 */
  reroll_clicked: { course_id: string; from_shared?: boolean; focus?: string };
  stop_reordered: { course_id: string; position: number; delta: -1 | 1 };
  /** 장소 이름을 눌러 메뉴 · 사진 · 영업시간 시트를 연 경우 */
  place_sheet_opened: { course_id: string; position: number };
  /** "예산을 바꾸면?": 그 예산으로 짜 본 것 / 그 코스를 열어 본 것 */
  budget_whatif_tried: { budget_total: number; from_budget: number };
  budget_whatif_opened: { course_id: string; budget_total: number };
  settlement_copied: { party_size: number; total: number };
  /** "이런 건 어때요?"에서 권한 곳을 코스에 넣었다 */
  hot_place_opened: { region: string; place_id: string; rank: number };
  suggestion_added: { course_id: string; role: string; price: number };
  stay_clicked: { day: number };
  performance_clicked: { performance_id: string };
  course_feedback_sent: { course_id: string; rating: number };
  banner_clicked: { banner_id: string; placement: string };
  share_clicked: { course_id: string; method: "web_share" | "clipboard" };
  event_clicked: { event_id: string; from: "course" | "explore" };
  /** 둘러보기 카드 → 상세 시트 */
  attraction_opened: { attraction_id: string; type: string };
  /** 상세 시트에서 지도·길찾기·검색으로 나간 클릭 */
  attraction_link_clicked: { attraction_id: string; to: "map" | "route" | "search" };
  explore_filtered: { type: string; region?: string };
  chat_message_sent: { session_id: string; length: number; suggested: boolean };
  chat_course_received: { session_id: string; course_id: string };
  login_clicked: { provider: "kakao" | "naver" | "google" };
  error_shown: { code: string; where: string };
}

export type AnalyticsEventName = keyof AnalyticsEvents;

export interface AnalyticsAdapter {
  name: string;
  init(): Promise<void> | void;
  track(event: string, props: Record<string, unknown>): void;
  page(path: string, props?: Record<string, unknown>): void;
  identify?(userId: string, traits?: Record<string, unknown>): void;
  reset?(): void;
}
