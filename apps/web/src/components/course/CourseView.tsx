"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bookmark, BookmarkCheck, CalendarDays, CalendarRange, Car, Check, Clock, CloudRain, CopyPlus, Footprints, GraduationCap, Maximize2, Minimize2, PartyPopper, RotateCw, Share2, Tent, TrainFront, TriangleAlert, Users, Wallet, X, type LucideIcon } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { ErrorState } from "@/components/mascot/EmptyState";
import { JjaniBubble } from "@/components/mascot/JjaniBubble";
import { JjaniLoader } from "@/components/mascot/JjaniLoader";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { ApiError } from "@/lib/api/client";
import { encodeCampus, useAccessHints, useAlongTheWay, usePlaceSignals, useCourse, useCourseNarrative, useCourseRoute, useGenerateCourse, useReorderStops, useSaveCourse, useSwapStop } from "@/lib/api/hooks";
import type { CourseWarning, GenerateCourseRequest, SwapStrategy } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { clock, dateLabel, transportLabel, won } from "@/lib/format";
import type { Transport } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { mascotCopyForError, type JjaniMood } from "@/lib/mascot-copy";
import { BudgetTools } from "./BudgetTools";
import { DaySummary } from "./DaySummary";
import { LeftoverCard } from "./LeftoverCard";
import { LocalCard } from "./LocalCard";
import { PerformanceCard } from "./PerformanceCard";
import { StayCard } from "./StayCard";
import { VisitedCard } from "./VisitedCard";
import { AlternativeTabs } from "./AlternativeTabs";
import { BudgetBar } from "./BudgetBar";
import { CourseTimeline } from "./CourseTimeline";
import { NearbyEvents } from "./NearbyEvents";
import { ResultHeader } from "./ResultHeader";
import { toMapRoute, type NearbyPin } from "./map-shared";
import { PlaceSheet } from "./PlaceSheet";
import { RouteIssues } from "./RouteIssues";
import { RouteMap } from "./RouteMap";
import { RoutePanel } from "./RoutePanel";
import { RerollSheet, tweaksToRequest, type Tweak } from "./RerollSheet";
import { usePins } from "@/lib/pins";
import { LAST_AREA_KEY } from "@/components/layout/NotificationBell";

const MODE_ICON: Record<Transport, LucideIcon> = { walk: Footprints, transit: TrainFront, car: Car };
const LOADING_STAGES = ["영수증을 꺼내는 중이에요", "지도에 핀을 꽂는 중"];
const FORK_STAGES = ["친구 코스의 조건을 가져오는 중", "예산 안에 들어오는 조합을 맞추는 중", "짠! 거의 다 됐어요"];
const REROLL_STAGES = ["다른 곳들로 다시 맞추는 중", "남는 돈까지 계산하고 있어요", "짠! 거의 다 됐어요"];

/** 모바일 바텀시트의 세 단계 (docs/25 §5): 지도를 크게 · 절반 · 목록 전체 */
type SheetStop = "map" | "half" | "full";
/** 헤더 높이 (sticky 오프셋) */
const HEADER_PX = 68;
/** 이야기가 이보다 길면 네 줄만 보이고 "더 읽기"로 편다 */
const STORY_FOLD = 60; // 한 줄(모바일 약 30자)을 넘으면 접는다

/** "18:00 ~ 21:00" — 만남 시간을 정했을 때만. 맡겼으면 출발 시각만. */
function meetWindow(startAt: string, durationMin?: number | null): string {
  if (!durationMin) return `${clock(startAt)} 출발`;
  const end = new Date(new Date(startAt).getTime() + durationMin * 60_000).toISOString();
  return `${clock(startAt)} ~ ${clock(end)}`;
}

/** 빈 슬롯이 둘이면 같은 문구가 두 번 온다. 화면엔 한 번만 보여 준다. */
function uniqueWarnings(warnings: CourseWarning[]): CourseWarning[] {
  const seen = new Set<string>();
  return warnings.filter((w) => {
    const text = `${w.code}:${w.message ?? w.detail ?? ""}`;
    if (seen.has(text)) return false;
    seen.add(text);
    return true;
  });
}

