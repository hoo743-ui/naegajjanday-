"use client";

import { useId } from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { X, Minus, Plus } from "lucide-react";
import { Receipt } from "@/components/brand/Receipt";
import { sampleCourse } from "@/components/brand/sample-course";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { JjaniBubble } from "@/components/mascot/JjaniBubble";
import { PurposeIcon } from "@/components/PurposeIcon";
import { Skeleton } from "@/components/ui/skeleton";
import { decodeCampus, isPointValue, usePurposes, useRegionName } from "@/lib/api/hooks";
import type { Purpose } from "@/lib/api/types";
import { won, wonCompact } from "@/lib/format";
import { budgetReaction } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";
import { BudgetChip } from "@/components/brand/BudgetChip";
import { HotPlaces } from "./HotPlaces";
import { MeetTimeCard } from "./MeetTimeCard";
import { RegionPicker } from "./RegionPicker";
import type { PlanValues } from "./schema";

// 고르는 칸 (docs/31 §6): 떠오르는 흰 카드가 아니라 종이 위에 그은 테두리 하나. 고르면 파랗게 찍힌다
const optionCard =
  "flex cursor-pointer items-center gap-3.5 rounded-lg border-[1.5px] border-line p-4 transition-colors duration-200 hover:border-ink-2 peer-checked:border-tomato peer-checked:bg-tomato-soft peer-focus-visible:outline-[3px] peer-focus-visible:outline-offset-2 peer-focus-visible:outline-blue";

function FieldError({ name }: { name: keyof PlanValues }) {
  const { formState } = useFormContext<PlanValues>();
  const message = formState.errors[name]?.message;
  return message ? (
    <p role="alert" className="mt-3 text-body-sm font-semibold text-danger">
      {message}
    </p>
  ) : null;
}

// ── 1. 지역 ─────────────────────────────────────────────────
/** 시도 → 시·군 → 구 → 동네로 들어가며 고르고, 검색하면 지역과 지하철역이 함께 나온다 (RegionPicker). */
const MAX_REGIONS = 3;

/** 지역 이름. 동은 전체 목록에 없어서 한 건씩 읽는다 → 읽는 동안은 비워 둔다(slug 를 보여 주지 않는다). */
function RegionName({ slug }: { slug: string }) {
  return <>{useRegionName(slug) ?? ""}</>;
}

export function RegionStep() {
  const { setValue } = useFormContext<PlanValues>();
  const selected = useWatch<PlanValues, "region">({ name: "region" });
  const before = useWatch<PlanValues, "regions_before">({ name: "regions_before" });
  const partySize = useWatch<PlanValues, "party_size">({ name: "party_size" });
  const selectedName = useRegionName(selected || undefined) ?? "";
  // 역 주변 코스는 한 지점이 기준이라 다른 동네와 잇지 않는다
  const canAdd = Boolean(selected) && !isPointValue(selected) && before.length < MAX_REGIONS - 1 && !before.includes(selected);
  const addAnother = () => {
    setValue("regions_before", [...before, selected], { shouldDirty: true });
    setValue("region", "", { shouldDirty: true });
  };
  return (
    <div className="grid gap-4">
      {before.length > 0 ? (
        <section aria-label="들를 동네 순서" className="border-t-[1.5px] border-dashed border-ink/20 pt-6">
          <h3 className="text-body-sm font-semibold text-muted-foreground">이 순서로 들러요</h3>
          <ol className="mt-2.5 flex flex-wrap items-center gap-2">
            {before.map((slug, i) => (
              <li key={slug} className="inline-flex items-center gap-1.5 rounded-full border border-tomato bg-tomato-soft py-1.5 pr-1.5 pl-3 text-body-sm font-semibold text-tomato-deep">
                <span className="tabular">{i + 1}.</span> <RegionName slug={slug} />
                <button
                  type="button"
                  aria-label={`${i + 1}번째 동네 빼기`}
                  onClick={() => setValue("regions_before", before.filter((s) => s !== slug), { shouldDirty: true })}
                  className="grid size-6 place-items-center rounded-full hover:bg-white"
                >
                  <X aria-hidden className="size-3.5" />
                </button>
              </li>
            ))}
            <li className="text-body-sm font-semibold text-ink-2">
              <span className="tabular">{before.length + 1}.</span> {selected ? selectedName : "아래에서 다음 동네를 골라 주세요"}
            </li>
          </ol>
          <p className="mt-2.5 text-caption text-muted-foreground">예산과 시간을 동네마다 나눠 쓰고, 남은 돈은 다음 동네로 넘겨요. 동네 사이는 대중교통(또는 고른 이동수단)으로 이어요.</p>
        </section>
      ) : null}
      <RegionPicker value={selected} onChange={(next) => setValue("region", next, { shouldValidate: true, shouldDirty: true })} />
      {canAdd ? (
        <button type="button" onClick={addAnother} className="inline-flex items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line bg-white px-4 py-3.5 text-body font-bold text-ink-2 hover:border-tomato hover:text-tomato-deep">
          <Plus aria-hidden className="size-4" />
          {selectedName}에 이어 다른 동네도 들르기
        </button>
      ) : null}
      <FieldError name="region" />
      {selected && !isPointValue(selected) ? <HotPlaces key={selected} regionSlug={selected} partySize={partySize} /> : null}
    </div>
  );
}

