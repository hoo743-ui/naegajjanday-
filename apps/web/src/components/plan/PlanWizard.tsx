"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { FormProvider, useForm, type FieldErrors } from "react-hook-form";
import { ArrowLeft, ArrowRight, RotateCw, Sparkles } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { JjaniBubble } from "@/components/mascot/JjaniBubble";
import { JjaniLoader } from "@/components/mascot/JjaniLoader";
import { Button } from "@/components/ui/button";
import { track, trackedWithin } from "@/lib/analytics";
import { ApiError } from "@/lib/api/client";
import { decodeStation, useGenerateCourse, usePickedRegion, usePurposes } from "@/lib/api/hooks";
import type { GenerateCourseRequest } from "@/lib/api/types";
import { num, toKstIso, won } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";
import { resolveStart } from "./meet-time";
import { PLAN_DEFAULTS, STEPS, planSchema, type PlanValues } from "./schema";
import { ReceiptProgress } from "./ReceiptProgress";
import { BudgetStep, PurposeStep, RegionStep, TasteStep } from "./steps";

const MIN_LOADER_MS = 2400;
const TRANSPORT_LABEL = { walk: "걸어서", transit: "대중교통", car: "자동차" } as const;

/**
 * 코스 생성이 실패했을 때 고치러 갈 단계. 이미 /plan 에 있으므로 "/plan 으로 가기" 링크는 아무 일도 하지 않는다
 * → 그 단계로 직접 옮겨 준다.
 */
const FIX_STEP: Record<string, { step: number; label: string }> = {
  REGION_NOT_FOUND: { step: 0, label: "지역 다시 고르기" },
  REGION_NOT_READY: { step: 0, label: "다른 지역 고르기" },
  PURPOSE_NOT_FOUND: { step: 1, label: "목적 다시 고르기" },
  NO_COURSE_AVAILABLE: { step: 2, label: "예산 · 시간 바꾸기" },
  SLOT_EMPTY: { step: 2, label: "예산 · 시간 바꾸기" },
};

