"use client";

import { useId, useMemo } from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { Car, Footprints, Heart, PartyPopper, PiggyBank, X, Minus, Plus, TrainFront, type LucideIcon } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { JjaniBubble } from "@/components/mascot/JjaniBubble";
import { PurposeIcon } from "@/components/PurposeIcon";
import { Skeleton } from "@/components/ui/skeleton";
import { usePurposes, useTags } from "@/lib/api/hooks";
import type { CourseStyle, Purpose, Tag, Transport } from "@/lib/api/types";
import { won, wonCompact } from "@/lib/format";
import { budgetReaction } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";
import { MeetTimeCard } from "./MeetTimeCard";
import { RegionPicker } from "./RegionPicker";
import type { PlanValues } from "./schema";

const optionCard =
  "flex cursor-pointer items-center gap-3.5 rounded-[20px] border-2 border-transparent bg-white p-4 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card peer-checked:border-blue-deep peer-checked:bg-blue-soft peer-focus-visible:outline-[3px] peer-focus-visible:outline-offset-2 peer-focus-visible:outline-blue";

function FieldError({ name }: { name: keyof PlanValues }) {
  const { formState } = useFormContext<PlanValues>();
  const message = formState.errors[name]?.message;
  return message ? (
    <p role="alert" className="mt-3 text-sm font-bold text-danger">
      {message}
    </p>
  ) : null;
}

// ── 1. 지역 ─────────────────────────────────────────────────
/** 시도 → 시·군 → 구 → 동네로 들어가며 고르고, 검색하면 지역과 지하철역이 함께 나온다 (RegionPicker). */
export function RegionStep() {
  const { setValue } = useFormContext<PlanValues>();
  const selected = useWatch<PlanValues, "region">({ name: "region" });
  return (
    <div>
      <RegionPicker value={selected} onChange={(next) => setValue("region", next, { shouldValidate: true, shouldDirty: true })} />
      <FieldError name="region" />
    </div>
  );
}

// ── 2. 목적 ─────────────────────────────────────────────────
export function PurposeStep({ onPicked }: { onPicked: (purpose: Purpose) => void }) {
  const { register, setValue } = useFormContext<PlanValues>();
  const selected = useWatch<PlanValues, "purpose">({ name: "purpose" });
  const purposes = usePurposes();

  if (purposes.isPending) {
    return (
      <div className="grid gap-3 sm:grid-cols-2" aria-busy="true">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-[92px] rounded-[20px]" />
        ))}
      </div>
    );
  }
  if (purposes.isError) return <ErrorState error={purposes.error} onRetry={() => void purposes.refetch()} size="sm" />;
  if (purposes.data.items.length === 0) return <EmptyState size="sm" title="고를 수 있는 목적이 아직 없어요" description="잠시 뒤에 다시 와 주세요." />;

  return (
    <fieldset>
      <legend className="sr-only">약속 목적 선택</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        {purposes.data.items.map((p) => (
          <label key={p.code} className="relative block">
            <input
              type="radio"
              value={p.code}
              className="peer sr-only"
              {...register("purpose")}
              checked={selected === p.code}
              onChange={() => {
                setValue("purpose", p.code, { shouldValidate: true, shouldDirty: true });
                onPicked(p);
              }}
            />
            <span className={cn(optionCard, "items-start")}>
              <span className="bg-grad-soft grid size-12 shrink-0 place-items-center rounded-2xl text-blue-deep">
                <PurposeIcon icon={p.icon} className="size-6" />
              </span>
              <span className="min-w-0 flex-1">
                <b className="block text-[17px] font-extrabold tracking-tight">{p.name}</b>
                {p.description ? <span className="block text-[13.5px] text-muted-foreground">{p.description}</span> : null}
                <span className="tabular mt-1 block text-xs font-extrabold text-blue-deep">
                  1인 {wonCompact(p.budget_range.min)} ~ {wonCompact(p.budget_range.max)}
                </span>
              </span>
            </span>
          </label>
        ))}
      </div>
      <FieldError name="purpose" />
    </fieldset>
  );
}