// ── 2. 목적 ─────────────────────────────────────────────────
export function PurposeStep({ onPicked }: { onPicked: (purpose: Purpose) => void }) {
  const { register, setValue } = useFormContext<PlanValues>();
  const selected = useWatch<PlanValues, "purpose">({ name: "purpose" });
  const extra = useWatch<PlanValues, "purposes_extra">({ name: "purposes_extra" });
  const region = useWatch<PlanValues, "region">({ name: "region" });
  // docs/34: 대학교를 골랐으면 그 하루의 목적(캠퍼스 탐방 · 대학가 맛집 · 축제 즐기기 …)이 먼저 나온다
  const purposes = usePurposes(decodeCampus(region) ? "university" : undefined);

  if (purposes.isPending) {
    return (
      <div className="grid gap-3 sm:grid-cols-2" aria-busy="true">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-[92px] rounded-lg" />
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
                setValue("purposes_extra", extra.filter((c) => c !== p.code), { shouldDirty: true });
                onPicked(p);
              }}
            />
            <span className={cn(optionCard, "items-start")}>
              <PurposeIcon icon={p.icon} className="mt-1 size-6 shrink-0 text-tomato-deep" />
              <span className="min-w-0 flex-1">
                <b className="block text-body-lg font-extrabold">{p.name}</b>
                {p.description ? <span className="block text-body-sm text-muted-foreground">{p.description}</span> : null}
                <span className="tabular mt-1 block text-caption font-extrabold text-tomato-deep">
                  1인 {wonCompact(p.budget_range.min)} ~ {wonCompact(p.budget_range.max)}
                </span>
              </span>
            </span>
          </label>
        ))}
      </div>
      <FieldError name="purpose" />
      {selected && purposes.data.items.length > 1 ? (
        <div className="mt-8 border-t-[1.5px] border-dashed border-ink/20 pt-6" role="group" aria-label="함께 고를 목적">
          <h3 className="text-body-sm font-semibold text-muted-foreground">다른 목적도 겹치나요? (선택)</h3>
          <p className="mt-1 text-body-sm text-ink-2">
            위에서 고른 것이 하루의 틀이 되고, 여기서 더 고른 것까지 모두 맞는 곳을 찾아요. 예를 들어 가족이 함께면 술집은 빠져요.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {purposes.data.items
              .filter((p) => p.code !== selected)
              .map((p) => {
                const on = extra.includes(p.code);
                const full = !on && extra.length >= 2;
                return (
                  <button
                    key={p.code}
                    type="button"
                    aria-pressed={on}
                    disabled={full}
                    onClick={() => setValue("purposes_extra", on ? extra.filter((c) => c !== p.code) : [...extra, p.code], { shouldDirty: true })}
                    className={cn(
                      "inline-flex min-h-11 items-center gap-1.5 rounded-full border px-3.5 text-body-sm font-semibold disabled:opacity-40",
                      on ? "border-tomato bg-tomato text-white" : "border-line bg-soft text-ink hover:border-tomato",
                    )}
                  >
                    <PurposeIcon icon={p.icon} className="size-4" />
                    {p.name}
                  </button>
                );
              })}
          </div>
        </div>
      ) : null}
    </fieldset>
  );
}

// ── 3. 인원 · 예산 ──────────────────────────────────────────
const NIGHTS = [
  { value: 0, label: "당일" },
  { value: 1, label: "1박 2일" },
  { value: 2, label: "2박 3일" },
  { value: 3, label: "3박 4일" },
];