export function PlanWizard() {
  const router = useRouter();
  const params = useSearchParams();
  const reduced = useReducedMotion();
  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(1);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const budgetTouched = useRef(false);
  const focusPending = useRef(false);
  // 서버는 성공(200)했는데 코스가 비어 온 경우처럼, mutation 의 error 로는 잡히지 않는 실패
  const [emptyError, setEmptyError] = useState<ApiError | null>(null);

  const form = useForm<PlanValues>({
    resolver: zodResolver(planSchema),
    mode: "onChange",
    defaultValues: { ...PLAN_DEFAULTS, region: params.get("region") ?? "", purpose: params.get("purpose") ?? "" },
  });
  const values = form.watch();
  const generate = useGenerateCourse();

  const purposes = usePurposes();
  const region = usePickedRegion(values.region || undefined);
  const pickedStation = decodeStation(values.region);
  const placeLabel = region?.name ?? (pickedStation ? `${pickedStation.name} 주변` : undefined);
  const purpose = purposes.data?.items.find((p) => p.code === values.purpose);

  useEffect(() => {
    // 헤더 · 랜딩의 버튼을 눌러서 왔으면 그 클릭이 이미 셌다 (entry 가 둘로 남지 않게)
    if (!trackedWithin("plan_started", 5000)) track("plan_started", { entry: params.get("purpose") || params.get("region") ? "landing_cta" : "direct" });
    // 최초 1회만
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 목적이 정해지면(직접 고르든 URL 로 오든) 그 목적의 기본 인원·예산으로 맞춘다. 사용자가 예산을 만진 뒤에는 건드리지 않는다.
  useEffect(() => {
    if (!purpose || budgetTouched.current) return;
    const party = Math.min(purpose.max_party_size ?? 20, purpose.default_party_size ?? form.getValues("party_size"));
    const typical = purpose.budget_range.typical ?? (purpose.budget_range.min + purpose.budget_range.max) / 2;
    form.setValue("party_size", party);
    form.setValue("budget_total", Math.round((typical * party) / 1000) * 1000);
  }, [purpose, form]);

  const jump = (next: number) => {
    if (next === step) {
      headingRef.current?.focus();
      return;
    }
    setDirection(next > step ? 1 : -1);
    setStep(next);
    // 새 단계의 제목은 앞 단계가 빠져나간 뒤에야 생긴다 → 들어오는 애니메이션이 끝날 때 초점을 옮긴다
    focusPending.current = true;
  };

  const go = async (next: number) => {
    if (next > step) {
      const current = STEPS[step];
      if (!current) return;
      const ok = await form.trigger([...current.fields]);
      if (!ok) return;
      track("plan_step_completed", {
        step: (step + 1) as 1 | 2 | 3 | 4,
        step_name: current.key,
        value: current.key === "region" ? values.region : current.key === "purpose" ? values.purpose : undefined,
      });
      if (current.key === "budget") budgetTouched.current = true;
    }
    jump(next);
  };

  /** 실패 안내의 버튼: 오류를 지우고 고칠 단계로 옮긴다 */
  const fixAt = (next: number) => {
    generate.reset();
    setEmptyError(null);
    jump(next);
  };

  const stationName = pickedStation?.name;
  const stages = useMemo(
    () => [
      region ? `${region.name} 장소 ${num(region.place_count)}곳 살펴보는 중…` : stationName ? `${stationName} 주변 장소를 살펴보는 중…` : "주변 장소를 살펴보는 중…",
      `${won(values.budget_total)} 예산에 맞는 곳만 고르는 중…`,
      // 엔진이 실제로 보는 것만 말한다 (평점·리뷰·혼잡도 자료는 아직 없다)
      "거리 · 목적에 맞는 분위기 · 영업시간 · 공공기관 소개 여부로 점수 매기는 중…",
      "가장 덜 걷는 동선 계산 중…",
    ],
    [region, stationName, values.budget_total],
  );

  // 검증 오류가 지금 보이지 않는 단계의 필드에 달리면(예: 3단계의 "이미 지난 시간") 제출 버튼이 말없이 아무 일도 안 한다
  // → 오류가 있는 첫 단계로 데려가서, 그 단계의 오류 문구가 보이게 한다.
  const onInvalid = (errors: FieldErrors<PlanValues>) => {
    const target = STEPS.findIndex((s) => s.fields.some((field) => errors[field]));
    jump(target >= 0 ? target : step);
  };

  const submit = form.handleSubmit(async (data) => {
    setEmptyError(null);
    const start = resolveStart(data, new Date());
    const station = decodeStation(data.region);
    const body: GenerateCourseRequest = {
      // 역을 골랐으면 지역 대신 그 역의 좌표를 출발점으로 보낸다 (API 는 region 또는 origin 을 받는다)
      ...(station ? { origin: { lat: station.lat, lng: station.lng }, origin_label: station.name } : { region: data.region }),
      // 여러 동네: 먼저 들를 동네들 → 마지막 동네 순서로 잇는다 (역 주변은 한 동네 코스만)
      ...(!station && data.regions_before.length > 0 ? { regions: [...data.regions_before, data.region] } : {}),
      purpose: data.purpose,
      ...(data.purposes_extra.length > 0 ? { purposes: data.purposes_extra } : {}),
      party_size: data.party_size,
      budget_total: data.budget_total,
      start_at: toKstIso(start),
      ...(data.duration_min ? { duration_min: data.duration_min } : {}),
      style: data.style,
      ...(data.focus ? { focus: data.focus } : {}),
      ...(data.with_bar || data.with_baseball ? { extras: [...(data.with_bar ? ["BAR"] : []), ...(data.with_baseball ? ["BASEBALL"] : [])] } : {}),
      ...(data.nights > 0 ? { nights: data.nights } : {}),
      ...(data.rainy ? { conditions: ["rain"] } : {}),
      transport: data.transport,
      preferences: { liked_tags: data.liked_tags, disliked_tags: data.disliked_tags, exclude_place_ids: [] },
      alternatives: 2,
    };
    track("plan_step_completed", { step: 4, step_name: "taste" });
    track("course_generate_requested", { region: body.region, purpose: body.purpose, party_size: body.party_size, budget_total: body.budget_total, transport: data.transport });
    try {
      // 로더의 단계 문구가 읽힐 만큼은 보여 준다
      const [res] = await Promise.all([generate.mutateAsync(body), new Promise((r) => setTimeout(r, reduced ? 0 : MIN_LOADER_MS))]);
      const first = res.courses[0];
      if (!first) {
        // 성공 응답이라 mutation 은 isSuccess 로 남는다 → 되돌려 놓지 않으면 로더가 끝나지 않는다
        generate.reset();
        throw new ApiError({ code: "NO_COURSE_AVAILABLE", status: 200, title: "코스를 만들지 못했어요", detail: "조건에 맞는 장소를 찾지 못했어요. 예산이나 시간을 바꿔 볼까요?" });
      }
      track("course_generated", { course_id: first.id, purpose: body.purpose, budget_total: body.budget_total, price: first.totals.price, stops: first.stops.length, candidates: res.meta.candidates, latency_ms: res.meta.latency_ms });
      router.push(`/course/${encodeURIComponent(first.id)}`);
    } catch (error) {
      const apiError = ApiError.from(error);
      track("course_generate_failed", { code: apiError.code, purpose: body.purpose, budget_total: body.budget_total });
      if (apiError.status === 200) setEmptyError(apiError);
      if (apiError.code === "BUDGET_TOO_LOW") {
        setDirection(-1);
        setStep(2);
      }
    }
  }, onInvalid);

  const error = generate.error ?? emptyError;
  const errorCopy = error ? mascotCopyForError(error) : null;
  const fix = error ? FIX_STEP[error.code] : undefined;
  const minBudget = error?.code === "BUDGET_TOO_LOW" && typeof error.meta.min_budget === "number" ? error.meta.min_budget : null;
  // 성공 후 라우팅되는 동안에도 로더를 유지한다
  const loading = generate.isPending || generate.isSuccess;
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  // 진행 영수증의 줄: 고른 것만 찍힌다 (예산 · 취향은 그 단계에 와야 찍힌다 — 기본값을 고른 것처럼 보이지 않게)
  const receiptLines = [
    { value: placeLabel ? (values.regions_before.length > 0 ? `${placeLabel} 외 ${values.regions_before.length}곳` : placeLabel) : undefined },
    { value: purpose ? (values.purposes_extra.length > 0 ? `${purpose.name} +${values.purposes_extra.length}` : purpose.name) : undefined },
    { value: step >= 2 ? `${values.party_size}명 · ${won(values.budget_total)}` : undefined },
    { value: step >= 3 ? `${values.style === "fun" ? "재미 우선" : "알뜰 · 효율"} · ${TRANSPORT_LABEL[values.transport]}` : undefined },
  ];
  // 짠이는 방금 고른 것에 한 줄로 반응한다
  const jjani =
    step === 0
      ? placeLabel
        ? { mood: "wink" as const, line: `${placeLabel}, 좋은 동네예요` }
        : { mood: "hi" as const, line: "어디서 만나요?" }
      : step === 1
        ? purpose
          ? { mood: "wink" as const, line: `${purpose.name} 코스로 짤게요` }
          : { mood: "think" as const, line: "어떤 약속이에요?" }
        : step === 2
          ? { mood: "done" as const, line: `${values.party_size}명이서 ${won(values.budget_total)}, 알맞게 써 볼게요` }
          : { mood: "cheers" as const, line: "거의 다 됐어요. 취향만 알려 주세요" };

  return (
    <FormProvider {...form}>
      {loading ? <JjaniLoader fullscreen stages={stages} interval={900} /> : null}

      {/* overflow-x-clip: 단계가 옆에서 밀려 들어오는 동안(16px) 모바일에서 가로 스크롤이 순간 생기던 것을 막는다 */}
      <form onSubmit={submit} noValidate className="mx-auto w-full max-w-[720px] overflow-x-clip px-5 pt-8 pb-36 sm:pt-12 lg:grid lg:max-w-[1120px] lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-x-16" aria-hidden={loading || undefined} inert={loading}>
        {/* 진행 표시 = 한 줄씩 찍히는 영수증 (모바일은 위쪽의 얇은 띠, 데스크톱은 옆의 영수증) */}
        <ReceiptProgress step={step} lines={receiptLines} budget={step >= 2 ? { total: values.budget_total, party: values.party_size } : undefined} jjani={jjani} onJump={(i) => void go(i)} />

        <div className="relative lg:col-start-1 lg:row-start-1">
          <AnimatePresence mode="wait" custom={direction} initial={false}>
            <motion.div
              key={step}
              custom={direction}
              variants={{
                enter: (d: number) => (reduced ? { opacity: 0 } : { opacity: 0, x: 48 * d }),
                center: { opacity: 1, x: 0 },
                exit: (d: number) => (reduced ? { opacity: 0 } : { opacity: 0, x: -48 * d }),
              }}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.32, ease: [0.2, 0.8, 0.2, 1] }}
              onAnimationComplete={(definition) => {
                if (definition !== "center" || !focusPending.current) return;
                focusPending.current = false;
                headingRef.current?.focus();
              }}
            >
              <h1 ref={headingRef} tabIndex={-1} className="mb-6 text-h1 font-bold outline-none">
                {current?.question}
              </h1>

              {step === 2 && minBudget !== null ? (
                <div role="alert" className="mb-5 rounded-card bg-white p-5 shadow-card">
                  <JjaniBubble mood="sorry" title="괜찮아요, 조금만 더 맞춰 볼까요?" size={72}>
                    {error?.detail ?? `이 조건에서는 최소 ${won(minBudget)}이 필요해요.`}
                  </JjaniBubble>
                  <Button
                    type="button"
                    variant="soft"
                    size="md"
                    className="mt-4 w-full"
                    onClick={() => {
                      form.setValue("budget_total", minBudget, { shouldValidate: true });
                      generate.reset();
                    }}
                  >
                    {won(minBudget)}으로 맞추기
                  </Button>
                </div>
              ) : null}

              {step === 0 ? <RegionStep /> : null}
              {step === 1 ? <PurposeStep onPicked={() => (budgetTouched.current = false)} /> : null}
              {step === 2 ? <BudgetStep purpose={purpose} /> : null}
              {step === 3 ? <TasteStep /> : null}

              {isLast && error && errorCopy && error.code !== "BUDGET_TOO_LOW" ? (
                <div className="mt-5 rounded-card bg-white shadow-card">
                  {fix ? (
                    <div role="alert">
                      <EmptyState mood={errorCopy.mood} title={errorCopy.title} description={errorCopy.description} size="sm" footnote={`오류 코드 ${errorCopy.code}${errorCopy.traceId ? ` · ${errorCopy.traceId}` : ""}`}>
                        <Button type="button" variant="brand" size="md" onClick={() => fixAt(fix.step)}>
                          {fix.label}
                        </Button>
                        {errorCopy.retry ? (
                          <Button type="button" variant="soft" size="md" onClick={() => void submit()}>
                            <RotateCw aria-hidden /> 다시 시도
                          </Button>
                        ) : null}
                      </EmptyState>
                    </div>
                  ) : (
                    <ErrorState error={error} onRetry={() => void submit()} size="sm" />
                  )}
                </div>
              ) : null}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* 하단 고정 내비게이션 */}
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-paper/90 pb-[max(14px,env(safe-area-inset-bottom))] backdrop-blur-xl">
          <div className="mx-auto flex w-full max-w-[720px] items-center gap-3 px-5 pt-3.5 lg:max-w-[1120px]">
            {/* 데스크톱은 옆의 영수증이 같은 것을 보여 준다 → 자리만 지킨다 */}
            <p className="tabular hidden min-w-0 flex-1 truncate text-body-sm font-bold text-ink-2 sm:block lg:invisible" aria-live="polite">
              {[placeLabel, purpose?.name, step >= 2 ? `${values.party_size}명` : null, step >= 2 ? won(values.budget_total) : null].filter(Boolean).join(" · ") || "세 가지만 알려 주세요"}
            </p>
            {step > 0 ? (
              <Button type="button" variant="soft" size="xl" onClick={() => void go(step - 1)} className="max-sm:px-4">
                <ArrowLeft aria-hidden /> <span className="max-sm:sr-only">이전</span>
              </Button>
            ) : null}
            {/*
              key 가 다르지 않으면 React 는 같은 <button> 을 재사용하면서 type 만 button → submit 으로 바꾼다.
              그 변경이 "다음" 클릭을 처리하는 도중에 일어나서, 브라우저가 그 클릭을 폼 제출로 실행한다
              → 취향 단계를 건너뛰고 코스가 바로 생성됐다(E2E 가 잡은 버그). key 로 요소를 새로 만들게 한다.
            */}
            {isLast ? (
              <Button key="submit" type="submit" variant="brand" size="xl" className="max-sm:flex-1" disabled={loading}>
                <Sparkles aria-hidden /> 코스 짜 주세요
              </Button>
            ) : (
              <Button key="next" type="button" variant="brand" size="xl" className="group max-sm:flex-1" onClick={() => void go(step + 1)}>
                다음 <ArrowRight aria-hidden className="transition-transform group-hover:translate-x-1" />
              </Button>
            )}
          </div>
        </div>
      </form>
    </FormProvider>
  );
}
