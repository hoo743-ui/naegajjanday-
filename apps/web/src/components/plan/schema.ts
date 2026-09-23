import { z } from "zod";
import { isPast } from "./meet-time";

export const planSchema = z
  .object({
    region: z.string().min(1, "어디서 놀지 골라 주세요"),
    purpose: z.string().min(1, "어떤 약속인지 골라 주세요"),
    /** 함께 고른 다른 목적 (최대 2) */
    purposes_extra: z.array(z.string()).max(2),
    /** 먼저 들를 동네들(방문 순서). 마지막 동네는 region 이다. 비어 있으면 한 동네 코스 */
    regions_before: z.array(z.string()).max(2),
    party_size: z.number().int().min(1, "최소 1명이에요").max(20, "20명까지 짤 수 있어요"),
    budget_total: z.number().int().min(5000, "예산은 5,000원부터예요").max(5_000_000, "예산이 너무 커요"),
    liked_tags: z.array(z.string()),
    disliked_tags: z.array(z.string()),
    transport: z.enum(["walk", "transit", "car"]),
    /** efficient = 가깝고 알뜰하게 · fun = 재미 우선. docs/30 부터는 "어떤 하루"에서 읽힌다(특별한 경험 → fun) */
    style: z.enum(["efficient", "fun"]),
    /** 어떤 하루 (docs/30): 0~2개. 비워 두면 짠이가 균형 있게 */
    pace: z.array(z.enum(["relaxed", "packed", "foodie", "special"])).max(2),
    /** 얼마나 이동해도 괜찮은지: 거리 필터가 아니라 엔진의 이동 선호 (docs/29) */
    move_style: z.enum(["local", "balanced", "explorer"]),
    /** 꼭 반영하고 싶은 것 (선택) */
    wishes: z.array(z.enum(["night", "walk", "exhibition", "value", "romantic"])),
    /** 꼭 넣을 동네 명물. "" = 짠이가 알아서(가장 뚜렷한 명물), "-" = 넣지 않기 */
    focus: z.string().max(12),
    /** 술 한잔 포함: 저녁 5시 이후에 술집 자리를 꼭 넣는다 */
    with_bar: z.boolean(),
    /** 야구 보러 가요: 동네에 1군 구장이 있으면 코스에 넣는다 (경기 일정은 직접 확인) */
    with_baseball: z.boolean(),
    /** 비 오는 날: 실내 위주로, 산책 대신 전시 · 실내 놀거리 */
    rainy: z.boolean(),
    /** 몇 박. 0 = 당일 */
    nights: z.number().int().min(0).max(3),
    /** "" = 오늘, 아니면 "YYYY-MM-DD" */
    meet_day: z.string().regex(/^$|^\d{4}-\d{2}-\d{2}$/, "날짜 형식을 확인해 주세요"),
    /** "" = 지금 출발(오늘만), 아니면 "HH:mm" */
    start_time: z.string().regex(/^$|^([01]\d|2[0-3]):[0-5]\d$/, "시간 형식을 확인해 주세요"),
    /** 함께 보내는 시간(분). null = 짠이에게 맡기기 */
    duration_min: z.number().int().min(60).max(960).nullable(),
  })
  // 지난 시각으로 코스를 짜면 영업시간·혼잡도 계산이 전부 틀어진다
  .refine((v) => !isPast(v, new Date()), { path: ["start_time"], message: "이미 지난 시간이에요. 시각을 다시 골라 주세요" });

export type PlanValues = z.infer<typeof planSchema>;

export const PLAN_DEFAULTS: PlanValues = {
  region: "",
  purpose: "",
  purposes_extra: [],
  regions_before: [],
  party_size: 2,
  budget_total: 40000,
  liked_tags: [],
  disliked_tags: [],
  transport: "walk",
  style: "efficient",
  pace: [],
  move_style: "balanced",
  wishes: [],
  focus: "",
  with_bar: false,
  with_baseball: false,
  rainy: false,
  nights: 0,
  meet_day: "",
  start_time: "",
  duration_min: null,
};

export const STEPS = [
  { key: "region", title: "지역", question: "오늘 어디서 만나요?", fields: ["region", "regions_before"] },
  { key: "purpose", title: "목적", question: "오늘은 어떤 약속인가요?", fields: ["purpose", "purposes_extra"] },
  { key: "budget", title: "인원 · 예산 · 시간", question: "몇 명이서, 얼마로, 언제 만나요?", fields: ["party_size", "budget_total", "nights", "meet_day", "start_time", "duration_min"] },
  // 4단계는 그대로 (docs/32 B §10): 취향 단계 안에 짧은 질문 셋(어떤 하루 · 얼마나 이동 · 꼭 원하는 것), 세부 태그는 "더 자세히" 안에
  { key: "taste", title: "취향", question: "마지막으로 취향만 알려 주세요", fields: ["pace", "style", "move_style", "transport", "wishes", "focus", "rainy", "with_bar", "with_baseball", "liked_tags", "disliked_tags"] },
] as const satisfies readonly { key: string; title: string; question: string; fields: readonly (keyof PlanValues)[] }[];

export type StepKey = (typeof STEPS)[number]["key"];
