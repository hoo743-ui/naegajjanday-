"use client";

import { useMemo, useState } from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Car,
  Check,
  ChevronDown,
  CloudRain,
  Compass,
  Footprints,
  Heart,
  Leaf,
  ListChecks,
  MapPin,
  Moon,
  Palette,
  PiggyBank,
  Plus,
  Route,
  Ticket,
  TrainFront,
  Trees,
  Trophy,
  Utensils,
  Wallet,
  Wine,
  X,
  type LucideIcon,
} from "lucide-react";
import { ErrorState, EmptyState } from "@/components/mascot/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { track } from "@/lib/analytics";
import { api } from "@/lib/api/client";
import { useLocalSignature, useTags } from "@/lib/api/hooks";
import { FOCUS_OFF, type Tag, type Transport } from "@/lib/api/types";
import { localSummary, type InterpretInput, type MoveStyle, type Pace, type SummaryLine, type Wish } from "@/lib/preference";
import { cn } from "@/lib/utils";
import type { PlanValues } from "./schema";

/*
 * 위저드 4단계 "취향" (docs/30 · docs/32 B §10): 태그 30여 개를 한 화면에 늘어놓지 않고 짧은 질문 셋 —
 * 오늘 어떤 하루 · 얼마나 이동해도 괜찮은지 · 꼭 반영하고 싶은 것. 세부 태그 · 그날의 사정 · 동네 명물은 "더 자세히" 안에.
 * 아래에는 고른 것을 말로 되읽어 주는 "좋아요. 이렇게 이해했어요." (해석은 API 의 선호 해석 레이어가 한다).
 * 아무것도 고르지 않아도 코스를 짤 수 있다.
 */

// 고르는 칸: 떠오르는 카드가 아니라 테두리 하나 (docs/31 §6). 고르면 파랗게 찍힌다
const choice = "relative flex w-full cursor-pointer items-start gap-3.5 rounded-lg border-[1.5px] p-4 text-left transition-colors duration-200";
const choiceOff = "border-line hover:border-ink-2";
const choiceOn = "border-tomato bg-tomato-soft";
const field = "border-t-[1.5px] border-dashed border-ink/20 pt-6";

function Tick({ on }: { on: boolean }) {
  return (
    <span aria-hidden className={cn("ml-auto grid size-6 shrink-0 place-items-center rounded-full border", on ? "border-tomato bg-tomato text-white" : "border-line bg-white text-transparent")}>
      <Check className="size-3.5" />
    </span>
  );
}

// ── 어떤 하루 ───────────────────────────────────────────────
const PACES: { value: Pace; label: string; hint: string; icon: LucideIcon }[] = [
  { value: "relaxed", label: "여유롭게", hint: "들르는 곳은 적게, 한 곳에 오래", icon: Leaf },
  { value: "packed", label: "알차게", hint: "시간 안에서 여러 곳을 촘촘히", icon: ListChecks },
  { value: "foodie", label: "맛있는 거 중심", hint: "식사에 예산을 더, 동네 맛집 위주", icon: Utensils },
  { value: "special", label: "특별한 경험", hint: "해 보는 것 · 볼거리 위주 (재미 우선)", icon: Ticket },
];
const MAX_PACE = 2;