// ── 3. 인원 · 예산 ──────────────────────────────────────────
const QUICK = [
  { label: "알뜰하게", pick: (r: Purpose["budget_range"]) => r.min * 1.3 },
  { label: "적당히", pick: (r: Purpose["budget_range"]) => r.typical ?? (r.min + r.max) / 2 },
  { label: "넉넉하게", pick: (r: Purpose["budget_range"]) => (r.typical ?? (r.min + r.max) / 2) * 1.6 },
  { label: "오늘은 플렉스", pick: (r: Purpose["budget_range"]) => r.max },
];

const roundTo = (value: number, unit: number) => Math.max(unit, Math.round(value / unit) * unit);

export function BudgetStep({ purpose }: { purpose: Purpose | undefined }) {
  const { setValue } = useFormContext<PlanValues>();
  const party = useWatch<PlanValues, "party_size">({ name: "party_size" });
  const budget = useWatch<PlanValues, "budget_total">({ name: "budget_total" });
  const sliderId = useId();

  const range = purpose?.budget_range;
  const maxParty = purpose?.max_party_size ?? 20;
  const sliderMax = roundTo((range?.max ?? 100_000) * party, 5000);
  const step = sliderMax > 400_000 ? 5000 : 1000;
  const sliderMin = 5000;
  const perPerson = Math.round(budget / Math.max(1, party));
  const reaction = budgetReaction(perPerson, range);

  const setParty = (next: number) => {
    const clamped = Math.min(maxParty, Math.max(1, next));
    // 1인당 예산을 유지한 채 인원만 바꾼다
    setValue("party_size", clamped, { shouldValidate: true, shouldDirty: true });
    setValue("budget_total", roundTo(perPerson * clamped, 1000), { shouldValidate: true, shouldDirty: true });
  };
  const setBudget = (next: number) => setValue("budget_total", Math.round(next), { shouldValidate: true, shouldDirty: true });

  return (
    <div className="grid gap-5">
      <section aria-labelledby="party-label" className="rounded-card bg-white p-6 shadow-soft">
        <h3 id="party-label" className="mb-3 text-sm font-extrabold text-muted-foreground">
          몇 명이서?
        </h3>
        <div className="flex items-center gap-4">
          <button type="button" onClick={() => setParty(party - 1)} disabled={party <= 1} aria-label="인원 줄이기" className="grid size-12 place-items-center rounded-[14px] bg-[#F0F4FA] transition-colors hover:bg-line disabled:opacity-40">
            <Minus aria-hidden className="size-5" />
          </button>
          <output aria-live="polite" className="tabular min-w-[64px] text-center text-2xl font-extrabold">
            {party}명
          </output>
          <button type="button" onClick={() => setParty(party + 1)} disabled={party >= maxParty} aria-label="인원 늘리기" className="grid size-12 place-items-center rounded-[14px] bg-[#F0F4FA] transition-colors hover:bg-line disabled:opacity-40">
            <Plus aria-hidden className="size-5" />
          </button>
          {purpose?.max_party_size && party >= maxParty ? (
            <span className="text-[13px] font-bold text-muted-foreground">
              {purpose.name}은(는) {maxParty}명까지예요
            </span>
          ) : null}
        </div>
        <FieldError name="party_size" />
      </section>

      <section className="rounded-card bg-white p-6 shadow-soft">
        <label htmlFor={sliderId} className="mb-4 flex items-baseline justify-between text-sm font-extrabold text-muted-foreground">
          총 예산
          <b className="tabular text-[28px] leading-none font-extrabold tracking-tight text-ink">{won(budget)}</b>
        </label>
        <input
          id={sliderId}
          type="range"
          className="jj-range"
          min={sliderMin}
          max={sliderMax}
          step={step}
          value={Math.min(budget, sliderMax)}
          onChange={(e) => setBudget(Number(e.target.value))}
          aria-valuetext={`${won(budget)}, 1인당 ${won(perPerson)}`}
        />
        <div className="tabular mt-2 flex justify-between text-xs font-bold text-muted-foreground">
          <span>{wonCompact(sliderMin)}</span>
          <span>{wonCompact(sliderMax)}</span>
        </div>

        {range ? (
          <div className="mt-5 flex flex-wrap gap-2" role="group" aria-label="빠른 예산 선택">
            {QUICK.map((qk) => {
              const amount = Math.min(sliderMax, roundTo(qk.pick(range) * party, 1000));
              const on = amount === budget;
              return (
                <button
                  key={qk.label}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setBudget(amount)}
                  className={cn(
                    "tabular rounded-full px-4 py-2.5 text-sm font-extrabold transition-colors",
                    on ? "bg-ink text-white" : "bg-[#F0F4FA] text-ink-2 hover:bg-line",
                  )}
                >
                  {qk.label} · {wonCompact(amount)}
                </button>
              );
            })}
          </div>
        ) : null}

        <p className="tabular mt-5 flex items-baseline justify-between rounded-2xl bg-soft px-4 py-3 text-sm font-bold text-ink-2" aria-live="polite">
          1인당
          <b className="text-xl font-extrabold tracking-tight text-blue-deep">{won(perPerson)}</b>
        </p>
        <FieldError name="budget_total" />
      </section>

      <MeetTimeCard />

      <JjaniBubble mood={reaction.mood} title={reaction.line} bubbleKey={reaction.mood} live size={84} />
    </div>
  );
}

