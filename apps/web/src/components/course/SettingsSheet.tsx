"use client";

import { useState, type ReactNode } from "react";
import { Check, Minus, Plus, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrandEditor } from "@/components/plan/ErrandEditor";
import { DURATION_PRESETS, START_PRESETS } from "@/components/plan/meet-time";
import { usePurposes, type Errand } from "@/lib/api/hooks";
import { dateLabel, won } from "@/lib/format";
import { cn } from "@/lib/utils";
import { COURSE_OPTIONS } from "./AddOptions";
import { BottomSheet } from "./BottomSheet";

/** 결과 화면에서 바꿀 수 있는 설정. 지역 · 출발점 · 취향은 그대로 두고 이것만 바꿔 다시 짠다 */
export interface CourseSettings {
  /** "+09:00" ISO */
  start_at: string;
  /** null = 짠이에게 맡기기 */
  duration_min: number | null;
  budget_total: number;
  party_size: number;
  purpose: string;
  /** "" = 목적의 기본 장면 */
  scene: string;
  /** 가는 김에 들를 곳 (docs/51 B1). null = 없음 */
  errand: Errand | null;
  /** 위저드에서 옮겨 온 옵션 (docs/59 #2): 술 한잔 · 영화 · 야구 (요청의 extras) */
  extras: string[];
  /** 그날의 사정: 비 오는 날 (요청의 conditions) */
  conditions: string[];
}

interface SettingsSheetProps {
  open: boolean;
  onClose: () => void;
  initial: CourseSettings;
  /** 대학교 중심 코스면 캠퍼스용 목적 목록 */
  university?: boolean;
  /** 여행 일정의 하루: 날짜는 일정이 정한다 — 시각만 바꾼다 */
  lockDay?: boolean;
  /** 고정한 곳의 수 (다시 짜도 남는다) */
  pinned: number;
  /** 들를 곳이 곧 하루의 중심(여기 근처에서 놀래요)이면: 빼거나 순서를 바꾸지 않는다 — 시간만 */
  errandIsCentre?: boolean;
  onApply: (next: CourseSettings) => void;
}

const HOUR = 3_600_000;
const BUDGET_MIN = 5_000;
const BUDGET_MAX = 5_000_000;

/** ISO → 서울 기준 "YYYY-MM-DD" · "HH:mm" (기기 시간대와 상관없이) */
function kstParts(iso: string | number): { day: string; time: string } {
  const d = new Date(new Date(iso).getTime() + 9 * HOUR).toISOString();
  return { day: d.slice(0, 10), time: d.slice(11, 16) };
}
const toIso = (day: string, time: string) => `${day}T${time}:00+09:00`;

function Chip({ on, onClick, children, label }: { on: boolean; onClick: () => void; children: ReactNode; label?: string }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "inline-flex min-h-11 items-center gap-1 rounded-full border px-3.5 text-body-sm transition-colors",
        on ? "border-tomato bg-tomato font-bold text-white" : "border-ink/20 bg-white font-semibold text-ink-2 hover:border-tomato hover:bg-tomato-soft",
      )}
    >
      {on ? <Check aria-hidden strokeWidth={3} className="size-4" /> : null}
      {children}
    </button>
  );
}

function Section({ title, children, note }: { title: string; children: ReactNode; note?: ReactNode }) {
  return (
    <section className="grid gap-2 border-t border-dashed border-ink/20 pt-4 first:border-t-0 first:pt-0">
      <h3 className="text-body-sm font-semibold text-ink-2">{title}</h3>
      {children}
      {note}
    </section>
  );
}

function Stepper({ value, onChange, min, max, step, label, format }: { value: number; onChange: (v: number) => void; min: number; max: number; step: number; label: string; format: (v: number) => string }) {
  const btn = "grid size-11 shrink-0 place-items-center rounded-[14px] bg-soft transition-colors hover:bg-line disabled:opacity-40";
  return (
    <div className="flex items-center gap-3">
      <button type="button" className={btn} aria-label={`${label} 줄이기`} disabled={value <= min} onClick={() => onChange(Math.max(min, value - step))}>
        <Minus aria-hidden className="size-5" />
      </button>
      <output aria-live="polite" className="tabular min-w-[96px] text-center text-h3 font-extrabold text-ink">
        {format(value)}
      </output>
      <button type="button" className={btn} aria-label={`${label} 늘리기`} disabled={value >= max} onClick={() => onChange(Math.min(max, value + step))}>
        <Plus aria-hidden className="size-5" />
      </button>
    </div>
  );
}