function DayQuestion() {
  const { setValue } = useFormContext<PlanValues>();
  const pace = useWatch<PlanValues, "pace">({ name: "pace" });
  const toggle = (value: Pace) => {
    const on = pace.includes(value);
    // 세 번째를 고르면 가장 먼저 고른 것이 빠진다 (막지 않는다)
    const next = on ? pace.filter((p) => p !== value) : [...pace, value].slice(-MAX_PACE);
    setValue("pace", next, { shouldDirty: true });
    // "특별한 경험"은 기존의 "재미 우선" 스타일로 읽힌다 (결과 화면의 "재미 우선" 칩)
    setValue("style", next.includes("special") ? "fun" : "efficient", { shouldDirty: true });
    if (!on) track("preference_style_selected", { pace: value });
  };
  const both = pace.includes("relaxed") && pace.includes("packed");
  return (
    <fieldset className="grid gap-3">
      <legend className="float-left w-full text-body font-bold text-ink">
        오늘 어떤 하루를 원하세요? <span className="text-body-sm font-medium text-muted-foreground">하나나 두 개, 안 골라도 괜찮아요</span>
      </legend>
      {/* 좁은 화면에서도 두 칸: 네 개가 한 화면을 다 차지하지 않게 */}
      <div className="clear-both grid grid-cols-2 gap-2.5">
        {PACES.map((p) => {
          const on = pace.includes(p.value);
          return (
            <button key={p.value} type="button" role="checkbox" aria-checked={on} onClick={() => toggle(p.value)} className={cn(choice, "flex-col gap-1.5 p-3.5 sm:flex-row sm:gap-3.5 sm:p-4", on ? choiceOn : choiceOff)}>
              {/* 좁은 화면: 체크 동그라미 대신 아이콘 자리에 체크 — 두 칸에 이름이 눌리지 않게 */}
              <span className="flex w-full items-center gap-2 sm:contents">
                {on ? <Check aria-hidden className="size-5 shrink-0 text-tomato-deep sm:hidden" /> : null}
                <p.icon aria-hidden className={cn("size-5 shrink-0 text-tomato-deep sm:mt-0.5", on && "max-sm:hidden")} />
                <b className="text-body font-bold text-ink sm:hidden">{p.label}</b>
              </span>
              <span className="min-w-0">
                <b className="hidden text-body font-bold text-ink sm:block">{p.label}</b>
                <span className="block text-caption text-muted-foreground sm:mt-0.5 sm:text-body-sm">{p.hint}</span>
              </span>
              <span className="ml-auto hidden sm:block">
                <Tick on={on} />
              </span>
            </button>
          );
        })}
      </div>
      {both ? (
        <p className="border-l-2 border-tomato pl-3 text-body-sm text-ink-2" aria-live="polite">
          여유롭게 + 알차게: 들르는 곳 수는 그대로 두고, 한 곳 한 곳을 더 알차게 골라요.
        </p>
      ) : null}
    </fieldset>
  );
}

// ── 얼마나 이동 ─────────────────────────────────────────────
const MOVES: { value: MoveStyle; label: string; hint: string; icon: LucideIcon }[] = [
  { value: "local", label: "가까운 곳 위주", hint: "고른 동네 안에서 짧게 이어요", icon: MapPin },
  { value: "balanced", label: "적당히 이동", hint: "동네와 바로 옆 생활권까지", icon: Route },
  { value: "explorer", label: "좋은 곳이라면 조금 멀어도", hint: "갈 만한 곳이면 한 정거장 더 가요", icon: Compass },
];
// 약속이 아니라 보통의 모습: 엔진은 구간을 자르지 않고, 길어질수록 조금씩 점수를 잃게 한다 (docs/29)
const TRANSPORTS: { value: Transport; label: string; hint: string; icon: LucideIcon }[] = [
  { value: "walk", label: "걸어서", hint: "한 구간 보통 15분 안팎", icon: Footprints },
  { value: "transit", label: "대중교통", hint: "한 구간 보통 25분 안팎", icon: TrainFront },
  { value: "car", label: "자동차", hint: "한 구간 보통 25분 안팎", icon: Car },
];