// ── 4. 취향 ─────────────────────────────────────────────────
const TRANSPORTS: { value: Transport; label: string; hint: string; icon: LucideIcon }[] = [
  { value: "walk", label: "걸어서", hint: "구간 20분 이내", icon: Footprints },
  { value: "transit", label: "대중교통", hint: "구간 35분 이내", icon: TrainFront },
  { value: "car", label: "자동차", hint: "구간 40분 이내", icon: Car },
];

const STYLES: { value: CourseStyle; label: string; hint: string; icon: LucideIcon }[] = [
  { value: "efficient", label: "알뜰 · 효율", hint: "가깝고 덜 걷게, 예산을 꽉 채워서", icon: PiggyBank },
  { value: "fun", label: "재미 우선", hint: "북적이는 거리 · 놀거리 포함 · 체인점은 덜", icon: PartyPopper },
];

type TagState = "none" | "like" | "avoid";

/** API 가 group_name 을 주지 않을 때 쓰는 기본 표시명. 모르는 그룹은 코드 그대로 보인다. */
const TAG_GROUP_LABEL: Record<string, string> = {
  mood: "분위기",
  food: "음식",
  activity: "놀거리",
  feature: "편의 · 조건",
};

export function TasteStep() {
  const { setValue, register } = useFormContext<PlanValues>();
  const liked = useWatch<PlanValues, "liked_tags">({ name: "liked_tags" });
  const disliked = useWatch<PlanValues, "disliked_tags">({ name: "disliked_tags" });
  const transport = useWatch<PlanValues, "transport">({ name: "transport" });
  const style = useWatch<PlanValues, "style">({ name: "style" });
  const tags = useTags();

  const groups = useMemo(() => {
    const map = new Map<string, Tag[]>();
    for (const tag of tags.data?.items ?? []) {
      const key = tag.group_name ?? TAG_GROUP_LABEL[tag.group] ?? tag.group;
      map.set(key, [...(map.get(key) ?? []), tag]);
    }
    return [...map.entries()];
  }, [tags.data]);

  const stateOf = (name: string): TagState => (liked.includes(name) ? "like" : disliked.includes(name) ? "avoid" : "none");
  const cycle = (name: string) => {
    const state = stateOf(name);
    const without = (list: string[]) => list.filter((t) => t !== name);
    setValue("liked_tags", state === "none" ? [...liked, name] : without(liked), { shouldDirty: true });
    setValue("disliked_tags", state === "like" ? [...disliked, name] : without(disliked), { shouldDirty: true });
  };

  return (
    <div className="grid gap-5">
      <fieldset className="rounded-card bg-white p-6 shadow-soft">
        <legend className="float-left mb-3 w-full text-sm font-extrabold text-muted-foreground">어떤 코스가 좋아요?</legend>
        <div className="clear-both grid gap-2.5 sm:grid-cols-2">
          {STYLES.map((s) => (
            <label key={s.value} className="relative block">
              <input type="radio" value={s.value} className="peer sr-only" {...register("style")} checked={style === s.value} onChange={() => setValue("style", s.value, { shouldDirty: true })} />
              <span className={cn(optionCard, "bg-soft shadow-none")}>
                <s.icon aria-hidden className="size-7 shrink-0 text-blue-deep" />
                <span className="min-w-0">
                  <b className="block text-[15px] font-extrabold">{s.label}</b>
                  <span className="block text-[12.5px] text-muted-foreground">{s.hint}</span>
                </span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <section className="rounded-card bg-white p-6 shadow-soft">
        <h3 className="text-sm font-extrabold text-muted-foreground">끌리는 분위기 (선택)</h3>
        <p className="mt-1 mb-4 text-[13px] text-muted-foreground">
          한 번 누르면 <b className="text-blue-deep">좋아요</b>, 한 번 더 누르면 <b className="text-pink-deep">피할래요</b>, 또 누르면 해제돼요.
        </p>
        {tags.isPending ? (
          <div className="flex flex-wrap gap-2" aria-busy="true">
            {Array.from({ length: 10 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-20 rounded-full" />
            ))}
          </div>
        ) : tags.isError ? (
          <ErrorState error={tags.error} onRetry={() => void tags.refetch()} size="sm" />
        ) : groups.length === 0 ? (
          <EmptyState size="sm" title="고를 태그가 아직 없어요" description="취향 없이도 코스는 잘 나와요. 그대로 진행해 주세요." />
        ) : (
          <div className="grid gap-4">
            {groups.map(([group, items]) => (
              <div key={group} role="group" aria-label={group}>
                <p className="mb-2 text-xs font-extrabold text-ink-2">{group}</p>
                <div className="flex flex-wrap gap-2">
                  {items.map((tag) => {
                    const state = stateOf(tag.name);
                    return (
                      <button
                        key={tag.code ?? tag.name}
                        type="button"
                        onClick={() => cycle(tag.name)}
                        aria-label={`${tag.name}: ${state === "like" ? "좋아요" : state === "avoid" ? "피할래요" : "선택 안 함"}`}
                        className={cn(
                          "rounded-full border-2 px-4 py-2 text-sm font-extrabold transition-all duration-150 active:scale-95",
                          state === "like" && "border-blue-deep bg-blue-deep text-white",
                          state === "avoid" && "border-pink-deep bg-pink-soft text-pink-deep line-through",
                          state === "none" && "border-transparent bg-[#F0F4FA] text-ink-2 hover:bg-line",
                        )}
                      >
                        {state === "like" ? <Heart aria-hidden className="mr-1 -mt-0.5 inline size-3.5 fill-current" /> : null}
                        {state === "avoid" ? <X aria-hidden className="mr-1 -mt-0.5 inline size-3.5" /> : null}
                        {tag.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <fieldset className="rounded-card bg-white p-6 shadow-soft">
        <legend className="float-left mb-3 w-full text-sm font-extrabold text-muted-foreground">어떻게 이동해요?</legend>
        <div className="clear-both grid grid-cols-3 gap-2.5">
          {TRANSPORTS.map((t) => (
            <label key={t.value} className="relative block">
              <input type="radio" value={t.value} className="peer sr-only" {...register("transport")} checked={transport === t.value} onChange={() => setValue("transport", t.value, { shouldDirty: true })} />
              <span className={cn(optionCard, "flex-col gap-1 bg-soft p-3.5 text-center shadow-none")}>
                <t.icon aria-hidden className="size-6 text-blue-deep" />
                <b className="text-[15px] font-extrabold">{t.label}</b>
                <span className="text-[11.5px] text-muted-foreground">{t.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

    </div>
  );
}
