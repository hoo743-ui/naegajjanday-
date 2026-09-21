"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bookmark, BookmarkCheck, Check, Clock, RotateCw, Share2, TriangleAlert } from "lucide-react";
import { ErrorState } from "@/components/mascot/EmptyState";
import { JjaniBubble } from "@/components/mascot/JjaniBubble";
import { JjaniLoader } from "@/components/mascot/JjaniLoader";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { ApiError } from "@/lib/api/client";
import { useAccessHints, useCourse, useCourseNarrative, useGenerateCourse, useReorderStops, useSaveCourse, useSwapStop, useWalkRoute } from "@/lib/api/hooks";
import type { CourseWarning, SwapStrategy } from "@/lib/api/types";
import { clock, dateLabel, distance, minutes, transportLabel, won } from "@/lib/format";
import { cn } from "@/lib/utils";
import { mascotCopyForError, type JjaniMood } from "@/lib/mascot-copy";
import { AlternativeTabs } from "./AlternativeTabs";
import { BudgetBar } from "./BudgetBar";
import { CourseTimeline } from "./CourseTimeline";
import { NearbyEvents } from "./NearbyEvents";
import { RouteMap } from "./RouteMap";

const LOADING_STAGES = ["코스를 펼치는 중…", "지도에 핀 꽂는 중…"];
const REROLL_STAGES = ["다른 곳들로 다시 살펴보는 중…", "예산에 맞는 곳만 고르는 중…", "가장 덜 걷는 동선 계산 중…"];

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
  const course = useCourse(id);
  const swap = useSwapStop(id);
  const reorder = useReorderStops(id);
  const save = useSaveCourse(id);
  const reroll = useGenerateCourse();
  const narrative = useCourseNarrative(course.data ? id : undefined);
  // 지도용 부가 정보: 실제 보행 경로 + 가까운 역 출구·정류장. 실패해도 코스 화면은 그대로 동작한다.
  const points = useMemo(() => (course.data?.stops ?? []).map((s) => ({ lat: s.place.lat, lng: s.place.lng })), [course.data?.stops]);
  const walkRoute = useWalkRoute(points);
  const accessHints = useAccessHints(points);

  const [activeStop, setActiveStop] = useState<number | null>(null);
  const [shared, setShared] = useState(false);
  const [notice, setNotice] = useState<{ mood: JjaniMood; title: string; body?: string } | null>(null);
  const viewed = useRef<string | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (course.data && viewed.current !== id) {
      viewed.current = id;
      track("course_viewed", { course_id: id, label: course.data.label, shared: !document.referrer.includes("/plan") });
    }
  }, [course.data, id]);

  if (course.isPending) return <JjaniLoader stages={LOADING_STAGES} />;
  if (course.isError) return <ErrorState error={course.error} onRetry={() => void course.refetch()} size="lg" className="py-10" />;

  const data = course.data;
  const { request } = data;
  const busy = swap.isPending || reorder.isPending;
  const over = data.totals.budget_left < 0;
  const mood: JjaniMood = data.is_saved ? "cheers" : over ? "sorry" : data.totals.budget_left > 0 ? "wink" : "done";

  // 지역 중심이 아니라 역·장소 주변으로 짠 코스면 그 이름으로 부른다 ("영등포구"가 아니라 "신도림역 주변")
  const placeLabel = request.origin_label ? `${request.origin_label} 주변` : request.region?.name;

  const fail = (error: unknown) => {
    const copy = mascotCopyForError(error);
    // 공유받은 코스를 바꾸거나 저장하려 한 경우다. 관리자 화면용 "권한" 문구 대신 할 수 있는 일을 알려 준다.
    if (copy.code === "FORBIDDEN") setNotice({ mood: "hi", title: "친구가 짠 코스예요", body: "‘다시 짜기’로 내 코스를 만들어 보세요." });
    else setNotice({ mood: copy.mood, title: copy.title, body: copy.description });
    track("error_shown", { code: copy.code, where: "course" });
    // 하단 버튼(다시 짜기·저장)에서 난 오류도 보이게 안내 말풍선으로 데려간다
    requestAnimationFrame(() => noticeRef.current?.scrollIntoView({ block: "center" }));
  };

  const onSwap = (position: number, strategy: SwapStrategy) => {
    setNotice(null);
    swap.mutate(
      { position, strategy },
      {
        onSuccess: (next) => {
          track("stop_swapped", { course_id: id, position, strategy });
          const changed = next.stops.find((s) => s.position === position);
          // 지키지 못한 예산을 지켰다고 말하지 않는다
          const within = next.totals.price <= request.budget_total;
          setNotice({
            mood: within ? "wink" : "sorry",
            title: changed ? `${changed.place.name}(으)로 바꿨어요` : "바꿨어요",
            body: within ? `총액 ${won(next.totals.price)}, 예산 안이에요.` : `총액 ${won(next.totals.price)}, 예산보다 ${won(next.totals.price - request.budget_total)} 많아요.`,
          });
        },
        // API 는 SWAP_NOT_POSSIBLE 을 낸다 (SLOT_EMPTY 는 예전 목 서버의 코드)
        onError: (error) =>
          error.code === "SWAP_NOT_POSSIBLE" || error.code === "SLOT_EMPTY"
            ? setNotice({ mood: "sorry", title: "바꿀 만한 곳을 찾지 못했어요", body: "이 기준으로는 예산 안에서 대신할 곳이 없어요. 다른 기준으로 바꿔 보세요." })
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
    reorder.mutate({ order }, { onSuccess: () => setNotice({ mood: "think", title: "순서를 바꿔서 이동 시간을 다시 계산했어요" }), onError: fail });
  };

  const onSave = () => {
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
    } catch {
      // 사용자가 공유 시트를 닫은 경우 등은 조용히 무시
    }
  };

  const onReroll = () => {
    track("reroll_clicked", { course_id: id });
    reroll.mutate(
      {
        region: request.region?.slug,
        // 역·장소 주변으로 짠 코스는 그 지점을 다시 보낸다 — 안 보내면 구 중심으로 옮겨 가 버린다
        ...(request.origin ? { origin: request.origin, ...(request.origin_label ? { origin_label: request.origin_label } : {}) } : {}),
        purpose: request.purpose.code,
        party_size: request.party_size,
        budget_total: request.budget_total,
        transport: request.transport,
        start_at: request.start_at,
        // 다시 짜도 처음에 정한 만남 시간은 그대로
        ...(request.duration_min ? { duration_min: request.duration_min } : {}),
        ...(request.style ? { style: request.style } : {}),
        // 처음에 고른 취향(좋아요·피할 것)은 그대로, 지금 코스의 장소만 빼고
        preferences: {
          liked_tags: request.preferences?.liked_tags ?? [],
          disliked_tags: request.preferences?.disliked_tags ?? [],
          exclude_place_ids: data.stops.map((s) => s.place.id),
        },
        alternatives: 2,
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

  const selectAlternative = (nextId: string) => {
    if (nextId === id) return;
    const label = data.siblings.find((s) => s.id === nextId)?.label ?? "";
    track("alternative_selected", { course_id: nextId, label });
    router.replace(`/course/${encodeURIComponent(nextId)}`, { scroll: false });
  };

  return (
    <>
      {reroll.isPending || reroll.isSuccess ? <JjaniLoader fullscreen stages={REROLL_STAGES} interval={900} /> : null}

      <div className="lg:grid lg:min-h-[calc(100dvh-68px)] lg:grid-cols-[minmax(0,1fr)_minmax(440px,560px)]">
        {/* 지도: 모바일·태블릿은 위에 붙어 있고(sticky), 데스크톱은 왼쪽에 고정 */}
        <div className="sticky top-[68px] z-0 h-[40dvh] sm:h-[44dvh] lg:h-[calc(100dvh-68px)]">
          <RouteMap stops={data.stops} activeStop={activeStop} onSelect={setActiveStop} route={walkRoute.data} access={accessHints.data?.items} />
        </div>

        {/* 타임라인: 모바일에서는 지도 위로 올라오는 바텀시트 모양 */}
        <div className="relative z-10 -mt-7 rounded-t-[28px] bg-soft shadow-[0_-10px_40px_rgba(47,80,160,.14)] lg:mt-0 lg:rounded-none lg:shadow-none">
          <span aria-hidden className="mx-auto block h-1 w-10 translate-y-2.5 rounded-full bg-[#D5DDEB] lg:hidden" />
          {/* grid-cols-[minmax(0,1fr)]: 칸이 긴 문장·상호만큼 늘어나 모바일에서 본문을 밀어내지 않게 (E2E 가 잡은 21px 넘침) */}
          <div className="mx-auto grid max-w-[640px] grid-cols-[minmax(0,1fr)] gap-4 px-4 pt-7 pb-32 sm:px-6 lg:max-w-none lg:px-7 lg:pt-7 lg:pb-28">
            <header className="grid grid-cols-[minmax(0,1fr)] gap-3">
              <p className="tabular flex flex-wrap gap-x-2 text-[13px] font-extrabold text-blue-deep">
                {[placeLabel, request.purpose.name, `${request.party_size}명`, `예산 ${won(request.budget_total)}`, dateLabel(request.start_at), meetWindow(request.start_at, request.duration_min), request.style === "fun" ? "재미 우선" : null].filter(Boolean).join(" · ")}
              </p>
              <h1 className="sr-only">
                {data.label}: {data.summary}
              </h1>
              <JjaniBubble mood={mood} title={over ? "괜찮아요, 조금만 더 맞춰 볼까요?" : data.totals.budget_left > 0 ? "짠! 코스 나왔어요" : "짠! 예산에 딱 맞췄어요"} tone="white" size={84} bubbleKey={`${id}-${data.totals.price}`}>
                {data.summary}
              </JjaniBubble>
              {narrative.text ? (
                <p className="rounded-card bg-white p-5 text-[15px] leading-[1.75] whitespace-pre-line text-ink-2 shadow-soft" aria-live="polite" aria-busy={narrative.status === "streaming"}>
                  {narrative.text}
                  {narrative.status === "streaming" ? <span aria-hidden className="ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 animate-pulse rounded-sm bg-blue-deep" /> : null}
                </p>
              ) : narrative.status === "streaming" ? (
                <p className="skeleton-shimmer h-[68px] rounded-card" aria-label="짠이가 코스 설명을 쓰는 중" />
              ) : null}
            </header>

            <AlternativeTabs items={data.siblings} currentId={id} onSelect={selectAlternative} />

            <div id="course-panel" role={data.siblings.length > 1 ? "tabpanel" : undefined} aria-label={data.label} className="grid gap-4">
              <BudgetBar
                totals={data.totals}
                budget={request.budget_total}
                partySize={request.party_size}
                stops={data.stops}
                heading={[request.region?.name, request.purpose.name, `${request.party_size}명`].filter(Boolean).join(" · ")}
              />

              <dl className="tabular grid grid-cols-3 gap-2 text-center">
                {[
                  { k: "총 소요", v: minutes(data.totals.duration_min) },
                  { k: `${transportLabel(request.transport)} 이동`, v: minutes(data.totals.travel_min) },
                  { k: "이동 거리", v: distance(data.totals.distance_m) },
                ].map((item) => (
                  <div key={item.k} className="rounded-2xl bg-white px-2 py-3 shadow-soft">
                    <dt className="text-xs font-bold text-muted-foreground">{item.k}</dt>
                    <dd className="text-base font-extrabold tracking-tight">{item.v}</dd>
                  </div>
                ))}
              </dl>

              {uniqueWarnings(data.warnings).map((w, i) => (
                <p
                  key={`${w.code}-${w.role ?? ""}-${i}`}
                  role="status"
                  className={cn("flex gap-2.5 rounded-2xl px-4 py-3 text-sm font-bold", w.code === "DURATION_FIT" ? "bg-blue-soft text-blue-deep" : "bg-gold-soft text-gold-ink")}
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

              <CourseTimeline
                course={data}
                style={request.style}
                partySize={request.party_size}
                activeStop={activeStop}
                swappingPosition={swap.isPending ? (swap.variables?.position ?? null) : null}
                busy={busy}
                route={walkRoute.data}
                access={accessHints.data?.items}
                onHover={setActiveStop}
                onSwap={onSwap}
                onMove={onMove}
              />

              <NearbyEvents events={data.nearby_events} region={request.region?.slug} startAt={request.start_at} />

              {data.meta ? (
                <p className="tabular text-center text-xs text-muted-foreground">
                  후보 {data.meta.candidates}곳 중에서 골랐어요 · 동선 {data.route.optimizer} · 엔진 {data.meta.engine_version}
                </p>
              ) : null}
            </div>
          </div>

          {/* 액션 바 */}
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-white/90 pb-[max(12px,env(safe-area-inset-bottom))] backdrop-blur-xl lg:sticky lg:bottom-0">
            <div className="mx-auto flex max-w-[640px] items-center gap-2 px-4 pt-3 sm:px-6 lg:max-w-none lg:px-7">
              <Button type="button" variant="soft" size="xl" onClick={onReroll} disabled={reroll.isPending} className="max-sm:px-4" aria-label="다른 장소들로 코스 다시 짜기">
                <RotateCw aria-hidden /> <span className="max-sm:sr-only">다시 짜기</span>
              </Button>
              <Button type="button" variant="soft" size="xl" onClick={() => void onShare()} className="max-sm:px-4" aria-label="코스 공유하기">
                {shared ? <Check aria-hidden /> : <Share2 aria-hidden />} <span className="max-sm:sr-only">{shared ? "링크 복사됨" : "공유"}</span>
              </Button>
              <span role="status" className="sr-only">
                {shared ? "링크를 복사했어요" : ""}
              </span>
              {data.is_saved ? (
                <Button asChild variant="brand" size="xl" className="flex-1">
                  <Link href="/my">
                    <BookmarkCheck aria-hidden /> 저장됨 · 내 코스 보기
                  </Link>
                </Button>
              ) : (
                <Button type="button" variant="brand" size="xl" className="flex-1" onClick={onSave} disabled={save.isPending}>
                  <Bookmark aria-hidden /> {save.isPending ? "저장하는 중…" : "코스 저장하기"}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