export function CourseView({ id }: { id: string }) {
  const router = useRouter();
  const auth = useAuth();
  const course = useCourse(id);
  const swap = useSwapStop(id);
  const reorder = useReorderStops(id);
  const save = useSaveCourse(id);
  const reroll = useGenerateCourse();
  const narrative = useCourseNarrative(course.data ? id : undefined);
  // 지도용 부가 정보: 실제 보행 경로 + 가까운 역 출구·정류장. 실패해도 코스 화면은 그대로 동작한다.
  const points = useMemo(() => (course.data?.stops ?? []).map((s) => ({ lat: s.place.lat, lng: s.place.lng })), [course.data?.stops]);
  // 코스의 실제 경로 (docs/27): 지도 · 카드 사이 구간 · 이동 요약이 모두 이 하나를 읽는다
  const courseRoute = useCourseRoute(course.data ? id : undefined, (course.data?.stops ?? []).map((s) => s.place.id));
  const mapRoute = useMemo(() => toMapRoute(courseRoute.data), [courseRoute.data]);
  const accessHints = useAccessHints(points);
  // 코스 옆의 부가 정보 (docs/46): 가는 길에 들를 곳 · 장소별 평판 신호. 코스 자체는 건드리지 않고, 실패하면 안 보일 뿐이다
  const stopIds = (course.data?.stops ?? []).map((s) => s.place.id);
  const alongTheWay = useAlongTheWay(course.data ? id : undefined, course.data?.request.transport === "walk", stopIds.join(","));
  const placeSignals = usePlaceSignals(stopIds);
  // 알림 종(docs/47)이 이 동네의 축제를 먼저 보여 준다: 마지막으로 본 코스의 첫 장소 주소 앞부분(시 · 구)
  const firstAddress = course.data?.stops[0]?.place.address;
  useEffect(() => {
    if (!firstAddress) return;
    try {
      localStorage.setItem(LAST_AREA_KEY, JSON.stringify(firstAddress.split(" ").slice(0, 2).join(" ")));
    } catch {
      /* 저장이 막혀 있으면 기억하지 않는다 */
    }
  }, [firstAddress]);

  const [activeStop, setActiveStop] = useState<number | null>(null);
  // 카드 → 지도: 그 장소로 옮겨 가 확대 (n 이 바뀔 때마다) · "전체 코스 지도에서 보기": 코스 전체로 다시 맞춤
  const [focus, setFocus] = useState<{ position: number; n: number } | null>(null);
  const [fitKey, setFitKey] = useState(0);
  // 주변 장소(동네 명소 · 숙소 · 남은 돈으로 갈 곳)를 지도 앱으로 내보내지 않고 이 지도에 띄운다. 정보는 "자세히"로 따로 연다 (docs/36)
  const [nearby, setNearby] = useState<NearbyPin | null>(null);
  const [nearbyOpen, setNearbyOpen] = useState(false);
  // 핀을 눌러 카드로 스크롤하는 동안은, 스크롤이 지나가는 다른 카드가 선택을 빼앗지 않게 한다
  const viewLock = useRef(0);
  const [shared, setShared] = useState(false);
  const [forking, setForking] = useState(false);
  const [notice, setNotice] = useState<{ mood: JjaniMood; title: string; body?: string } | null>(null);
  const viewed = useRef<string | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const [sheet, setSheet] = useState<SheetStop>("half");
  const [storyOpen, setStoryOpen] = useState(false);
  // 편집 가능한 초안 (docs/42): 고정한 곳은 다시 짜도 남는다 · 다시 짜기는 방향을 고르는 시트로
  const { pins, toggle: togglePin } = usePins();
  const [rerollOpen, setRerollOpen] = useState(false);
  const mapBoxRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ y: number; moved: boolean } | null>(null);
  // 목록을 읽던 중에 단계를 바꾸면 지도 칸의 높이만큼 내용이 밀린다 → 그만큼 되돌려 읽던 카드를 제자리에 둔다
  const shiftFrom = useRef<number | null>(null);
  const [instantSheet, setInstantSheet] = useState(false);
  useLayoutEffect(() => {
    const before = shiftFrom.current;
    if (before === null) return;
    shiftFrom.current = null;
    const after = mapBoxRef.current?.parentElement?.getBoundingClientRect().height ?? before;
    window.scrollBy({ top: after - before, behavior: "instant" });
  }, [sheet]);

  useEffect(() => {
    if (course.data && viewed.current !== id) {
      viewed.current = id;
      track("course_viewed", { course_id: id, label: course.data.label, shared: course.data.can_edit === false });
    }
  }, [course.data, id]);

  if (course.isPending)
    return (
      <>
        <ResultHeader />
        <JjaniLoader stages={LOADING_STAGES} />
      </>
    );
  if (course.isError)
    return (
      <>
        <ResultHeader />
        <ErrorState error={course.error} onRetry={() => void course.refetch()} size="lg" className="py-10" />
      </>
    );

  const data = course.data;
  const { request } = data;
  const busy = swap.isPending || reorder.isPending;
  // 남이 만든 코스(공유 링크): 서버가 403 을 낼 조작은 버튼째 숨기고, 같은 조건으로 내 코스를 만드는 길만 남긴다
  const readOnly = data.can_edit === false;
  // 새로고침 직후 세션을 복원하는 동안에는 "내 코스"인지 아직 모른다 → 그동안은 친구 코스라고 단정하지 않는다
  const viewerKnown = auth.status !== "loading";
  const over = data.totals.budget_left < 0;
  const mood: JjaniMood = data.is_saved ? "cheers" : over ? "sorry" : data.totals.budget_left > 0 ? "wink" : "done";

  // 지역 중심이 아니라 역·장소 주변으로 짠 코스면 그 이름으로 부른다 ("영등포구"가 아니라 "신도림역 주변")
  const hopping = (request.regions?.length ?? 0) > 1;
  // 여행 일정의 하루: 탭은 대안 코스가 아니라 날짜이고, 다시 짜면 그 날의 자리에 그대로 들어간다
  const tripDay = (request.days ?? 0) > 1;
  const firstStop = data.stops[0];
  const lastStop = data.stops[data.stops.length - 1];
  // 시 · 도 전체 여행: "부산광역시 · 송도해수욕장 주변 → 부산타워 주변"
  // docs/34: 대학교를 중심으로 짠 하루는 그 학교 이름 그대로 ("가천대학교 · 캠퍼스 탐방")
  const anchor = request.anchor ?? null;
  const areaLabel = anchor ? anchor.name : hopping ? request.regions!.map((r) => r.name).join(" → ") : request.origin_label ? `${request.origin_label} 주변` : request.region?.name;
  const placeLabel = request.city ? [request.city.name, areaLabel].filter(Boolean).join(" · ") : areaLabel;
  // 목적을 여러 개 골랐으면 모두 보여 준다 (첫 번째가 하루의 틀)
  const purposeLabel = (request.purposes?.length ?? 0) > 1 ? request.purposes!.map((p) => p.name).join(" + ") : request.purpose.name;

  const fail = (error: unknown) => {
    const copy = mascotCopyForError(error);
    // 공유받은 코스를 바꾸거나 저장하려 한 경우다. 관리자 화면용 "권한" 문구 대신 할 수 있는 일을 알려 준다.
    // 보통은 can_edit=false 라 버튼이 없어서 여기 오지 않는다. 화면을 연 뒤에 주인이 생긴 경우(다른 사람이 먼저 저장)만 온다.
    if (copy.code === "FORBIDDEN") {
      setNotice({ mood: "hi", title: "친구가 짠 코스예요", body: "‘이 코스로 내 코스 만들기’로 같은 조건의 내 코스를 만들어 보세요." });
      void course.refetch(); // 읽기 전용 화면으로 바꾼다
    } else setNotice({ mood: copy.mood, title: copy.title, body: copy.description });
    track("error_shown", { code: copy.code, where: "course" });
    // 하단 버튼(다시 짜기·저장)에서 난 오류도 보이게 안내 말풍선으로 데려간다
    requestAnimationFrame(() => noticeRef.current?.scrollIntoView({ block: "center" }));
  };

  const onSwap = (position: number, strategy: SwapStrategy | { placeId: string }) => {
    setNotice(null);
    swap.mutate(
      typeof strategy === "string" ? { position, strategy } : { position, place_id: strategy.placeId },
      {
        onSuccess: (next) => {
          track("stop_swapped", { course_id: id, position, strategy: typeof strategy === "string" ? strategy : "pick" });
          const changed = next.stops.find((s) => s.position === position);
          // 지키지 못한 예산을 지켰다고 말하지 않는다
          const within = next.totals.price <= request.budget_total;
          setNotice({
            mood: within ? "wink" : "sorry",
            title: changed ? `${changed.place.name}(으)로 바꿨어요` : "바꿨어요",
            // 한 곳만 바꿔도 남은 돈은 바로 다시 계산된다 — 그 숫자로 말한다
            body: within ? `총액 ${won(next.totals.price)} · ${won(next.totals.budget_left)} 남아요.` : `총액 ${won(next.totals.price)}, 예산보다 ${won(next.totals.price - request.budget_total)} 많아요.`,
          });
        },
        // API 는 SWAP_NOT_POSSIBLE 을 낸다 (SLOT_EMPTY 는 예전 목 서버의 코드)
        onError: (error) =>
          error.code === "SWAP_NOT_POSSIBLE" || error.code === "SLOT_EMPTY"
            ? setNotice({ mood: "sorry", title: "바꿀 만한 곳을 찾지 못했어요", body: "이 기준으로는 예산 안에서 대신할 곳이 없어요. 다른 기준으로 바꿔 보세요." })
            : error.code === "CANDIDATE_NOT_ELIGIBLE"
              ? setNotice({ mood: "sorry", title: "그곳은 지금 넣을 수 없어요", body: "그 시간에 문을 닫았거나 예산을 넘어요. 다른 후보를 골라 주세요." })
              : fail(error),
      },
    );
  };

  const onMove = (position: number, delta: -1 | 1) => {
    const order = data.stops.map((s) => s.position);
    const from = order.indexOf(position);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= order.length) return;
    [order[from], order[to]] = [order[to]!, order[from]!];
    setNotice(null);
    track("stop_reordered", { course_id: id, position, delta });
    reorder.mutate({ order }, { onSuccess: () => setNotice({ mood: "think", title: "순서를 바꿔서 이동 시간을 다시 계산했어요" }), onError: fail });
  };

  const onSave = () => {
    // 로그인하지 않은 것이 확실하면 서버에 묻지 않고 바로 로그인으로 (돌아올 답은 401 뿐이다)
    if (auth.status === "anonymous") {
      router.push(`/login?next=${encodeURIComponent(`/course/${id}`)}`);
      return;
    }
    save.mutate(undefined, {
      onSuccess: () => {
        track("course_saved", { course_id: id, price: data.totals.price });
        setNotice({ mood: "cheers", title: "잘 다녀오세요, 짠!", body: "내 코스에 저장했어요." });
      },
      onError: (error) => (error.code === "UNAUTHORIZED" ? router.push(`/login?next=${encodeURIComponent(`/course/${id}`)}`) : fail(error)),
    });
  };

  const onShare = async () => {
    const url = window.location.href;
    const payload = { title: data.og.title, text: data.summary, url };
    try {
      if (navigator.share) {
        await navigator.share(payload);
        track("share_clicked", { course_id: id, method: "web_share" });
      } else {
        await navigator.clipboard.writeText(url);
        track("share_clicked", { course_id: id, method: "clipboard" });
        setShared(true);
        setTimeout(() => setShared(false), 2200);
      }
    } catch (error) {
      // 공유 시트를 닫은 것은 실패가 아니다. 복사가 막힌 경우(권한 · 보안 연결 아님)는 주소를 직접 보여 준다
      if (error instanceof DOMException && error.name === "AbortError") return;
      setNotice({ mood: "sorry", title: "링크를 복사하지 못했어요", body: `이 주소를 길게 눌러 복사해 주세요: ${url}` });
    }
  };

  // 조건 바꾸기: 지역 · 목적을 채운 채로 위저드로 돌아간다 (역 · 장소 기준 코스는 지역이 없어 목적만)
  const changeHref = `/plan?${new URLSearchParams({ ...(anchor ? { region: encodeCampus(anchor) } : request.region ? { region: request.region.slug } : {}), purpose: request.purpose.code }).toString()}`;

  /** fork: 친구 코스를 같은 조건 그대로 내 코스로 새로 만든다 (지금 장소를 빼지 않는다). 아니면 다른 장소들로 다시 짠다. */
  /** focus: 이 동네 명물을 골라(또는 FOCUS_OFF 로 빼고) 다시 짠다. 안 주면 처음 조건 그대로 */
  /** 이 코스를 만든 조건 그대로. 다시 짜기 · 예산 what-if 가 여기서 필요한 것만 바꿔 보낸다 */
  const baseRequest: GenerateCourseRequest = {
        // 대학교를 중심으로 짠 하루: 다시 짜도 그 캠퍼스가 중심이다 (docs/34)
        ...(anchor ? { anchor: { kind: "university" as const, id: anchor.id } } : { region: request.city?.slug ?? request.region?.slug }),
        // 도시 여행의 구역은 서버가 다시 고른다(인기 구역). 직접 고른 여러 동네만 그대로 보낸다
        ...(hopping && !request.city ? { regions: request.regions!.map((r) => r.slug) } : {}),
        ...((request.purposes?.length ?? 0) > 1 ? { purposes: request.purposes!.slice(1).map((p) => p.code) } : {}),
        // 역·장소 주변으로 짠 코스는 그 지점을 다시 보낸다 — 안 보내면 구 중심으로 옮겨 가 버린다
        ...(request.origin && !request.city && !anchor ? { origin: request.origin, ...(request.origin_label ? { origin_label: request.origin_label } : {}) } : {}),
        purpose: request.purpose.code,
        party_size: request.party_size,
        budget_total: request.budget_total,
        transport: request.transport,
        start_at: request.start_at,
        // 다시 짜도 처음에 정한 만남 시간은 그대로
        ...(request.duration_min ? { duration_min: request.duration_min } : {}),
        ...(request.style ? { style: request.style } : {}),
        ...(request.focus ? { focus: request.focus } : {}),
        ...(request.extras?.length ? { extras: request.extras } : {}),
        ...(request.conditions?.length ? { conditions: request.conditions } : {}),
        preferences: {
          liked_tags: request.preferences?.liked_tags ?? [],
          disliked_tags: request.preferences?.disliked_tags ?? [],
          exclude_place_ids: [],
        },
        alternatives: 2,
  };

  // 이 코스에 들어 있는 고정한 곳만 (다른 코스에서 고정한 것은 보내지 않는다)
  const keep = data.stops.map((s) => s.place.id).filter((pid) => pins.includes(pid));
  const onReroll = (fork = false, focus?: string, tweaks: Tweak[] = []) => {
    setForking(fork);
    track("reroll_clicked", { course_id: id, ...(fork ? { from_shared: true } : {}), ...(focus ? { focus } : {}) });
    reroll.mutate(
      {
        ...baseRequest,
        ...(focus ? { focus } : {}),
        ...(tripDay && !fork ? { replaces: id } : {}),
        ...tweaksToRequest(tweaks),
        ...(!fork && keep.length ? { keep_place_ids: keep } : {}),
        // 처음에 고른 취향(좋아요·피할 것)은 그대로, 지금 코스의 장소만 빼고
        preferences: { ...baseRequest.preferences!, exclude_place_ids: fork ? [] : data.stops.map((s) => s.place.id) },
      },
      {
        onSuccess: (res) => {
          const first = res.courses[0];
          if (first) {
            router.push(`/course/${encodeURIComponent(first.id)}`);
            return;
          }
          reroll.reset(); // 성공 상태로 두면 전체 화면 로더가 끝나지 않는다
          fail(new ApiError({ code: "NO_COURSE_AVAILABLE", status: 200, title: "다시 짤 곳이 부족해요", detail: "지금 코스의 장소를 빼면 남는 곳이 모자라요. 예산이나 시간을 바꿔서 새로 짜 보세요." }));
        },
        onError: fail,
      },
    );
  };

  /**
   * 바텀시트를 그 단계로: 지도 칸의 높이만 바꾼다(지도는 크기가 바뀌면 코스 전체를 다시 맞춘다).
   * 맨 위에서는 부드럽게 늘고 줄지만, 목록을 읽던 중이면 한 번에 바꾸고 읽던 자리를 지킨다.
   */
  const moveSheet = (next: SheetStop) => {
    const reading = window.scrollY > 8;
    setInstantSheet(reading || Boolean(reduced));
    shiftFrom.current = reading ? (mapBoxRef.current?.parentElement?.getBoundingClientRect().height ?? 0) : null;
    setSheet(next);
  };
  const longStory = (narrative.text?.length ?? 0) > STORY_FOLD && narrative.status !== "streaming";

  const desktop = () => window.matchMedia("(min-width: 1024px)").matches;
  /** 그 장소의 카드를 지도 바로 아래(데스크톱은 헤더 아래)로 데려온다 */
  const scrollToCard = (position: number, delay = 0) => {
    viewLock.current = Date.now() + 1400 + delay;
    window.setTimeout(() => {
      const el = document.querySelector<HTMLElement>(`article[data-position='${position}']`);
      if (!el) return;
      const sticky = HEADER_PX + (desktop() ? 0 : (mapBoxRef.current?.parentElement?.getBoundingClientRect().height ?? 0));
      window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + window.scrollY - sticky - 12), behavior: reduced ? "auto" : "smooth" });
    }, delay);
  };
  /** 지도 → 목록: 핀을 누르면 그 카드로. 모바일에서 지도를 크게 보던 중이면 시트를 절반으로 올린다 */
  const selectFromMap = (position: number | null) => {
    setActiveStop(position);
    if (position === null) return;
    const lift = !desktop() && sheet === "map";
    if (lift) moveSheet("half");
    scrollToCard(position, lift ? 340 : 0);
  };
  /** 목록 → 지도: 카드를 누르면 지도가 그 장소로. 모바일에서 목록만 보던 중이면 지도가 보이게 절반으로 */
  const focusStop = (position: number) => {
    setActiveStop(position);
    setFocus((f) => ({ position, n: (f?.n ?? 0) + 1 }));
    if (!desktop() && sheet === "full") moveSheet("half");
  };
  /** 스크롤이 화면 가운데를 지나는 카드 → 그 핀 (핀을 눌러 스크롤하는 중에는 쉰다) */
  const viewFromScroll = (position: number) => {
    if (Date.now() < viewLock.current) return;
    setActiveStop(position);
  };
  /** 주변 장소 → 지도: 코스 지도에 번호 없는 핀으로 띄운다. 모바일에서 목록만 보던 중이면 지도가 보이게 절반으로 */
  const showNearby = (pin: Omit<NearbyPin, "n">) => {
    setActiveStop(null);
    setNearby((prev) => ({ ...pin, n: (prev?.n ?? 0) + 1 }));
    track("nearby_shown", { kind: pin.kind });
    if (!desktop() && sheet === "full") moveSheet("half");
  };
  /** 전체 코스: 핀 · 경로 · 순서 · 이동 시간이 모두 보이게. 모바일은 지도를 크게 */
  const showWholeCourse = () => {
    setActiveStop(null);
    setNearby(null);
    setFitKey((k) => k + 1);
    if (!desktop()) {
      moveSheet("map");
      window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
    }
  };

  const selectAlternative = (nextId: string) => {
    if (nextId === id) return;
    const label = data.siblings.find((s) => s.id === nextId)?.label ?? "";
    track("alternative_selected", { course_id: nextId, label });
    router.replace(`/course/${encodeURIComponent(nextId)}`, { scroll: false });
  };

  /** 다시 짜기 · (모바일) 공유 · 저장: 좁은 화면은 아래 고정 바, 넓은 화면은 영수증 아래 — 같은 버튼 한 벌 */
  const actionButtons = (
    <>
      {/* 넓은 화면(영수증 칸)에서는 저장이 먼저, 한 줄에 하나씩 */}
      {readOnly ? (
        <Button type="button" variant="brand" size="xl" className="flex-1 wide:order-first" onClick={() => onReroll(true)} disabled={reroll.isPending || !viewerKnown}>
          <CopyPlus aria-hidden /> 이 코스로 내 코스 만들기
        </Button>
      ) : data.is_saved ? (
        <Button asChild variant="brand" size="xl" className="flex-1 wide:order-first">
          <Link href="/my">
            <BookmarkCheck aria-hidden /> 저장됨 · 내 코스 보기
          </Link>
        </Button>
      ) : (
        <Button type="button" variant="brand" size="xl" className="flex-1 wide:order-first" onClick={onSave} disabled={save.isPending}>
          <Bookmark aria-hidden /> {save.isPending ? "저장하는 중…" : "코스 저장하기"}
        </Button>
      )}
      {readOnly ? null : (
        <Button type="button" variant="soft" size="xl" onClick={() => setRerollOpen(true)} disabled={reroll.isPending} className="-order-1 max-sm:px-4 wide:order-none" aria-label="다시 짜기">
          <RotateCw aria-hidden /> <span className="max-sm:sr-only">다시 짜기</span>
        </Button>
      )}
      {/* 데스크톱의 공유는 결과 헤더에 있다 */}
      <Button type="button" variant="soft" size="xl" onClick={() => void onShare()} className="-order-1 max-sm:px-4 lg:hidden" aria-label="코스 공유하기">
        {shared ? <Check aria-hidden /> : <Share2 aria-hidden />} <span className="max-sm:sr-only">{shared ? "링크 복사됨" : "공유"}</span>
      </Button>
    </>
  );

  return (
    <>
      <ResultHeader
        title={[placeLabel, purposeLabel].filter(Boolean).join(" · ")}
        // 인원 · 예산 · 날짜는 아래 조건 칩과 요약이 말한다 — 머리에 한 줄로 몰아넣지 않는다 (docs/32 B §12)
        subtitle={data.label}

        onShare={() => void onShare()}
        shared={shared}
      />
      {reroll.isPending || reroll.isSuccess ? <JjaniLoader fullscreen stages={forking ? FORK_STAGES : REROLL_STAGES} interval={900} /> : null}

      <div inert={reroll.isPending || reroll.isSuccess} className="[overflow-anchor:none] lg:grid lg:min-h-[calc(100dvh-68px)] lg:grid-cols-[minmax(0,1fr)_minmax(440px,560px)] wide:grid-cols-[minmax(0,1fr)_minmax(0,840px)]">
        {/* 지도 + 바텀시트 손잡이: 모바일 · 태블릿은 헤더 밑에 붙어 있고 목록이 그 아래로 지나간다
            → 장소를 읽는 동안에도 그 장소의 핀이 보인다. 데스크톱은 왼쪽에 고정 */}
        <div className="sticky top-[68px] z-20 lg:z-0 lg:h-[calc(100dvh-68px)]">
          {/* 높이는 바텀시트 단계가 정한다: 지도를 크게 · 절반 · 접음(목록 전체). 데스크톱은 늘 화면 높이 */}
          <div
            ref={mapBoxRef}
            style={{ "--map-h": sheet === "map" ? "calc(100dvh - 68px - 150px)" : sheet === "half" ? "30dvh" : "0px" } as React.CSSProperties}
            className={cn("relative h-(--map-h) overflow-hidden lg:h-full", !instantSheet && "transition-[height] duration-300 ease-out")}
          >
            <RouteMap
              stops={data.stops}
              activeStop={activeStop}
              onSelect={selectFromMap}
              route={mapRoute}
              focus={focus}
              fitKey={fitKey}
              access={accessHints.data?.items}
              nearby={nearby}
              onNearby={nearby?.id ? () => setNearbyOpen(true) : undefined}
            />
            {/* 띄운 주변 장소의 이름표: 무엇을 보고 있는지 · 정보는 따로 열기 · 지우기 */}
            {nearby ? (
              <div role="status" className="absolute top-3 left-3 z-[500] flex max-w-[calc(100%-11rem)] items-center gap-1 rounded-xl bg-white py-1 pr-1 pl-3 shadow-soft">
                <span className="min-w-0">
                  <span className="block text-caption text-muted-foreground">{nearby.kind}</span>
                  <b className="block truncate text-body-sm font-semibold text-ink">{nearby.name}</b>
                </span>
                {nearby.id ? (
                  <button type="button" aria-label={`${nearby.name} 자세히 보기`} onClick={() => setNearbyOpen(true)} className="min-h-11 shrink-0 rounded-lg px-2.5 text-body-sm font-semibold text-blue-deep hover:bg-blue-soft">
                    자세히
                  </button>
                ) : null}
                <button type="button" aria-label="지도에서 지우기" onClick={() => setNearby(null)} className="grid size-11 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-soft hover:text-ink">
                  <X aria-hidden className="size-4" />
                </button>
              </div>
            ) : null}
          </div>
          {/* 바텀시트 손잡이: 누르면 절반 ↔ 전체, 위아래로 끌면 한 단계씩. 오른쪽 버튼은 지도를 크게 ↔ 절반 */}
          <div className={cn("relative flex h-9 items-center justify-center rounded-t-[24px] bg-soft shadow-[0_-8px_24px_rgba(72,54,24,.10)] lg:hidden", sheet !== "full" && "-mt-5")}>
            <button
              type="button"
              aria-label={sheet === "full" ? "목록 접기" : "목록 크게 보기"}
              onPointerDown={(e) => {
                drag.current = { y: e.clientY, moved: false };
              }}
              onPointerUp={(e) => {
                const start = drag.current;
                if (!start) return;
                const dy = e.clientY - start.y;
                if (Math.abs(dy) < 24) return;
                start.moved = true;
                moveSheet(dy < 0 ? (sheet === "map" ? "half" : "full") : sheet === "full" ? "half" : "map");
              }}
              onClick={() => {
                const moved = drag.current?.moved;
                drag.current = null;
                if (!moved) moveSheet(sheet === "full" ? "half" : "full");
              }}
              className="grid h-9 w-28 touch-none place-items-center rounded-full"
            >
              <span aria-hidden className="h-1 w-10 rounded-full bg-ink/20" />
            </button>
            <button
              type="button"
              onClick={() => moveSheet(sheet === "map" ? "half" : "map")}
              aria-label={sheet === "map" ? "지도 작게 보기" : "지도 크게 보기"}
              className="absolute top-0.5 right-3 grid size-11 place-items-center rounded-full text-ink-2 hover:bg-white"
            >
              {sheet === "map" ? <Minimize2 aria-hidden className="size-4" /> : <Maximize2 aria-hidden className="size-4" />}
            </button>
          </div>
        </div>

        {/* 타임라인 */}
        <div className="relative z-10 bg-soft">
          {/* grid-cols-[minmax(0,1fr)]: 칸이 긴 문장·상호만큼 늘어나 모바일에서 본문을 밀어내지 않게 (E2E 가 잡은 21px 넘침) */}
          <div className="mx-auto grid max-w-[640px] grid-cols-[minmax(0,1fr)] gap-4 px-4 pt-3 pb-32 sm:gap-5 sm:px-6 lg:max-w-none lg:px-7 lg:pt-7 lg:pb-28 wide:pb-12">
            <header className="grid grid-cols-[minmax(0,1fr)] gap-3">
              {/* 조건 칩: 아이콘 + 짧은 말 (docs/32 B §12). 돈은 바로 아래 요약이 가장 크게 말한다 */}
              {/* 좁은 화면: 칩은 한 줄로 흐른다(가로로 밀어 보기) — 두 줄이 되어 첫 장소를 밀어내지 않게 (docs/33 §10) */}
              <ul aria-label="이 코스의 조건" className="tabular flex items-center gap-1.5 text-body-sm font-semibold text-ink-2 max-sm:-mx-4 max-sm:overflow-x-auto max-sm:px-4 max-sm:[scrollbar-width:none] sm:flex-wrap">
                {(
                  [
                    // 하루의 중심이 대학교면 첫 칩 (docs/34). 그날 축제가 코스에 들어갔으면 그 이름도
                    anchor ? { icon: GraduationCap, text: anchor.name } : null,
                    anchor?.festival ? { icon: Tent, text: anchor.festival } : null,
                    request.days && request.days > 1 ? { icon: CalendarRange, text: `${request.day}일차 / ${request.days}일` } : null,
                    // 날짜와 시간은 한 칩: 좁은 화면에서 칩이 두 줄이 되어 첫 일정을 밀어내지 않게
                    { icon: CalendarDays, text: `${dateLabel(request.start_at)} ${meetWindow(request.start_at, request.duration_min)}` },
                    { icon: Users, text: `${request.party_size}명` },
                    { icon: MODE_ICON[request.transport] ?? Footprints, text: transportLabel(request.transport) },
                    request.conditions?.includes("rain") ? { icon: CloudRain, text: "비 오는 날" } : null,
                    tripDay && request.trip_budget_total ? { icon: Wallet, text: `여행 전체 ${won(request.trip_budget_total)}` } : null,
                    request.style === "fun" ? { icon: PartyPopper, text: "재미 우선" } : null,
                  ].filter(Boolean) as { icon: LucideIcon; text: string }[]
                ).map(({ icon: Icon, text }) => (
                  <li key={text} className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md bg-paper-2 px-2.5 whitespace-nowrap">
                    <Icon aria-hidden className="size-3.5 text-muted-foreground" />
                    {text}
                  </li>
                ))}
              </ul>
              <h1 className="sr-only">
                {data.label}: {data.summary}
              </h1>
            </header>

            {readOnly && viewerKnown ? (
              <p role="note" className="flex items-center gap-2 border-l-2 border-blue-deep pl-3 text-body-sm font-semibold text-blue-deep">
                <Users aria-hidden className="size-4 shrink-0" />
                친구가 짠 코스예요. 아래 버튼으로 같은 조건의 내 코스를 만들면 바꾸고 저장할 수 있어요.
              </p>
            ) : null}

            <AlternativeTabs items={data.siblings} currentId={id} onSelect={selectAlternative} label={tripDay ? "날짜별 코스" : undefined} />

            {/* 정보의 순서 (docs/33 §8): 무엇을 · 어디로 · 언제(일정) → 얼마(영수증) → 얼마나 이동 → 부가 정보.
                ≥1360px: 왼쪽 칸은 하루, 오른쪽 칸은 따라 내려오는 영수증 + 저장. 그보다 좁으면 일정 바로 다음이 영수증 */}
            <div
              id="course-panel"
              role={data.siblings.length > 1 ? "tabpanel" : undefined}
              aria-label={data.label}
              className="grid grid-cols-[minmax(0,1fr)] gap-4 wide:grid-cols-[minmax(0,1fr)_320px] wide:items-start wide:gap-x-8"
            >
              <div className="grid min-w-0 gap-3 sm:gap-4">
              <DaySummary
                totals={data.totals}
                budget={request.budget_total}
                partySize={request.party_size}
                transport={request.transport}
                travelMin={courseRoute.data?.totals.travel_min ?? data.totals.travel_min}
                distanceM={courseRoute.data?.totals.distance_m ?? data.totals.distance_m}
                mood={mood}
                line={over ? "조금 넘었어요. 한 곳만 바꿔 볼까요?" : undefined}
                summary={data.summary}
                stops={data.stops.length}
                editable={!readOnly}
                bubbleKey={`${id}-${data.totals.price}`}
              />
              {/* 좁은 화면에서는 첫 장소가 첫 화면에 들어오게 구멍 줄을 뺀다 */}
              <hr aria-hidden className="tear-line my-1 max-lg:hidden" />

              {uniqueWarnings(data.warnings).map((w, i) => (
                <p
                  key={`${w.code}-${w.role ?? ""}-${i}`}
                  role="status"
                  className={cn("flex gap-2.5 rounded-2xl px-4 py-3 text-body-sm font-semibold", w.code === "DURATION_FIT" ? "bg-blue-soft text-blue-deep" : w.code === "BUDGET_OVER" ? "bg-pink-soft text-pink-deep" : "bg-paper-2 text-ink-2")}
                >
                  {/* DURATION_FIT 은 경고가 아니라 "시간에 맞췄다"는 안내다 */}
                  {w.code === "DURATION_FIT" ? <Clock aria-hidden className="mt-0.5 size-4 shrink-0" /> : <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />}
                  {w.message ?? w.detail}
                </p>
              ))}

              <div ref={noticeRef} aria-live="polite">
                {notice ? (
                  <JjaniBubble mood={notice.mood} title={notice.title} size={60} bubbleKey={notice.title}>
                    {notice.body}
                  </JjaniBubble>
                ) : null}
              </div>

              {/* 실제 이동 시간으로 다시 재 보니 어긋나는 곳 (docs/27 §17) */}
              {courseRoute.data ? <RouteIssues issues={courseRoute.data.issues} onReroll={readOnly ? undefined : () => onReroll()} busy={reroll.isPending} /> : null}

              <CourseTimeline
                course={data}
                transport={request.transport}
                style={request.style}
                partySize={request.party_size}
                activeStop={activeStop}
                swappingPosition={swap.isPending ? (swap.variables?.position ?? null) : null}
                busy={busy}
                editable={!readOnly}
                route={courseRoute.data}
                access={accessHints.data?.items}
                onHover={setActiveStop}
                onView={viewFromScroll}
                onFocusStop={focusStop}
                onSwap={onSwap}
                onSwapTo={(position, placeId) => onSwap(position, { placeId })}
                onMove={onMove}
                pins={pins}
                onTogglePin={readOnly ? undefined : togglePin}
                along={alongTheWay.data?.legs}
                onShowPlace={showNearby}
                signals={placeSignals.data?.items}
              />
              </div>

              {/* 오늘의 영수증: 오늘 하루의 요약 한 장. 저장 · 공유하는 것이 이것이다 */}
              <aside aria-labelledby="receipt-heading" className="grid gap-3 wide:sticky wide:top-[calc(68px+28px)] wide:row-span-2">
              <h2 id="receipt-heading" className="mt-4 text-h3 font-bold wide:mt-0">
                오늘의 영수증
              </h2>
              <BudgetBar
                totals={data.totals}
                budget={request.budget_total}
                partySize={request.party_size}
                stops={data.stops}
                heading={[placeLabel, purposeLabel, `${request.party_size}명`].filter(Boolean).join(" · ")}
                // 예산 + 이동 = 오늘의 하루 한 장 (docs/27 §15)
                travel={{ mode: request.transport, minutes: courseRoute.data?.totals.travel_min ?? data.totals.travel_min, distanceM: courseRoute.data?.totals.distance_m ?? data.totals.distance_m }}
              />
              {/* 넓은 화면: 저장 · 다시 짜기가 영수증 바로 아래 (아래 고정 바는 숨긴다) */}
              <div className="hidden gap-2 wide:grid">{actionButtons}</div>
              </aside>

              <div className="grid min-w-0 gap-4">

              <RoutePanel
                stops={data.stops}
                transport={request.transport}
                route={courseRoute.data}
                loading={courseRoute.isPending}
                failed={courseRoute.isError}
                onRetry={() => void courseRoute.refetch()}
                activeStop={activeStop}
                onShowAll={showWholeCourse}
              />

              {!readOnly ? (
                <BudgetTools
                  baseRequest={baseRequest}
                  budget={request.budget_total}
                  partySize={request.party_size}
                  stops={data.stops}
                  total={data.totals.price}
                  heading={[dateLabel(request.start_at), placeLabel].filter(Boolean).join(" · ")}
                  courseUrl={typeof window === "undefined" ? "" : window.location.href}
                />
              ) : null}

              {data.local ? <LocalCard local={data.local} focus={request.focus} onPick={readOnly ? undefined : (word) => onReroll(false, word)} busy={reroll.isPending} onShow={showNearby} /> : null}

              {/* 늦게 도착하는 것은 장소 목록 뒤에 둔다: 추천(조회 뒤에 뜬다)과 이야기(스켈레톤 68px → 본문 250px)가 목록 위에
                  있을 때는, 화면이 뜬 뒤 1초 동안 첫 장소 카드가 613px 아래로 밀렸다(누르려던 버튼이 달아난다). 추천은 "마지막
                  장소에서 걸어갈 수 있는 곳"이므로 마지막 장소 다음이 제자리이기도 하다 */}
              <LeftoverCard
                courseId={id}
                budgetLeft={data.totals.budget_left}
                budget={request.budget_total}
                editable={!readOnly}
                onShow={showNearby}
                onAdded={(name, price) => setNotice({ mood: "cheers", title: `${name}을(를) 코스에 넣었어요`, body: price > 0 ? `${won(price)}을 더 써서, 남은 돈은 ${won(data.totals.budget_left - price)}이에요.` : "돈은 그대로 남아 있어요." })}
              />

              {/* 짠이의 이야기: 카드가 아니라 금빛 선 하나를 세운 곁글. 한 줄만 보이고 펼친다 (2026-09-24 "결과 화면이 너무 방대하다") */}
              {narrative.text ? (
                <section aria-label="짠이의 코스 이야기" className="grid justify-items-start gap-1.5 border-l-2 border-gold pl-4">
                  <p className={cn("text-body whitespace-pre-line text-ink-2", longStory && !storyOpen && "line-clamp-1")} aria-live="polite" aria-busy={narrative.status === "streaming"}>
                    {narrative.text}
                    {narrative.status === "streaming" ? <span aria-hidden className="ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 animate-pulse rounded-sm bg-blue-deep" /> : null}
                  </p>
                  {longStory ? (
                    <button type="button" aria-expanded={storyOpen} onClick={() => setStoryOpen((v) => !v)} className="-ml-2 rounded-full px-2 py-1.5 text-body-sm font-semibold text-blue-deep hover:bg-blue-soft">
                      {storyOpen ? "접기" : "이야기 더 읽기"}
                    </button>
                  ) : null}
                </section>
              ) : narrative.status === "streaming" ? (
                <p className="skeleton-shimmer h-[68px] rounded-2xl" aria-label="짠이가 코스 설명을 쓰는 중" />
              ) : null}

              {/* 저장한 내 코스: 다녀온 뒤 별점 하나 → ‘다녀옴’ 표시 + 다음 추천의 취향 학습 */}
              {data.is_saved && !readOnly ? <VisitedCard courseId={id} visited={data.status === "completed"} /> : null}

              {/* 여행 일정의 마지막 날이 아니면: 그날 동선이 끝나는 곳 근처의 숙소 */}
              {lastStop && request.day && request.days && request.day < request.days ? (
                <StayCard at={{ lat: lastStop.place.lat, lng: lastStop.place.lng }} day={request.day} startAt={request.start_at} adults={request.party_size} onShow={showNearby} />
              ) : null}
              {firstStop ? (
                <PerformanceCard at={{ lat: firstStop.place.lat, lng: firstStop.place.lng }} startAt={request.start_at} durationMin={request.duration_min ?? Math.max(120, data.totals.duration_min ?? 240)} />
              ) : null}
              <NearbyEvents events={data.nearby_events} region={request.region?.slug} startAt={request.start_at} />

              </div>
            </div>
          </div>

          {/* 액션 바 */}
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-paper/90 pb-[max(12px,env(safe-area-inset-bottom))] backdrop-blur-xl lg:sticky lg:bottom-0 wide:hidden">
            <div className="mx-auto flex max-w-[640px] items-center gap-2 px-4 pt-3 sm:px-6 lg:max-w-none lg:px-7">
              {actionButtons}
              <span role="status" className="sr-only">
                {shared ? "링크를 복사했어요" : ""}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 다시 짜기: 고정한 곳은 두고, 원하면 방향(더 저렴하게 · 덜 걷게 …)을 골라서 */}
      {!readOnly ? (
        <RerollSheet
          open={rerollOpen}
          onClose={() => setRerollOpen(false)}
          pinned={keep.length}
          changeHref={changeHref}
          onReroll={(tweaks) => {
            setRerollOpen(false);
            track("reroll_tweaked", { course_id: id, tweaks: tweaks.join(","), pinned: keep.length });
            onReroll(false, undefined, tweaks);
          }}
        />
      ) : null}

      {/* 주변 장소의 정보: 지도에 띄운 뒤, 원할 때만 따로 연다 */}
      {nearby?.id && nearbyOpen ? (
        <PlaceSheet
          place={{ id: nearby.id, name: nearby.name, category: "", lat: nearby.lat, lng: nearby.lng, address: "", thumbnail_url: null, rating: null, review_count: 0, price_per_person: null, tags: [] }}
          partySize={request.party_size}
          onClose={() => setNearbyOpen(false)}
        />
      ) : null}
    </>
  );
}
