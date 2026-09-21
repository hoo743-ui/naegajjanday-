import { ApiError } from "@/lib/api/client";
import { won } from "@/lib/format";

export type JjaniMood = "hi" | "think" | "done" | "wink" | "sorry" | "cheers";

export const MOOD_LABEL: Record<JjaniMood, string> = {
  hi: "손을 흔들며 인사하는 짠이",
  think: "고민하는 표정의 짠이",
  done: "두 팔을 들고 기뻐하는 짠이",
  wink: "동전을 들고 윙크하는 짠이",
  sorry: "미안해하는 표정의 짠이",
  cheers: "잔을 들고 건배하는 짠이",
};

export interface MascotCopy {
  mood: JjaniMood;
  title: string;
  description: string;
  /** 재시도 버튼을 보여줄지 */
  retry: boolean;
  /** 재시도 대신/함께 제안할 이동 */
  action?: { label: string; href: string };
}

type CopyFactory = (error: ApiError) => MascotCopy;

/** API `code` → 짠이 표정 + 문구. 짠이는 혼내지 않는다: 원인보다 다음 행동을 말한다. */
const ERROR_COPY: Record<string, CopyFactory> = {
  BUDGET_TOO_LOW: (e) => {
    const min = typeof e.meta.min_budget === "number" ? e.meta.min_budget : null;
    return {
      mood: "sorry",
      title: "괜찮아요, 조금만 더 맞춰 볼까요?",
      description: min
        ? `이 조건에서는 최소 ${won(min)}이 필요해요. 예산을 조금 올리거나 인원을 조정해 보세요.`
        : (e.detail ?? "이 예산으로는 코스를 짜기 어려워요. 예산을 조금만 올려 보세요."),
      retry: false,
      action: { label: "예산 다시 정하기", href: "/plan" },
    };
  },
  REGION_NOT_FOUND: () => ({
    mood: "think",
    title: "그 동네는 아직 지도에 없어요",
    description: "다른 지역을 골라 주세요. 새 지역은 계속 추가하고 있어요.",
    retry: false,
    action: { label: "지역 다시 고르기", href: "/plan" },
  }),
  REGION_NOT_READY: () => ({
    mood: "think",
    title: "이 동네는 지금 장소를 모으는 중이에요",
    description: "수집이 끝나면 바로 열릴 거예요. 그동안 가까운 다른 지역은 어때요?",
    retry: false,
    action: { label: "다른 지역 보기", href: "/plan" },
  }),
  PURPOSE_NOT_FOUND: () => ({
    mood: "think",
    title: "그 약속 종류는 아직 준비 중이에요",
    description: "지금 고를 수 있는 목적 중에서 하나를 골라 주세요.",
    retry: false,
    action: { label: "목적 다시 고르기", href: "/plan" },
  }),
  // 같은 조건으로 다시 눌러도 결과는 같다 → 재시도 대신 조건을 바꾸게 한다
  NO_COURSE_AVAILABLE: (e) => ({
    mood: "sorry",
    title: "이 조건으로는 코스가 안 나와요",
    description: e.detail ?? "예산을 조금 올리거나 만나는 시간을 바꾸면 짤 수 있어요.",
    retry: false,
    action: { label: "조건 바꿔서 다시 짜기", href: "/plan" },
  }),
  SLOT_EMPTY: (e) => ({
    mood: "sorry",
    title: "갈 만한 곳이 모자라요",
    description: e.detail ?? "예산을 조금 올리거나 만나는 시간을 바꾸면 짤 수 있어요.",
    retry: false,
    action: { label: "조건 바꿔서 다시 짜기", href: "/plan" },
  }),
  SWAP_NOT_POSSIBLE: () => ({
    mood: "sorry",
    title: "바꿀 만한 곳을 찾지 못했어요",
    description: "이 기준으로는 예산 안에서 대신할 곳이 없어요. 다른 기준으로 바꿔 보세요.",
    retry: false,
  }),
  // 서버 설정 이야기는 사용자에게 하지 않는다. 같은 일을 할 수 있는 길(코스 짜기)로 안내한다.
  // 503 = 이 환경에 대화 기능이 없음(다시 눌러도 같다) · 그 밖 = 대화 도중 답이 끊김(다시 보내면 된다)
  LLM_UNAVAILABLE: (e) =>
    e.status === 503
      ? {
          mood: "sorry",
          title: "짠이와 대화는 준비 중이에요",
          description: "코스는 지금도 바로 짤 수 있어요. 지역 · 목적 · 예산만 알려 주세요.",
          retry: false,
          action: { label: "코스 짜러 가기", href: "/plan" },
        }
      : {
          mood: "sorry",
          title: "짠이가 답을 끝까지 못 했어요",
          description: "한 번만 다시 보내 주세요. 급하면 코스 짜기로 바로 만들 수 있어요.",
          retry: true,
          action: { label: "코스 짜러 가기", href: "/plan" },
        },
  COURSE_NOT_FOUND: () => ({
    mood: "sorry",
    title: "이 코스는 사라졌어요",
    description: "저장하지 않은 코스는 24시간 뒤에 지워져요. 새로 짜 드릴게요.",
    retry: false,
    action: { label: "새 코스 짜기", href: "/plan" },
  }),
  NOT_FOUND: () => ({
    mood: "think",
    title: "찾는 게 여기 없어요",
    description: "주소가 바뀌었거나 삭제됐을 수 있어요.",
    retry: false,
    action: { label: "홈으로", href: "/" },
  }),
  UNAUTHORIZED: () => ({
    mood: "hi",
    title: "로그인이 필요해요",
    description: "코스를 저장하고 다시 꺼내 보려면 로그인해 주세요.",
    retry: false,
    action: { label: "로그인하기", href: "/login" },
  }),
  FORBIDDEN: () => ({
    mood: "sorry",
    title: "여긴 들어올 수 없어요",
    description: "이 화면은 권한이 있는 계정만 볼 수 있어요.",
    retry: false,
    action: { label: "홈으로", href: "/" },
  }),
  RATE_LIMITED: (e) => ({
    mood: "sorry",
    title: "짠이가 잠깐 숨 좀 돌릴게요",
    description: e.retryAfter
      ? `요청이 많았어요. ${Math.ceil(e.retryAfter / 60)}분 뒤에 다시 시도해 주세요.`
      : "요청이 많았어요. 잠시 뒤에 다시 시도해 주세요.",
    retry: true,
  }),
  VALIDATION_ERROR: (e) => ({
    mood: "think",
    title: "입력을 한 번만 더 봐 주세요",
    description: e.detail ?? "빠졌거나 맞지 않는 값이 있어요.",
    retry: false,
  }),
  NETWORK_ERROR: () => ({
    mood: "sorry",
    title: "서버에 닿지 못했어요",
    description: "인터넷 연결을 확인하고 다시 시도해 주세요.",
    retry: true,
  }),
  TIMEOUT: () => ({
    mood: "think",
    title: "생각보다 오래 걸리네요",
    description: "잠시 뒤에 다시 시도해 주세요.",
    retry: true,
  }),
  INTERNAL_ERROR: () => ({
    mood: "sorry",
    title: "앗, 짠이가 실수했어요",
    description: "문제가 생겼어요. 잠시 뒤에 다시 시도해 주세요.",
    retry: true,
  }),
};

