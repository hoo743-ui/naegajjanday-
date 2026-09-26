"use client";

import { useId, useState, type FormEvent } from "react";
import { Check, Clapperboard, CloudRain, Minus, Plus, ShoppingBag, Sparkles, Trophy, Wine, type LucideIcon } from "lucide-react";
import { track } from "@/lib/analytics";
import { useParseOptions, type ParsedOptions, type Spot } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

/** 위저드에서 뺀 옵션 (docs/59 #2): 코스를 본 뒤에 "이것도" 하고 넣는다 */
export const COURSE_OPTIONS: { key: string; kind: "extra" | "condition"; label: string; icon: LucideIcon }[] = [
  { key: "BAR", kind: "extra", label: "술 한잔", icon: Wine },
  { key: "MOVIE", kind: "extra", label: "영화 한 편", icon: Clapperboard },
  { key: "BASEBALL", kind: "extra", label: "야구", icon: Trophy },
  { key: "rain", kind: "condition", label: "비 오는 날", icon: CloudRain },
];

/** 옵션을 넣고 뺀 뒤의 요청 조각. errand: undefined = 그대로, 값 = 이곳을 먼저/끝나고 들르기 */
export interface OptionChange {
  extras: string[];
  conditions: string[];
  errand?: { name: string; lat: number; lng: number; place_id: string | null; minutes: number; when: "before" | "after" };
  /** 분석용: 무엇을 켜고 껐는지 */
  toggled: { option: string; on: boolean }[];
  via: "chip" | "text";
}

interface AddOptionsProps {
  courseId: string;
  extras: string[];
  conditions: string[];
  hasErrand: boolean;
  busy?: boolean;
  onChange: (change: OptionChange) => void;
  /** 꼭 들를 곳: 검색 칸이 있는 설정 바꾸기 시트로 */
  onErrand: () => void;
}

const chip = "inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-full border-[1.5px] px-3.5 text-body-sm font-semibold transition-colors disabled:opacity-50";

/**
 * "이것도 넣어 볼까요?" (docs/59 #2 · 창업자 2026-09-26 "선택지가 늘어도 어지럽지 않게"):
 * 위저드는 어디 · 누구와 · 얼마 · 언제만 묻고, 술 한잔 · 영화 · 야구 · 비 · 꼭 들를 곳은 코스를 본 뒤에 여기서.
 * 칩 하나 = 그 옵션을 넣어(이미 있으면 빼서) 다시 짜기. 아래 한 줄은 말로 받는다 — 읽은 것을 먼저 보여 주고, 누르면 다시 짠다.
 */
