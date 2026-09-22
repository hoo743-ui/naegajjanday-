"use client";

import { useId, useMemo } from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { CalendarDays, Clock, Hourglass } from "lucide-react";
import { cn } from "@/lib/utils";
import { DURATION_PRESETS, START_PRESETS, dayOptions, describeWindow, isPast, isToday, toDayString } from "./meet-time";
import type { PlanValues } from "./schema";

const chip = (on: boolean, disabled = false) =>
  cn(
    "tabular rounded-full px-4 py-2.5 text-body-sm font-extrabold transition-colors",
    on ? "bg-ink text-white" : "bg-soft text-ink-2 hover:bg-line",
    disabled && "cursor-not-allowed opacity-40 hover:bg-soft",
  );

const rowLabel = "mb-2 flex items-center gap-1.5 text-caption font-semibold text-ink-2";

/** 만나는 날 · 시작 시각 · 얼마나 — 세 줄짜리 카드. 고른 값은 start_at / duration_min 으로 코스 엔진에 그대로 들어간다. */
export function MeetTimeCard() {
  const { setValue, formState } = useFormContext<PlanValues>();
  const day = useWatch<PlanValues, "meet_day">({ name: "meet_day" });
  const startTime = useWatch<PlanValues, "start_time">({ name: "start_time" });
  const duration = useWatch<PlanValues, "duration_min">({ name: "duration_min" });
  const dateId = useId();
  const timeId = useId();

  // 렌더마다 바뀌면 칩이 흔들린다 → 마운트 시각 기준. 제출 시에는 그때의 now 로 다시 계산한다.
  const now = useMemo(() => new Date(), []);
  const days = useMemo(() => dayOptions(now), [now]);
  const today = isToday({ meet_day: day }, now);
  const opts = { shouldValidate: true, shouldDirty: true } as const;

  const pickDay = (value: string) => {
    setValue("meet_day", value === toDayString(now) ? "" : value, opts);
    // 다른 날에는 "지금 바로"가 없다 → 저녁 약속을 기본으로
    if (value && value !== toDayString(now) && !startTime) setValue("start_time", "18:00", opts);
  };

  const error = formState.errors.start_time?.message ?? formState.errors.meet_day?.message;

  return (
    <section aria-labelledby="meet-label" className="border-t-[1.5px] border-dashed border-ink/20 pt-6">
      <h3 id="meet-label" className="mb-4 text-body-sm font-semibold text-muted-foreground">
        언제 만나요?
      </h3>

      <div className="grid gap-5">
        <div role="group" aria-label="만나는 날">
          <p className={rowLabel}>
            <CalendarDays aria-hidden className="size-3.5" /> 날짜
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {days.map((d) => {
              const on = d.value === day || (d.value === "" && today);
              return (
                <button key={d.label} type="button" aria-pressed={on} onClick={() => pickDay(d.value)} className={chip(on)}>
                  {d.label}
                </button>
              );
            })}
            <label htmlFor={dateId} className="sr-only">
              날짜 직접 고르기
            </label>
            <input
              id={dateId}
              type="date"
              min={toDayString(now)}
              value={day || toDayString(now)}
              onChange={(e) => pickDay(e.target.value)}
              className={cn("tabular h-11 rounded-xl border-2 bg-white px-3 text-body-sm font-extrabold", day && !days.some((d) => d.value === day) ? "border-blue-deep" : "border-input")}
            />
          </div>
        </div>

        <div role="group" aria-label="만나는 시각">
          <p className={rowLabel}>
            <Clock aria-hidden className="size-3.5" /> 시작
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {today ? (
              <button type="button" aria-pressed={startTime === ""} onClick={() => setValue("start_time", "", opts)} className={chip(startTime === "")}>
                지금 바로
              </button>
            ) : null}
            {START_PRESETS.map((p) => {
              const gone = isPast({ meet_day: day, start_time: p.time }, now);
              return (
                <button key={p.time} type="button" disabled={gone} aria-pressed={startTime === p.time} onClick={() => setValue("start_time", p.time, opts)} className={chip(startTime === p.time, gone)}>
                  {p.label} {p.time}
                </button>
              );
            })}
            <label htmlFor={timeId} className="sr-only">
              시각 직접 입력
            </label>
            <input
              id={timeId}
              type="time"
              step={600}
              value={startTime}
              onChange={(e) => setValue("start_time", e.target.value, opts)}
              className={cn("tabular h-11 rounded-xl border-2 bg-white px-3 text-body font-extrabold", startTime && !START_PRESETS.some((p) => p.time === startTime) ? "border-blue-deep" : "border-input")}
            />
          </div>
        </div>

        <div role="group" aria-label="함께 보내는 시간">
          <p className={rowLabel}>
            <Hourglass aria-hidden className="size-3.5" /> 얼마나
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" aria-pressed={duration === null} onClick={() => setValue("duration_min", null, opts)} className={chip(duration === null)}>
              짠이에게 맡기기
            </button>
            {DURATION_PRESETS.map((p) => (
              <button key={p.minutes} type="button" aria-pressed={duration === p.minutes} onClick={() => setValue("duration_min", p.minutes, opts)} className={chip(duration === p.minutes)}>
                {p.label} <span className="font-bold opacity-60">· {p.hint}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <p className="tabular mt-5 rounded-2xl bg-soft px-4 py-3 text-body-sm font-bold text-ink-2" aria-live="polite">
        {describeWindow({ meet_day: day, start_time: startTime, duration_min: duration }, now)}
      </p>
      {error ? (
        <p role="alert" className="mt-3 text-body-sm font-semibold text-danger">
          {error}
        </p>
      ) : null}
    </section>
  );
}