function MoveQuestion() {
  const { setValue } = useFormContext<PlanValues>();
  const move = useWatch<PlanValues, "move_style">({ name: "move_style" });
  const transport = useWatch<PlanValues, "transport">({ name: "transport" });
  return (
    <div className={cn(field, "grid gap-5")}>
      <div role="radiogroup" aria-labelledby="move-q" className="grid gap-2.5">
        <p id="move-q" className="text-body font-bold text-ink">
          얼마나 이동해도 괜찮아요?
        </p>
        {MOVES.map((m) => {
          const on = move === m.value;
          return (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => {
                setValue("move_style", m.value, { shouldDirty: true });
                track("travel_preference_selected", { move_style: m.value });
              }}
              className={cn(choice, "items-center py-3.5", on ? choiceOn : choiceOff)}
            >
              <m.icon aria-hidden className="size-5 shrink-0 text-tomato-deep" />
              <span className="min-w-0">
                <b className="block text-body font-bold text-ink">{m.label}</b>
                <span className="block text-body-sm text-muted-foreground">{m.hint}</span>
              </span>
              <Tick on={on} />
            </button>
          );
        })}
      </div>
      <div role="radiogroup" aria-labelledby="transport-q">
        <p id="transport-q" className="mb-2 text-body-sm font-semibold text-ink-2">
          어떻게 다녀요?
        </p>
        <div className="grid grid-cols-3 gap-2">
          {TRANSPORTS.map((t) => {
            const on = transport === t.value;
            return (
              <button
                key={t.value}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => setValue("transport", t.value, { shouldDirty: true })}
                className={cn("flex min-h-11 flex-col items-center gap-0.5 rounded-lg border-[1.5px] px-2 py-2.5 text-center transition-colors", on ? choiceOn : choiceOff)}
              >
                <t.icon aria-hidden className="size-4 text-tomato-deep" />
                <b className="text-body-sm font-bold text-ink">{t.label}</b>
                <span className="text-caption text-muted-foreground">{t.hint}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── 꼭 원하는 것 ─────────────────────────────────────────────
const WISHES: { value: Wish; label: string; icon: LucideIcon }[] = [
  { value: "night", label: "야경", icon: Moon },
  { value: "walk", label: "산책", icon: Trees },
  { value: "exhibition", label: "전시", icon: Palette },
  { value: "value", label: "가성비", icon: PiggyBank },
  { value: "romantic", label: "로맨틱", icon: Heart },
];
/** 세부 태그 묶음의 순서와 이름 (API 의 group 코드 → 화면 이름) */
const GROUP_ORDER = ["activity", "food", "mood", "feature"] as const;
const GROUP_LABEL: Record<string, string> = { activity: "놀거리", food: "음식", mood: "분위기", feature: "편의 · 조건" };

type TagState = "none" | "like" | "avoid";

function WishQuestion() {
  const { setValue } = useFormContext<PlanValues>();
  const wishes = useWatch<PlanValues, "wishes">({ name: "wishes" });
  const liked = useWatch<PlanValues, "liked_tags">({ name: "liked_tags" });
  const disliked = useWatch<PlanValues, "disliked_tags">({ name: "disliked_tags" });
  // 세부 설정을 이미 골라 둔 채로 돌아오면 펼친 채로
  const [open, setOpen] = useState(liked.length + disliked.length > 0);
  const toggle = (value: Wish) => {
    const on = wishes.includes(value);
    setValue("wishes", on ? wishes.filter((w) => w !== value) : [...wishes, value], { shouldDirty: true });
    track("quick_preference_selected", { wish: value, on: !on });
  };
  return (
    <div className={cn(field, "grid gap-4")}>
      <div role="group" aria-labelledby="wish-q" className="grid gap-3">
        <p id="wish-q" className="text-body font-bold text-ink">
          꼭 반영하고 싶은 게 있나요? <span className="text-body-sm font-medium text-muted-foreground">없으면 넘어가도 돼요</span>
        </p>
        <div className="flex flex-wrap gap-2">
          {WISHES.map((w) => {
            const on = wishes.includes(w.value);
            return (
              <button
                key={w.value}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(w.value)}
                className={cn("inline-flex min-h-11 items-center gap-2 rounded-full border-[1.5px] px-4 text-body font-semibold transition-colors", on ? "border-tomato bg-tomato-soft text-tomato-deep" : "border-line text-ink hover:border-ink-2")}
              >
                {on ? <Check aria-hidden className="size-4" /> : <w.icon aria-hidden className="size-4 text-tomato-deep" />}
                {w.label}
              </button>
            );
          })}
        </div>
      </div>

      <button
        type="button"
        aria-expanded={open}
        aria-controls="plan-details"
        onClick={() => {
          if (!open) track("advanced_preference_opened", {});
          setOpen(!open);
        }}
        className="-ml-1 inline-flex min-h-11 w-fit items-center gap-1.5 rounded-full px-1 text-body-sm font-semibold text-tomato-deep"
      >
        {open ? <ChevronDown aria-hidden className="size-4" /> : <Plus aria-hidden className="size-4" />}
        {open ? "자세한 설정 접기" : "더 자세히 (비 · 술 한잔 · 야구 · 동네 명물 · 세부 취향)"}
      </button>
      {open ? <Details /> : null}
    </div>
  );
}

function Toggle({ on, onChange, icon: Icon, title, hint }: { on: boolean; onChange: (v: boolean) => void; icon: LucideIcon; title: string; hint: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-3.5 border-b border-dashed border-line py-3.5 last:border-b-0">
      <input type="checkbox" className="peer sr-only" checked={on} onChange={(e) => onChange(e.target.checked)} />
      <Icon aria-hidden className="size-5 shrink-0 text-tomato-deep" />
      <span className="min-w-0 flex-1">
        <b className="block text-body font-semibold text-ink">{title}</b>
        <span className="block text-caption text-muted-foreground">{hint}</span>
      </span>
      <span aria-hidden className={cn("grid size-6 shrink-0 place-items-center rounded-md border peer-focus-visible:ring-2 peer-focus-visible:ring-tomato", on ? "border-tomato bg-tomato text-white" : "border-line bg-white text-transparent")}>
        <Check className="size-3.5" />
      </span>
    </label>
  );
}

/** "더 자세히": 예전 취향 화면의 모든 것 — 그날의 사정 · 동네 명물 · 세부 태그(좋아요/피할래요). 지운 것은 없다 */
function Details() {
  const { setValue } = useFormContext<PlanValues>();
  const liked = useWatch<PlanValues, "liked_tags">({ name: "liked_tags" });
  const disliked = useWatch<PlanValues, "disliked_tags">({ name: "disliked_tags" });
  const focus = useWatch<PlanValues, "focus">({ name: "focus" });
  const withBar = useWatch<PlanValues, "with_bar">({ name: "with_bar" });
  const rainy = useWatch<PlanValues, "rainy">({ name: "rainy" });
  const withBaseball = useWatch<PlanValues, "with_baseball">({ name: "with_baseball" });
  const region = useWatch<PlanValues, "region">({ name: "region" });
  const tags = useTags();
  // 이 동네가 무엇으로 알려져 있는지 — 뚜렷한 명물이 없는 동네면 이 칸은 아예 안 나온다
  const local = useLocalSignature(region || undefined);
  const specialties = local.data?.specialties ?? [];

  const groups = useMemo(() => {
    const map = new Map<string, Tag[]>();
    for (const tag of tags.data?.items ?? []) map.set(tag.group, [...(map.get(tag.group) ?? []), tag]);
    const rank = (g: string) => (GROUP_ORDER as readonly string[]).indexOf(g) + 1 || 99;
    // 묶음 이름이 API 원시 코드(activity/…)로 새지 않게: group_name → 기본 이름 → 코드
    return [...map.entries()].sort((a, b) => rank(a[0]) - rank(b[0])).map(([g, items]) => [items[0]?.group_name ?? GROUP_LABEL[g] ?? g, items] as const);
  }, [tags.data]);

  const stateOf = (name: string): TagState => (liked.includes(name) ? "like" : disliked.includes(name) ? "avoid" : "none");
  const cycle = (name: string) => {
    const state = stateOf(name);
    const without = (list: string[]) => list.filter((t) => t !== name);
    setValue("liked_tags", state === "none" ? [...liked, name] : without(liked), { shouldDirty: true });
    setValue("disliked_tags", state === "like" ? [...disliked, name] : without(disliked), { shouldDirty: true });
    track("advanced_preference_selected", { tag: name, state: state === "none" ? "like" : state === "like" ? "avoid" : "none" });
  };

  return (
    <div id="plan-details" className="grid gap-5 border-l-2 border-line pl-4">
      <section>
        <h3 className="sr-only">그날의 사정</h3>
        <Toggle on={rainy} onChange={(v) => setValue("rainy", v, { shouldDirty: true })} icon={CloudRain} title="비 오는 날이에요" hint="실내 위주로 짜요. 산책 대신 전시 · 실내 놀거리를 넣어요." />
        <Toggle on={withBar} onChange={(v) => setValue("with_bar", v, { shouldDirty: true })} icon={Wine} title="술 한잔 포함" hint="저녁 5시 이후에 술집 한 곳을 꼭 넣어요. 예산도 떼어 둘게요." />
        <Toggle on={withBaseball} onChange={(v) => setValue("with_baseball", v, { shouldDirty: true })} icon={Trophy} title="야구 보러 가요" hint="1군 구장이 있는 동네면 넣어요. 경기 일정은 직접 확인해 주세요." />
      </section>

      {specialties.length > 0 ? (
        <fieldset>
          <legend className="float-left mb-1 w-full text-body-sm font-semibold text-ink-2">{local.data?.region}에 왔다면</legend>
          <p className="clear-both mb-3 text-body-sm text-muted-foreground">이 동네 간판에 유독 많이 걸린 말이에요. 하나 고르면 그 집을 꼭 넣어요.</p>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="꼭 넣을 동네 명물">
            {[{ value: "", label: "짠이가 알아서", hint: "" }, ...specialties.map((s) => ({ value: s.word, label: s.word, hint: `${s.count}곳` })), { value: FOCUS_OFF, label: "상관없어요", hint: "" }].map((o) => {
              const on = focus === o.value;
              return (
                <button key={o.value || "auto"} type="button" role="radio" aria-checked={on} onClick={() => setValue("focus", o.value, { shouldDirty: true })} className={cn("inline-flex min-h-11 items-center gap-1.5 rounded-full border-[1.5px] px-3.5 text-body-sm font-semibold", on ? "border-tomato bg-tomato-soft text-tomato-deep" : "border-line text-ink hover:border-ink-2")}>
                  {o.label}
                  {o.hint ? <span className="tabular text-caption text-muted-foreground">{o.hint}</span> : null}
                </button>
              );
            })}
          </div>
        </fieldset>
      ) : null}

      <section>
        <h3 className="text-body-sm font-semibold text-ink-2">세부 취향</h3>
        <p className="mt-1 mb-2 text-caption text-muted-foreground">
          한 번 누르면 <b className="text-tomato-deep">좋아요</b>, 한 번 더 누르면 <b className="text-pink-deep">피할래요</b>, 또 누르면 해제돼요.
        </p>
        {tags.isPending ? (
          <div className="flex flex-wrap gap-2" aria-busy="true">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-9 w-20 rounded-full" />
            ))}
          </div>
        ) : tags.isError ? (
          <ErrorState error={tags.error} onRetry={() => void tags.refetch()} size="sm" />
        ) : groups.length === 0 ? (
          <EmptyState size="sm" title="고를 태그가 아직 없어요" description="세부 취향 없이도 코스는 잘 나와요." />
        ) : (
          <div className="divide-y divide-dashed divide-line">
            {groups.map(([group, items]) => {
              const picked = items.filter((t) => stateOf(t.name) !== "none").length;
              return (
                <details key={group} className="group py-2" open={picked > 0}>
                  <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-body-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
                    <span>
                      {group}
                      {picked > 0 ? <span className="tabular ml-2 text-caption font-semibold text-tomato-deep">{picked}개 고름</span> : null}
                    </span>
                    <ChevronDown aria-hidden className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
                  </summary>
                  <div role="group" aria-label={group} className="flex flex-wrap gap-2 pt-1 pb-1">
                    {items.map((tag) => {
                      const state = stateOf(tag.name);
                      return (
                        <button
                          key={tag.code ?? tag.name}
                          type="button"
                          onClick={() => cycle(tag.name)}
                          aria-label={`${tag.name}: ${state === "like" ? "좋아요" : state === "avoid" ? "피할래요" : "선택 안 함"}`}
                          className={cn(
                            "rounded-full border-[1.5px] px-3.5 py-1.5 text-body-sm font-semibold transition-colors",
                            state === "like" && "border-tomato bg-tomato-soft text-tomato-deep",
                            state === "avoid" && "border-pink-deep bg-pink-soft text-pink-deep line-through",
                            state === "none" && "border-line text-ink-2 hover:border-ink-2",
                          )}
                        >
                          {state === "like" ? <Heart aria-hidden className="mr-1 -mt-0.5 inline size-3.5 fill-current" /> : null}
                          {state === "avoid" ? <X aria-hidden className="mr-1 -mt-0.5 inline size-3.5" /> : null}
                          {tag.name}
                        </button>
                      );
                    })}
                  </div>
                </details>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

// ── 이렇게 이해했어요 ───────────────────────────────────────────
const LINE_ICON: Record<SummaryLine["kind"], LucideIcon> = { pace: Leaf, move: Route, wish: Heart, detail: ListChecks, budget: Wallet };

/**
 * 고른 것을 말로 되읽어 준다: 내부 값이 아니라 문장으로, 영수증의 줄처럼 (docs/30 · docs/32 B §10).
 * API 가 답하기 전에도 · 실패해도 같은 규칙의 로컬 요약이 있어 비지 않는다. 고를 때마다 조용히 바뀐다(깜빡이지 않게 이전 답을 유지).
 */
function Understood() {
  const values = useWatch<PlanValues>();
  const input: InterpretInput = {
    pace: values.pace ?? [],
    move_style: values.move_style ?? "balanced",
    wishes: values.wishes ?? [],
    liked_tags: values.liked_tags ?? [],
    disliked_tags: values.disliked_tags ?? [],
    budget_total: values.budget_total ?? 0,
    party_size: values.party_size ?? 1,
  };
  const understood = useQuery({
    queryKey: ["interpret", input],
    queryFn: ({ signal }) => api.post<{ summary: SummaryLine[] }>("/courses/interpret", input, { timeoutMs: 6000, signal }),
    staleTime: 60_000,
    retry: 1,
    placeholderData: keepPreviousData,
  });
  const lines = understood.data?.summary?.length ? understood.data.summary : localSummary(input);
  return (
    <section aria-labelledby="understood" className={cn(field, "grid gap-2")}>
      <h2 id="understood" className="text-body font-bold text-ink">
        좋아요. 이렇게 이해했어요.
      </h2>
      <ul aria-live="polite" className="divide-y divide-dashed divide-ink/15">
        {lines.map((line) => {
          const Icon = LINE_ICON[line.kind] ?? Check;
          return (
            <li key={`${line.kind}-${line.key}`} className="flex items-center gap-3 py-2.5">
              <Icon aria-hidden className={cn("size-4 shrink-0", line.kind === "budget" ? "text-gold-ink" : "text-tomato-deep")} />
              <span className={cn("text-body text-ink", line.kind === "budget" ? "tabular font-bold text-gold-ink" : "font-semibold")}>{line.text}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function TasteStep() {
  return (
    <div className="grid gap-7">
      <DayQuestion />
      <MoveQuestion />
      <WishQuestion />
      <Understood />
    </div>
  );
}
