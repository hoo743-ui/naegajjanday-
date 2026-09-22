import io
import os
import sys

WEB = r"C:\Users\LG\OneDrive\바탕 화면\링커스\내가짠데이\apps\web"
os.chdir(WEB)
DRY = "--apply" not in sys.argv  # without --apply: only check every anchor, write nothing


def edit(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert s.count(a) == 1, (path, s.count(a), a[:80])
        s = s.replace(a, b, 1)
    if not DRY:
        io.open(path, "w", encoding="utf-8", newline="\n").write(s)


# ── schema ────────────────────────────────────────────────────
edit("src/components/plan/schema.ts", [
    ('''    /** efficient = 가깝고 알뜰하게 · fun = 재미 우선 */
    style: z.enum(["efficient", "fun"]),''', '''    /** efficient = 가깝고 알뜰하게 · fun = 재미 우선. docs/30 부터는 "어떤 하루"에서 읽힌다(특별한 경험 → fun) */
    style: z.enum(["efficient", "fun"]),
    /** 어떤 하루 (docs/30): 0~2개. 비워 두면 짠이가 균형 있게 */
    pace: z.array(z.enum(["relaxed", "packed", "foodie", "special"])).max(2),
    /** 얼마나 이동해도 괜찮은지: 거리 필터가 아니라 엔진의 이동 선호 (docs/29) */
    move_style: z.enum(["local", "balanced", "explorer"]),
    /** 꼭 반영하고 싶은 것 (선택) */
    wishes: z.array(z.enum(["night", "walk", "exhibition", "value", "romantic"])),'''),
    ('''  style: "efficient",
  focus: "",''', '''  style: "efficient",
  pace: [],
  move_style: "balanced",
  wishes: [],
  focus: "",'''),
    ('''  { key: "taste", title: "취향", question: "마지막으로 취향만 알려 주세요", fields: ["style", "focus", "rainy", "with_bar", "with_baseball", "liked_tags", "disliked_tags", "transport"] },''',
     '''  // docs/30: 취향은 세 개의 짧은 질문. 세부 태그는 마지막 질문의 "더 자세히" 안에 있다
  { key: "day", title: "하루", question: "오늘 어떤 하루를 원하세요?", fields: ["pace", "style"] },
  { key: "move", title: "이동", question: "얼마나 이동해도 괜찮아요?", fields: ["move_style", "transport"] },
  { key: "wish", title: "원하는 것", question: "꼭 반영하고 싶은 게 있나요?", fields: ["wishes", "focus", "rainy", "with_bar", "with_baseball", "liked_tags", "disliked_tags"] },'''),
])

# ── types ─────────────────────────────────────────────────────
edit("src/lib/api/types.ts", [
    ('''  /** 여행 일정의 하루를 다시 짤 때: 바꿀 그 날의 코스 id. 새 코스가 같은 여행의 같은 날 자리에 들어간다 */
  replaces?: string;
}''', '''  /** 여행 일정의 하루를 다시 짤 때: 바꿀 그 날의 코스 id. 새 코스가 같은 여행의 같은 날 자리에 들어간다 */
  replaces?: string;
  /** docs/30 세 질문: 어떤 하루 · 얼마나 이동 · 꼭 원하는 것 (해석은 API 가 한다) */
  pace?: ("relaxed" | "packed" | "foodie" | "special")[];
  move_style?: MoveStyle;
  wishes?: ("night" | "walk" | "exhibition" | "value" | "romantic")[];
}'''),
])

# ── analytics ─────────────────────────────────────────────────
edit("src/lib/analytics/events.ts", [
    ('''  plan_step_completed: { step: 1 | 2 | 3 | 4; step_name: "region" | "purpose" | "budget" | "taste"; value?: string };''',
     '''  plan_step_completed: { step: 1 | 2 | 3 | 4 | 5 | 6 | 7; step_name: "region" | "purpose" | "budget" | "day" | "move" | "wish" | "confirm"; value?: string };
  /** docs/30 세 질문: 어느 단계에서 멈추는지 보려고. 개인정보 없이 고른 값의 코드만 */
  preference_step_view: { step: "day" | "move" | "wish" | "confirm" };
  preference_style_selected: { pace: string };
  travel_preference_selected: { move_style: string };
  quick_preference_selected: { wish: string; on: boolean };
  advanced_preference_opened: Record<string, never>;
  advanced_preference_selected: { tag: string; state: "like" | "avoid" | "none" };
  preference_skipped: { step: "day" | "wish" };
  course_generation_started: { pace: number; wishes: number; detailed: number; move_style: string; from: "confirm" };'''),
])

# ── progress receipt: six steps ───────────────────────────────
edit("src/components/plan/ReceiptProgress.tsx", [
    ('''      <ol aria-label="진행 단계" className="receipt grid grid-cols-4 px-1 py-2">''',
     '''      <ol aria-label="진행 단계" className="receipt grid grid-cols-6 px-1 py-2">'''),
    ('''              <button type="button" disabled={!done} onClick={() => onJump(i)} aria-label={label(i, step)} className="block w-full min-w-0 px-2.5 py-1.5 text-left disabled:cursor-default">''',
     '''              <button type="button" disabled={!done} onClick={() => onJump(i)} aria-label={label(i, step)} className="block w-full min-w-0 px-1.5 py-1.5 text-left disabled:cursor-default sm:px-2.5">'''),
    ('''                <span className={cn("mt-0.5 block truncate text-caption font-semibold", value && i <= step ? "text-ink" : "text-ink/25")}>{value && i <= step ? value : "· · ·"}</span>''',
     '''                {/* 여섯 칸이 390px 에 들어가도록: 고른 값은 태블릿부터 */}
                <span className={cn("mt-0.5 hidden truncate text-caption font-semibold sm:block", value && i <= step ? "text-ink" : "text-ink/25")}>{value && i <= step ? value : "· · ·"}</span>'''),
    ('''                  {String(i + 1).padStart(2, "0")} {s.title.split(" · ")[0]}''',
     '''                  <span className="max-sm:hidden">{String(i + 1).padStart(2, "0")}</span> <span className="truncate">{s.title.split(" · ")[0]}</span>'''),
])

# ── wizard ────────────────────────────────────────────────────
edit("src/components/plan/PlanWizard.tsx", [
    ('''import { BudgetStep, PurposeStep, RegionStep, TasteStep } from "./steps";''',
     '''import { BudgetStep, PurposeStep, RegionStep } from "./steps";
import { ConfirmView, DayStep, MoveStep, WishStep } from "./PreferenceSteps";
import { MOVE_LABEL, PACE_LABEL, WISH_LABEL } from "@/lib/preference";'''),
    ('''  const [step, setStep] = useState(0);''', '''  const [step, setStep] = useState(0);
  // docs/30: 세 질문이 끝나면 한 번 확인한다 ("좋아요. 이렇게 이해했어요.")
  const [confirming, setConfirming] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);'''),
    ('''  const jump = (next: number) => {
    if (next === step) {''', '''  const jump = (next: number) => {
    setConfirming(false);
    if (next === step) {'''),
    ('''      track("plan_step_completed", {
        step: (step + 1) as 1 | 2 | 3 | 4,
        step_name: current.key,
        value: current.key === "region" ? values.region : current.key === "purpose" ? values.purpose : undefined,
      });
      if (current.key === "budget") budgetTouched.current = true;
    }
    jump(next);
  };''', '''      track("plan_step_completed", {
        step: (step + 1) as 1 | 2 | 3 | 4 | 5 | 6,
        step_name: current.key,
        value: current.key === "region" ? values.region : current.key === "purpose" ? values.purpose : undefined,
      });
      if (current.key === "budget") budgetTouched.current = true;
      if (current.key === "day" && values.pace.length === 0) track("preference_skipped", { step: "day" });
      if (current.key === "wish" && values.wishes.length === 0 && values.liked_tags.length === 0) track("preference_skipped", { step: "wish" });
      if (next >= STEPS.length) {
        // 마지막 질문 다음은 제출이 아니라 확인
        setConfirming(true);
        track("preference_step_view", { step: "confirm" });
        focusPending.current = true;
        return;
      }
      const key = STEPS[next]?.key;
      if (key === "day" || key === "move" || key === "wish") track("preference_step_view", { step: key });
    }
    jump(next);
  };'''),
    ('''    const target = STEPS.findIndex((s) => s.fields.some((field) => errors[field]));
    jump(target >= 0 ? target : step);''', '''    const target = STEPS.findIndex((s) => s.fields.some((field) => errors[field as keyof PlanValues]));
    jump(target >= 0 ? target : step);'''),
    ('''      transport: data.transport,
      preferences: { liked_tags: data.liked_tags, disliked_tags: data.disliked_tags, exclude_place_ids: [] },
      alternatives: 2,
    };
    track("plan_step_completed", { step: 4, step_name: "taste" });''', '''      transport: data.transport,
      preferences: { liked_tags: data.liked_tags, disliked_tags: data.disliked_tags, exclude_place_ids: [] },
      // docs/30: 고른 말 그대로 보낸다 — 엔진의 손잡이로 바꾸는 것은 API 의 해석 레이어
      ...(data.pace.length > 0 ? { pace: data.pace } : {}),
      move_style: data.move_style,
      ...(data.wishes.length > 0 ? { wishes: data.wishes } : {}),
      alternatives: 2,
    };
    track("plan_step_completed", { step: 7, step_name: "confirm" });
    track("course_generation_started", { pace: data.pace.length, wishes: data.wishes.length, detailed: data.liked_tags.length + data.disliked_tags.length, move_style: data.move_style, from: "confirm" });'''),
    ('''  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  // 진행 영수증의 줄''', '''  const current = STEPS[step];
  // 제출은 확인 화면에서만 한다
  const isLast = confirming;

  // 진행 영수증의 줄'''),
    ('''    { value: step >= 3 ? `${values.style === "fun" ? "재미 우선" : "알뜰 · 효율"} · ${TRANSPORT_LABEL[values.transport]}` : undefined },
  ];''', '''    { value: step >= 3 ? (values.pace.length ? values.pace.map((p) => PACE_LABEL[p]).join(" · ") : "짠이가 알아서") : undefined },
    { value: step >= 4 ? `${MOVE_LABEL[values.move_style]} · ${TRANSPORT_LABEL[values.transport]}` : undefined },
    { value: step >= 5 ? (values.wishes.length ? values.wishes.map((w) => WISH_LABEL[w]).join(" · ") : "없음") : undefined },
  ];'''),
    ('''        : step === 2
          ? { mood: "done" as const, line: `${values.party_size}명이서 ${won(values.budget_total)}, 알맞게 써 볼게요` }
          : { mood: "cheers" as const, line: "거의 다 됐어요. 취향만 알려 주세요" };''', '''        : step === 2
          ? { mood: "done" as const, line: `${values.party_size}명이서 ${won(values.budget_total)}, 알맞게 써 볼게요` }
          : confirming
            ? { mood: "cheers" as const, line: "이대로 짜 볼게요" }
            : step === 3
              ? { mood: "think" as const, line: values.pace.length ? `${values.pace.map((p) => PACE_LABEL[p]).join(" · ")}, 알겠어요` : "어떤 하루면 좋을까요?" }
              : step === 4
                ? { mood: "wink" as const, line: values.move_style === "explorer" ? "좋은 곳이면 조금 더 가 볼게요" : values.move_style === "local" ? "가까운 곳끼리 이을게요" : "적당히 움직일게요" }
                : { mood: "cheers" as const, line: "거의 다 됐어요. 없으면 넘어가도 돼요" };'''),
    ('''              <h1 ref={headingRef} tabIndex={-1} className="mb-6 text-h1 font-bold outline-none">
                {current?.question}
              </h1>''', '''              <h1 ref={headingRef} tabIndex={-1} className="mb-6 text-h1 font-bold outline-none">
                {confirming ? "좋아요. 이렇게 이해했어요." : current?.question}
              </h1>'''),
    ('''            <motion.div
              key={step}''', '''            <motion.div
              key={confirming ? "confirm" : step}'''),
    ('''              {step === 0 ? <RegionStep /> : null}
              {step === 1 ? <PurposeStep onPicked={() => (budgetTouched.current = false)} /> : null}
              {step === 2 ? <BudgetStep purpose={purpose} /> : null}
              {step === 3 ? <TasteStep /> : null}''', '''              {confirming ? (
                <ConfirmView
                  input={{
                    pace: values.pace,
                    move_style: values.move_style,
                    wishes: values.wishes,
                    liked_tags: values.liked_tags,
                    disliked_tags: values.disliked_tags,
                    budget_total: values.budget_total,
                    party_size: values.party_size,
                  }}
                />
              ) : (
                <>
                  {step === 0 ? <RegionStep /> : null}
                  {step === 1 ? <PurposeStep onPicked={() => (budgetTouched.current = false)} /> : null}
                  {step === 2 ? <BudgetStep purpose={purpose} /> : null}
                  {step === 3 ? <DayStep /> : null}
                  {step === 4 ? <MoveStep /> : null}
                  {step === 5 ? <WishStep detailsOpen={detailsOpen} onDetails={setDetailsOpen} /> : null}
                </>
              )}'''),
    ('''            {step > 0 ? (
              <Button type="button" variant="soft" size="xl" onClick={() => void go(step - 1)} className="max-sm:px-4">
                <ArrowLeft aria-hidden /> <span className="max-sm:sr-only">이전</span>
              </Button>
            ) : null}''', '''            {confirming ? (
              <Button
                type="button"
                variant="soft"
                size="xl"
                className="max-sm:px-4"
                onClick={() => {
                  // "조금 더 알려주기": 마지막 질문으로 돌아가 세부 설정을 펼친다
                  setDetailsOpen(true);
                  track("advanced_preference_opened", {});
                  jump(STEPS.length - 1);
                }}
              >
                <ArrowLeft aria-hidden /> 조금 더 알려주기
              </Button>
            ) : step > 0 ? (
              <Button type="button" variant="soft" size="xl" onClick={() => void go(step - 1)} className="max-sm:px-4">
                <ArrowLeft aria-hidden /> <span className="max-sm:sr-only">이전</span>
              </Button>
            ) : null}'''),
    ('''                <Sparkles aria-hidden /> 코스 짜 주세요''', '''                <Sparkles aria-hidden /> 이대로 코스 짜 주세요'''),
])
print("dry-run: every anchor found" if DRY else "applied")