export function AddOptions({ courseId, extras, conditions, hasErrand, busy, onChange, onErrand }: AddOptionsProps) {
  const parse = useParseOptions();
  const [text, setText] = useState("");
  const [read, setRead] = useState<ParsedOptions | null>(null);
  const inputId = useId();

  const isOn = (key: string) => extras.includes(key) || conditions.includes(key);

  const toggle = (key: string) => {
    const option = COURSE_OPTIONS.find((o) => o.key === key);
    if (!option) return;
    const on = !isOn(key);
    const list = option.kind === "extra" ? extras : conditions;
    const next = on ? [...list, key] : list.filter((k) => k !== key);
    onChange({
      extras: option.kind === "extra" ? next : extras,
      conditions: option.kind === "condition" ? next : conditions,
      toggled: [{ option: key, on }],
      via: "chip",
    });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const line = text.trim();
    if (!line || parse.isPending) return;
    parse.mutate(line, {
      onSuccess: (got) => {
        setRead(got);
        track("course_option_text_parsed", {
          course_id: courseId,
          length: line.length,
          matched: got.matched.length,
          options: got.matched.map((m) => (m.declined ? `-${m.key}` : m.key)).join(","),
        });
      },
    });
  };

  const spot: Spot | null = read?.errand?.spots[0] ?? null;
  // 이미 그렇게 짠 것은 "새로 넣을 것"이 아니다
  const adds = read ? [...read.extras, ...read.conditions].filter((k) => !isOn(k)) : [];
  const drops = read ? read.declined.filter((k) => isOn(k)) : [];
  const changes = adds.length + drops.length + (spot ? 1 : 0);

  const apply = () => {
    if (!read) return;
    const kindOf = (k: string) => COURSE_OPTIONS.find((o) => o.key === k)?.kind ?? "extra";
    const nextExtras = [...extras.filter((k) => !drops.includes(k)), ...adds.filter((k) => kindOf(k) === "extra")];
    const nextConditions = [...conditions.filter((k) => !drops.includes(k)), ...adds.filter((k) => kindOf(k) === "condition")];
    onChange({
      extras: nextExtras,
      conditions: nextConditions,
      ...(spot && read.errand ? { errand: { name: spot.name, lat: spot.lat, lng: spot.lng, place_id: spot.place_id, minutes: 30, when: read.errand.when } } : {}),
      toggled: [...adds.map((option) => ({ option, on: true })), ...drops.map((option) => ({ option, on: false })), ...(spot ? [{ option: "ERRAND", on: true }] : [])],
      via: "text",
    });
    setRead(null);
    setText("");
  };

  const labelOf = (key: string) => COURSE_OPTIONS.find((o) => o.key === key)?.label ?? key;

  return (
    <section aria-labelledby="add-options" className="grid gap-3 border-t border-dashed border-ink/20 pt-4">
      <div>
        <h2 id="add-options" className="text-body font-bold text-ink">
          이것도 넣어 볼까요?
        </h2>
        <p className="text-body-sm text-muted-foreground">누르면 그걸 넣어서 다시 짜요. 이미 넣은 건 한 번 더 누르면 빠져요.</p>
      </div>
      {/* 좁은 화면: 한 줄로 흐른다(가로로 밀어 보기) */}
      <div role="group" aria-label="넣을 것" className="flex gap-2 max-sm:-mx-4 max-sm:overflow-x-auto max-sm:px-4 max-sm:[scrollbar-width:none] sm:flex-wrap">
        {COURSE_OPTIONS.map((o) => {
          const on = isOn(o.key);
          return (
            <button key={o.key} type="button" aria-pressed={on} disabled={busy} onClick={() => toggle(o.key)} className={cn(chip, on ? "border-tomato bg-tomato-soft text-tomato-deep" : "border-line bg-white text-ink hover:border-ink-2")}>
              {on ? <Check aria-hidden className="size-4" /> : <o.icon aria-hidden className="size-4 text-tomato-deep" />}
              {o.label}
            </button>
          );
        })}
        <button type="button" aria-pressed={hasErrand} disabled={busy} onClick={onErrand} className={cn(chip, hasErrand ? "border-tomato bg-tomato-soft text-tomato-deep" : "border-line bg-white text-ink hover:border-ink-2")}>
          {hasErrand ? <Check aria-hidden className="size-4" /> : <ShoppingBag aria-hidden className="size-4 text-tomato-deep" />}
          꼭 들를 곳
        </button>
      </div>

      <form onSubmit={submit} className="flex min-w-0 items-center gap-2">
        <label htmlFor={inputId} className="sr-only">
          한 줄로 말하기
        </label>
        <input
          id={inputId}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (read) setRead(null);
          }}
          maxLength={120}
          autoComplete="off"
          enterKeyHint="send"
          placeholder="한 줄로 말해도 돼요 · 애플스토어 들렀다가 영화"
          className="h-11 min-w-0 flex-1 rounded-xl border border-input bg-white px-3.5 text-body-sm font-semibold placeholder:font-medium placeholder:text-muted-foreground focus-visible:border-tomato"
        />
        <button type="submit" disabled={!text.trim() || parse.isPending || busy} className="inline-flex min-h-11 shrink-0 items-center gap-1 rounded-xl bg-ink px-3.5 text-body-sm font-bold text-white disabled:opacity-40">
          <Sparkles aria-hidden className="size-4" />
          {parse.isPending ? "읽는 중" : "읽기"}
        </button>
      </form>

      <div aria-live="polite">
        {parse.isError ? <p className="text-body-sm font-semibold text-pink-deep">지금은 말을 읽지 못했어요. 위의 칩으로 골라 주세요.</p> : null}
        {read ? (
          changes === 0 ? (
            <p className="border-l-2 border-line pl-3 text-body-sm text-ink-2">
              {read.errand && !spot
                ? `‘${read.errand.query}’은(는) 찾지 못했어요. ‘꼭 들를 곳’에서 이름으로 찾아 주세요.`
                : read.matched.length > 0
                  ? "이미 그렇게 짠 코스예요."
                  : "아직 이 말은 못 알아들었어요. 술 한잔 · 영화 · 야구 · 비 · 들를 곳을 말해 주거나 위의 칩으로 골라 주세요."}
            </p>
          ) : (
            <div className="grid gap-2 rounded-xl border-[1.5px] border-tomato bg-tomato-soft p-3.5">
              <p className="text-body-sm font-bold text-ink">이렇게 읽었어요</p>
              <ul className="grid gap-1 text-body-sm font-semibold text-ink-2">
                {spot && read.errand ? (
                  <li className="flex items-center gap-2">
                    <ShoppingBag aria-hidden className="size-4 shrink-0 text-tomato-deep" />
                    <span className="min-w-0">
                      {read.errand.when === "after" ? "끝나고" : "먼저"} {spot.name} 들르기
                      {spot.address ? <span className="block truncate text-caption font-medium text-muted-foreground">{spot.address}</span> : null}
                    </span>
                  </li>
                ) : null}
                {adds.map((k) => (
                  <li key={k} className="flex items-center gap-2">
                    <Plus aria-hidden className="size-4 shrink-0 text-tomato-deep" />
                    {labelOf(k)} 넣기
                  </li>
                ))}
                {drops.map((k) => (
                  <li key={k} className="flex items-center gap-2">
                    <Minus aria-hidden className="size-4 shrink-0 text-pink-deep" />
                    {labelOf(k)} 빼기
                  </li>
                ))}
              </ul>
              <button type="button" onClick={apply} disabled={busy} className="inline-flex min-h-11 w-fit items-center rounded-xl bg-tomato px-4 text-body-sm font-bold text-white disabled:opacity-50">
                이대로 다시 짜기
              </button>
            </div>
          )
        ) : null}
      </div>
    </section>
  );
}