const FALLBACK: CopyFactory = (e) => ({
  mood: "sorry",
  title: "앗, 문제가 생겼어요",
  description: e.detail ?? e.message ?? "잠시 뒤에 다시 시도해 주세요.",
  retry: true,
});

export function mascotCopyForError(error: unknown): MascotCopy & { code: string; traceId?: string } {
  const apiError = ApiError.from(error);
  const copy = (ERROR_COPY[apiError.code] ?? FALLBACK)(apiError);
  return { ...copy, code: apiError.code, traceId: apiError.traceId };
}

/** 예산 수준에 따른 짠이 한마디 (plan 3단계). ratio = 1인 예산 / 목적의 typical 예산 */
export function budgetReaction(perPerson: number, range?: { min: number; max: number; typical?: number }): {
  mood: JjaniMood;
  line: string;
} {
  if (!range) return { mood: "hi", line: "얼마 쓸 거예요? 편하게 정해 주세요." };
  const typical = range.typical ?? (range.min + range.max) / 2;
  if (perPerson < range.min) {
    return { mood: "sorry", line: `조금 빠듯해요. 1인 ${won(range.min)}부터 코스가 나와요.` };
  }
  if (perPerson < typical * 0.8) {
    return { mood: "think", line: "알뜰 코스로 짜 볼게요. 무료 산책 코스를 섞으면 충분해요." };
  }
  if (perPerson <= typical * 1.3) {
    return { mood: "wink", line: "딱 좋아요! 식사에 카페, 놀거리까지 넉넉해요." };
  }
  if (perPerson <= range.max) {
    return { mood: "done", line: "오, 오늘 제대로 즐기는 날이네요. 분위기 좋은 곳으로 골라 볼게요." };
  }
  return { mood: "cheers", line: "예산이 아주 넉넉해요. 남는 돈은 남는 대로 알려 드릴게요." };
}