/** 몇 박 며칠: 날마다 코스를 하나씩 짠다. 예산은 여행 전체 금액이고, 숙박비는 들어 있지 않다(공식 요금 데이터가 없다). */
function NightsCard() {
  const { setValue } = useFormContext<PlanValues>();
  const nights = useWatch<PlanValues, "nights">({ name: "nights" });
  return (
    <section aria-labelledby="nights-title" className="border-t-[1.5px] border-dashed border-ink/20 pt-6">
      <h3 id="nights-title" className="text-body-sm font-semibold text-muted-foreground">며칠 일정인가요?</h3>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="일정 길이">
        {NIGHTS.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={nights === o.value}
            onClick={() => setValue("nights", o.value, { shouldDirty: true })}
            className={cn("rounded-2xl border-2 px-3 py-3 text-body font-extrabold", nights === o.value ? "border-tomato bg-tomato-soft text-tomato-deep" : "border-line bg-white text-ink-2 hover:border-tomato")}
          >
            {o.label}
          </button>
        ))}
      </div>
      {nights > 0 ? (
        <p className="mt-3 text-body-sm text-ink-2">
          위 예산을 <b>{nights + 1}일</b>에 나눠 써요(첫날은 만나는 시각부터). 남은 돈은 다음 날로 넘기고, 갔던 곳은 다시 넣지 않아요. 숙박비는 예산에 들어 있지 않아요 — 코스 화면에서 그날 동선 끝 근처의 숙소를 보여 드릴게요.
        </p>
      ) : null}
    </section>
  );
}

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
      <section aria-labelledby="party-label" className="border-t-[1.5px] border-dashed border-ink/20 pt-6">
        <h3 id="party-label" className="mb-3 text-body-sm font-semibold text-muted-foreground">
          몇 명이서?
        </h3>
        <div className="flex items-center gap-4">
          <button type="button" onClick={() => setParty(party - 1)} disabled={party <= 1} aria-label="인원 줄이기" className="grid size-12 place-items-center rounded-[14px] bg-soft transition-colors hover:bg-line disabled:opacity-40">
            <Minus aria-hidden className="size-5" />
          </button>
          <output aria-live="polite" className="tabular min-w-[64px] text-center text-h2 font-extrabold">
            {party}명
          </output>
          <button type="button" onClick={() => setParty(party + 1)} disabled={party >= maxParty} aria-label="인원 늘리기" className="grid size-12 place-items-center rounded-[14px] bg-soft transition-colors hover:bg-line disabled:opacity-40">
            <Plus aria-hidden className="size-5" />
          </button>
          {purpose?.max_party_size && party >= maxParty ? (
            <span className="text-body-sm font-semibold text-muted-foreground">
              {purpose.name}은(는) {maxParty}명까지예요
            </span>
          ) : null}
        </div>
        <FieldError name="party_size" />
      </section>

      <section className="border-t-[1.5px] border-dashed border-ink/20 pt-6">
        <label htmlFor={sliderId} className="mb-4 flex items-baseline justify-between text-body-sm font-semibold text-muted-foreground">
          총 예산
          <b className="money text-price text-ink">{won(budget)}</b>
        </label>
        <input
          id={sliderId}
          type="range"
          className="jj-range"
          style={{ "--fill": `${((Math.min(budget, sliderMax) - sliderMin) / Math.max(1, sliderMax - sliderMin)) * 100}%` } as React.CSSProperties}
          min={sliderMin}
          max={sliderMax}
          step={step}
          value={Math.min(budget, sliderMax)}
          onChange={(e) => setBudget(Number(e.target.value))}
          aria-valuetext={`${won(budget)}, 1인당 ${won(perPerson)}`}
        />
        <div className="tabular mt-2 flex justify-between text-caption font-bold text-muted-foreground">
          <span>{wonCompact(sliderMin)}</span>
          <span>{wonCompact(sliderMax)}</span>
        </div>

        {range ? (
          <div className="mt-5 flex flex-wrap gap-2" role="group" aria-label="빠른 예산 선택">
            {QUICK.map((qk) => {
              const amount = Math.min(sliderMax, roundTo(qk.pick(range) * party, 1000));
              return <BudgetChip key={qk.label} amount={wonCompact(amount)} hint={qk.label} selected={amount === budget} onSelect={() => setBudget(amount)} />;
            })}
          </div>
        ) : null}

        <p className="tabular mt-5 flex items-baseline justify-between rounded-2xl bg-soft px-4 py-3 text-body-sm font-bold text-ink-2" aria-live="polite">
          1인당
          <b className="money text-price-sm text-tomato-deep">{won(perPerson)}</b>
        </p>
        <FieldError name="budget_total" />
      </section>

      {/* 돈을 움직이면 하루가 어떻게 달라지는지 그 자리에서 보여 준다 (docs/19 — 영수증은 서비스의 시그니처) */}
      {/* 데스크톱은 옆의 진행 영수증이 이 예시를 이어서 찍는다 */}
      <details className="group border-t-[1.5px] border-dashed border-ink/20 pt-6 lg:hidden">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-body-sm font-semibold text-ink-2 [&::-webkit-details-marker]:hidden">
          이 예산이면 이런 하루예요
          <span className="tabular rounded-full bg-gold-soft px-2.5 py-1 text-caption text-gold-ink">예시 · 열어 보기</span>
        </summary>
        <Receipt
          className="mx-auto mt-4 max-w-[380px]"
          heading={`${party}명 · 예시`}
          items={sampleCourse(Math.floor(budget / Math.max(1, party)), party)}
          budget={budget}
          footer="업종 평균가로 만든 예시예요. 실제 코스는 고른 동네의 진짜 가게로 짜 드려요."
        />
      </details>

      <NightsCard />

      <MeetTimeCard />

      <JjaniBubble mood={reaction.mood} title={reaction.line} bubbleKey={reaction.mood} live size={84} />
    </div>
  );
}