/**
 * 설정 바꾸기: 코스가 나온 뒤에 시간 · 예산 · 인원 · 누구와 · 목적 · 가는 김에 들를 곳을 바꿔서 그 자리에서 다시 짠다.
 * 지역과 출발점, 고른 취향은 그대로다. 지역부터 바꾸려면 위저드로 간다(다시 짜기 시트).
 */
export function SettingsSheet({ open, onClose, initial, university, lockDay, pinned, errandIsCentre, onApply }: SettingsSheetProps) {
  const purposes = usePurposes(university ? "university" : undefined);
  const now = Date.now();
  const today = kstParts(now).day;
  const tomorrow = kstParts(now + 24 * HOUR).day;
  const first = kstParts(initial.start_at);

  // 지난 날짜로 짠 코스를 열었으면 오늘부터 고른다
  const [day, setDay] = useState(first.day < today && !lockDay ? today : first.day);
  const [time, setTime] = useState(first.time);
  const [duration, setDuration] = useState<number | null>(initial.duration_min);
  const [budget, setBudget] = useState(initial.budget_total);
  const [party, setParty] = useState(initial.party_size);
  const [purposeCode, setPurposeCode] = useState(initial.purpose);
  const [scene, setScene] = useState(initial.scene);
  const [errand, setErrand] = useState<Errand | null>(initial.errand);
  const [extras, setExtras] = useState<string[]>(initial.extras);
  const [conditions, setConditions] = useState<string[]>(initial.conditions);

  const purpose = purposes.data?.items.find((p) => p.code === purposeCode);
  const maxParty = purpose?.max_party_size ?? 20;
  const scenes = purpose?.scenes ?? [];
  const currentScene = scene || purpose?.default_scene || "";

  const days = [...new Set([today, tomorrow, ...(first.day >= today ? [first.day] : [])])].sort();
  const dayName = (d: string) => (d === today ? "오늘" : d === tomorrow ? "내일" : dateLabel(toIso(d, "12:00")));

  const start = toIso(day, time);
  const past = new Date(start).getTime() < now - 5 * 60_000;
  const next: CourseSettings = { start_at: start, duration_min: duration, budget_total: budget, party_size: Math.min(party, maxParty), purpose: purposeCode, scene, errand, extras, conditions };
  const changed =
    kstParts(next.start_at).day !== first.day ||
    kstParts(next.start_at).time !== first.time ||
    next.duration_min !== initial.duration_min ||
    next.budget_total !== initial.budget_total ||
    next.party_size !== initial.party_size ||
    next.purpose !== initial.purpose ||
    next.scene !== initial.scene ||
    JSON.stringify(next.errand) !== JSON.stringify(initial.errand) ||
    [...next.extras].sort().join() !== [...initial.extras].sort().join() ||
    [...next.conditions].sort().join() !== [...initial.conditions].sort().join();

  const budgetStep = budget >= 200_000 ? 10_000 : 5_000;
  const perPerson = Math.round(budget / Math.max(1, next.party_size) / 100) * 100;

  return (
    <BottomSheet
      open={open}
      onClose={onClose}
      title="설정 바꾸기"
      description={pinned > 0 ? `동네와 취향, 확정한 ${pinned}곳은 그대로 두고 다시 짜요.` : "동네와 취향은 그대로, 바꾼 것만 맞춰 다시 짜요."}
      footer={
        <Button type="button" variant="brand" size="xl" className="w-full" disabled={!changed || past} onClick={() => onApply(next)}>
          <RotateCw aria-hidden /> {past ? "이미 지난 시간이에요" : changed ? "이 설정으로 다시 짜기" : "바꾸고 싶은 걸 골라 주세요"}
        </Button>
      }
    >
      <div className="grid gap-4">
        <Section
          title="언제 만나요?"
          note={past ? <p role="alert" className="text-body-sm font-semibold text-pink-deep">이미 지난 시간이에요. 시각을 다시 골라 주세요.</p> : null}
        >
          {lockDay ? null : (
            <div className="flex flex-wrap gap-2" role="group" aria-label="날짜">
              {days.map((d) => (
                <Chip key={d} on={d === day} onClick={() => setDay(d)}>
                  {dayName(d)}
                </Chip>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="출발 시각">
            {START_PRESETS.map((p) => (
              <Chip key={p.time} on={time === p.time} onClick={() => setTime(p.time)} label={`${p.label} ${p.time}`}>
                {p.label} <span className="tabular font-normal opacity-80">{p.time}</span>
              </Chip>
            ))}
            <label className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-ink/20 bg-white pr-2 pl-3.5 text-body-sm font-semibold text-ink-2">
              직접
              <input type="time" value={time} step={600} onChange={(e) => e.target.value && setTime(e.target.value)} className="tabular min-h-9 rounded-md bg-transparent text-ink outline-none" aria-label="출발 시각 직접 고르기" />
            </label>
          </div>
        </Section>

        <Section title="얼마나 함께 있어요?">
          <div className="flex flex-wrap gap-2" role="group" aria-label="함께 있는 시간">
            {DURATION_PRESETS.map((p) => (
              <Chip key={p.minutes} on={duration === p.minutes} onClick={() => setDuration(p.minutes)}>
                {p.label}
              </Chip>
            ))}
            <Chip on={duration === null} onClick={() => setDuration(null)}>
              짠이에게 맡기기
            </Chip>
          </div>
        </Section>

        <Section title="예산은요?" note={<p className="tabular text-caption text-muted-foreground">한 사람에 약 {won(perPerson)}</p>}>
          <Stepper value={budget} onChange={setBudget} min={BUDGET_MIN} max={BUDGET_MAX} step={budgetStep} label="예산" format={won} />
        </Section>

        <Section title="몇 명이서?" note={purpose?.max_party_size && party >= maxParty ? <p className="text-caption text-muted-foreground">{purpose.name}은(는) {maxParty}명까지예요</p> : null}>
          <Stepper value={Math.min(party, maxParty)} onChange={setParty} min={1} max={maxParty} step={1} label="인원" format={(v) => `${v}명`} />
        </Section>

        <Section title="어떤 약속이에요?">
          {purposes.isPending ? (
            <p className="skeleton-shimmer h-11 rounded-full" aria-label="목적을 불러오는 중" />
          ) : (
            <div className="flex flex-wrap gap-2" role="group" aria-label="목적">
              {(purposes.data?.items ?? []).map((p) => (
                <Chip
                  key={p.code}
                  on={p.code === purposeCode}
                  onClick={() => {
                    if (p.code === purposeCode) return;
                    setPurposeCode(p.code);
                    setScene(""); // 누구와는 목적마다 다르다
                  }}
                >
                  {p.name}
                </Chip>
              ))}
            </div>
          )}
        </Section>

        <Section title="가는 김에 들를 곳">
          <ErrandEditor value={errand} onChange={setErrand} isCentre={errandIsCentre && errand !== null} />
        </Section>

        <Section title="이것도 넣을까요?">
          <div className="flex flex-wrap gap-2" role="group" aria-label="넣을 것">
            {COURSE_OPTIONS.map((o) => {
              const list = o.kind === "extra" ? extras : conditions;
              const set = o.kind === "extra" ? setExtras : setConditions;
              const on = list.includes(o.key);
              return (
                <Chip key={o.key} on={on} onClick={() => set(on ? list.filter((k) => k !== o.key) : [...list, o.key])}>
                  {o.label}
                </Chip>
              );
            })}
          </div>
        </Section>

        {purpose && scenes.length > 0 ? (
          <Section title={purpose.scene_question ?? "누구와 가나요?"}>
            <div className="flex flex-wrap gap-2" role="group" aria-label="누구와">
              {scenes.map((s) => (
                <Chip key={s.code} on={s.code === currentScene} onClick={() => setScene(s.code === currentScene && !purpose.default_scene ? "" : s.code)}>
                  {s.label}
                </Chip>
              ))}
            </div>
          </Section>
        ) : null}
      </div>
    </BottomSheet>
  );
}
