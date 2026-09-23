"use client";

import { useId, useMemo, useState, type CSSProperties } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, Check, MapPin, Minus, Plus } from "lucide-react";
import { BudgetChip } from "@/components/brand/BudgetChip";
import { Money } from "@/components/brand/Money";
import { Receipt } from "@/components/brand/Receipt";
import { sampleCourse } from "@/components/brand/sample-course";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useDebounced, usePurposes, useRegions } from "@/lib/api/hooks";
import type { Region } from "@/lib/api/types";
import type { JjaniMood } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";

/**
 * 히어로 = 이름 그대로 세 칸 (2026-09-23 · docs/38): **내가**(조건을 정한다) → **짠**(예산 안에서 맞춘다) → **데이**(하루가 나온다).
 * 설명을 읽기 전에 손으로 만지는 곳이다: 어디서 · 무엇 · 몇 명 → 오늘 쓸 돈 → 그 돈으로 짜인 예시 하루의 영수증.
 * 넓은 화면은 12칸을 4 · 4 · 4 로 나눠 왼쪽에서 오른쪽으로 읽히고, 좁은 화면은 같은 순서로 쌓인다(행동 버튼은 "짠" 칸 끝 — 첫 화면 안).
 *
 * 영수증의 품목은 실제 가게가 아니라 **업종 평균가로 만든 예시**다 — 영수증 머리에 그렇게 적는다.
 */
const MIN = 10000;
const MAX = 120000;
const STEP = 5000;
/** 빠른 선택: 금액 + 어떤 하루인지 한 낱말 (색 없이도 무엇을 골랐는지 읽힌다) */
const PRESETS = [
  { value: 30000, hint: "가볍게" },
  { value: 50000, hint: "무난하게" },
  { value: 100000, hint: "넉넉하게" },
];
/** 목적 코드 → 짧은 이름 (API 이름은 "친구모임" · "혼밥·혼놀"처럼 길다) */
const PURPOSE_SHORT: Record<string, string> = { date: "데이트", friends: "친구", solo: "혼자", family: "가족", travel: "여행" };
const PURPOSE_ORDER = ["date", "friends", "solo", "family", "travel"];
/** 예시 하루는 저녁 6시에 시작한다. 머무는 시간은 업종의 보통값, 사이마다 걸어서 10분 */
const START_MIN = 18 * 60;
const STAY_MIN: Record<string, number> = { 식사: 70, 카페: 50, 산책: 40, 한잔: 60, 놀거리: 60 };
const WALK_MIN = 10;

const hhmm = (min: number) => `${String(Math.floor(min / 60) % 24).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
const won = (n: number) => `${n.toLocaleString("ko-KR")}원`;

/** 한 세션에 한 번 (탭을 닫기 전까지) — 인트로(BrandIntro)가 이 표식으로 틀지 정한다 */
const INTRO_KEY = "jj-brand-intro";
/**
 * 인라인 스크립트: 첫 페인트 전에 브랜드 인트로(내가 → 짠 → 데이)를 틀지 정한다 → 틀지 않을 사람에게는 한 프레임도 흔들리지 않는다.
 * 건너뛰는 경우: 이번 세션에 이미 봤음 · 모션 최소화 · 자동화 브라우저(검증 · E2E · 캡처가 중간 프레임을 찍지 않게) · ?intro=0.
 * ?intro=1 이면 무엇이든 무시하고 튼다(확인용).
 */
export const HERO_INTRO_GATE = `(function(){try{var d=document.documentElement,f=/[?&]intro=1/.test(location.search);if(!f&&(sessionStorage.getItem("${INTRO_KEY}")||navigator.webdriver||matchMedia("(prefers-reduced-motion: reduce)").matches||/[?&]intro=0/.test(location.search)))return;sessionStorage.setItem("${INTRO_KEY}","1");d.setAttribute("data-intro","play")}catch(e){}})();`;

function status(region: string, left: number, preset: string | undefined): { mood: JjaniMood; say: string } {
  if (!region) return { mood: "hi", say: "어디서 만날지만 알려 주세요." };
  if (left < 0) return { mood: "sorry", say: "조금 넘었어요. 한 곳만 바꿔 볼까요?" };
  if (preset === "넉넉하게") return { mood: "wink", say: `넉넉해요. ${won(left)} 남으니 디저트 하나 더?` };
  return { mood: "done", say: `짠! ${won(left)} 남아요.` };
}

export function Hero() {
  const reduced = useReducedMotion();
  const sliderId = useId();
  const placeId = useId();
  const [budget, setBudget] = useState(50000);
  const [party, setParty] = useState(2);
  const [purpose, setPurpose] = useState("date");
  // 어디서: 목록에서 고르면 slug, 그냥 적으면 글자 그대로(위저드가 그 글자로 찾기부터 시작한다)
  const [placeText, setPlaceText] = useState("");
  const [picked, setPicked] = useState<Region | null>(null);
  const [open, setOpen] = useState(false);

  const regions = useRegions();
  const purposes = usePurposes();
  const purposeInfo = purposes.data?.items.find((p) => p.code === purpose);
  const maxParty = Math.min(6, purposeInfo?.max_party_size ?? 6);

  // 많이 찾는 동네: 장소가 많은 동네부터 (위저드의 칩과 같은 기준)
  const hot = useMemo(
    () => [...(regions.data?.items ?? [])].filter((r) => r.level === 3 && r.place_count > 0).sort((a, b) => b.place_count - a.place_count).slice(0, 5),
    [regions.data],
  );
  const query = placeText.trim();
  // 동 · 읍 · 면(성수동 · 연남동 …)은 전체 목록에 없다 → 두 글자부터 서버에 묻는다 (위저드와 같은 방식)
  const asked = useDebounced(query, 200);
  const found = useRegions(asked.length >= 2 && picked?.name !== placeText ? { q: asked } : undefined);
  const matches = useMemo(() => {
    if (!query || picked?.name === placeText) return [];
    const seen = new Set<string>();
    return [...(regions.data?.items ?? []), ...(asked.length >= 2 ? (found.data?.items ?? []) : [])]
      .filter((r) => r.place_count > 0 && r.name.includes(query) && !seen.has(r.slug) && seen.add(r.slug))
      .sort((a, b) => Math.min(b.level, 3) - Math.min(a.level, 3) || b.place_count - a.place_count)
      .slice(0, 5);
  }, [query, placeText, picked, regions.data, asked, found.data]);

  // 증거는 지어내지 않는다: 지금 DB 에 실제로 있는 숫자만 보여 준다
  const proof = useMemo(() => {
    const all = regions.data?.items ?? [];
    const places = all.filter((r) => r.level === 1).reduce((sum, r) => sum + r.place_count, 0);
    return all.length && places ? places : null;
  }, [regions.data]);

  const items = useMemo(() => sampleCourse(Math.floor(budget / party), party), [budget, party]);
  const total = items.reduce((sum, i) => sum + i.price, 0);
  const left = budget - total;
  const preset = PRESETS.find((p) => p.value === budget)?.hint;
  const { mood, say } = status(picked?.slug ?? query, left, preset);
  // "데이": 영수증 줄마다 그 시각을 붙인다 — 영수증이 곧 하루의 시간표
  const dayItems = useMemo(() => {
    let at = START_MIN;
    return items.map((item) => {
      const time = hhmm(at);
      at += (STAY_MIN[item.label] ?? 60) + WALK_MIN;
      return { ...item, label: `${time} ${item.label}` };
    });
  }, [items]);

  const choose = (r: Region) => {
    setPicked(r);
    setPlaceText(r.name);
    setOpen(false);
  };
  const pickPurpose = (code: string) => {
    setPurpose(code);
    const p = purposes.data?.items.find((x) => x.code === code);
    const max = Math.min(6, p?.max_party_size ?? 6);
    // 혼자면 1명, 데이트는 2명까지 — 목적이 받을 수 있는 인원으로 맞춘다
    if (code === "solo") setParty(1);
    else if (party > max) setParty(max);
    else if (party === 1 && p?.default_party_size && p.default_party_size > 1) setParty(p.default_party_size);
  };

  const href = useMemo(() => {
    const q = new URLSearchParams({ budget: String(budget), party: String(party), purpose });
    if (picked && picked.name === placeText) q.set("region", picked.slug);
    else if (query) q.set("q", query);
    return `/plan?${q.toString()}`;
  }, [budget, party, purpose, picked, placeText, query]);

  const zoneLabel = (n: string, word: string, rest: string) => (
    <p className="mb-3 flex items-baseline gap-2 text-body-sm font-semibold text-ink-2">
      <span className="tabular text-caption font-bold text-muted-foreground">{n}</span>
      <b className={cn("font-extrabold text-ink", word === "짠" && "text-tomato-deep")}>{word}</b>
      {rest}
    </p>
  );

  return (
    <section className="hero-home paper-map relative isolate bg-paper pt-[calc(var(--header-h)+20px)] pb-12 lg:pt-[calc(var(--header-h)+32px)] lg:pb-16 short:pt-[calc(var(--header-h)+12px)] short:pb-10">
      <div className="wrap">
        <div className="max-w-[760px]">
          {/* 이름이 곧 문장: 내가 정하면 → 짠! → 하루가 나온다 */}
          <h1 className="hero-title text-display font-extrabold tracking-[-0.03em] text-ink">
            내가 정하면, <span className="hero-jjan">짠!</span> <span className="hero-day">하루가 나와요.</span>
          </h1>
          <p className="mt-3 text-body-lg text-ink-2 short:mt-2">얼마 쓸지만 정하세요. 하루는 짠이가 짜 볼게요.</p>
        </div>

        <div className="mt-7 grid gap-6 lg:grid-cols-12 lg:gap-8 short:mt-5">
          {/* ① 내가 — 어디서 · 무엇 · 몇 명 */}
          <div className="lg:col-span-4">
            {zoneLabel("01", "내가", "정하고")}
            <div className="grid gap-4">
              <div className="relative">
                <label htmlFor={placeId} className="sr-only">
                  어디서 만나요?
                </label>
                <div className="relative">
                <MapPin aria-hidden className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id={placeId}
                  value={placeText}
                  onChange={(e) => {
                    setPlaceText(e.target.value);
                    setOpen(true);
                  }}
                  onFocus={() => setOpen(true)}
                  onBlur={() => window.setTimeout(() => setOpen(false), 120)}
                  placeholder="어디서 만나요? (예: 홍대, 성수)"
                  autoComplete="off"
                  role="combobox"
                  aria-expanded={open && matches.length > 0}
                  aria-controls={`${placeId}-list`}
                  className="h-12 w-full rounded-xl border border-ink/35 bg-white pr-3 pl-10 text-body text-ink outline-none placeholder:text-muted-foreground focus-visible:border-ink"
                />
                {open && matches.length > 0 ? (
                  <ul id={`${placeId}-list`} role="listbox" className="absolute inset-x-0 top-[calc(100%+4px)] z-20 overflow-hidden rounded-xl border border-line bg-white shadow-card">
                    {matches.map((r) => (
                      <li key={r.slug} role="option" aria-selected={picked?.slug === r.slug}>
                        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => choose(r)} className="flex min-h-11 w-full items-center justify-between gap-3 px-3.5 text-left text-body-sm hover:bg-tomato-soft">
                          <span className="font-semibold text-ink">{r.name}</span>
                          <span className="tabular text-caption text-muted-foreground">장소 {r.place_count.toLocaleString("ko-KR")}곳</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
                </div>
                {hot.length > 0 ? (
                  <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none]" role="group" aria-label="많이 찾는 동네">
                    {hot.map((r) => {
                      const on = picked?.slug === r.slug && placeText === r.name;
                      return (
                        <button
                          key={r.slug}
                          type="button"
                          aria-pressed={on}
                          onClick={() => choose(r)}
                          className={cn(
                            "inline-flex min-h-9 shrink-0 items-center gap-1 rounded-full border px-3 text-body-sm transition-colors",
                            on ? "border-tomato bg-tomato font-bold text-white" : "border-ink/20 bg-paper font-medium text-ink-2 hover:border-tomato hover:bg-tomato-soft",
                          )}
                        >
                          {on ? <Check aria-hidden strokeWidth={3} className="size-3.5" /> : null}
                          {r.name}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>

              {/* 무엇: 하나만 고른다 (segmented) */}
              <div role="radiogroup" aria-label="어떤 약속" className="grid grid-cols-5 rounded-xl border border-ink/20 bg-paper p-1">
                {PURPOSE_ORDER.map((code) => {
                  const on = purpose === code;
                  return (
                    <button
                      key={code}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      onClick={() => pickPurpose(code)}
                      className={cn("min-h-10 rounded-lg text-body-sm transition-colors", on ? "bg-tomato font-extrabold text-white" : "font-medium text-ink-2 hover:bg-tomato-soft")}
                    >
                      {PURPOSE_SHORT[code]}
                    </button>
                  );
                })}
              </div>

              <div className="flex items-center justify-between gap-3">
                <span className="text-body-sm font-semibold text-ink-2">몇 명이서</span>
                <div className="flex items-center gap-1.5" role="group" aria-label="인원">
                  <button type="button" onClick={() => setParty((p) => Math.max(1, p - 1))} disabled={party <= 1} aria-label="인원 줄이기" className="grid size-11 place-items-center rounded-full border border-ink/25 bg-paper hover:border-ink disabled:opacity-35">
                    <Minus aria-hidden className="size-4" />
                  </button>
                  <output aria-live="polite" className="tabular min-w-12 text-center text-body-lg font-bold">
                    {party}명
                  </output>
                  <button type="button" onClick={() => setParty((p) => Math.min(maxParty, p + 1))} disabled={party >= maxParty} aria-label="인원 늘리기" className="grid size-11 place-items-center rounded-full border border-ink/25 bg-paper hover:border-ink disabled:opacity-35">
                    <Plus aria-hidden className="size-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* ② 짠 — 오늘 쓸 돈. 행동 버튼은 이 칸 끝에(모바일에서도 첫 화면 안) */}
          <div className="lg:col-span-4 lg:border-x lg:border-dashed lg:border-ink/15 lg:px-8">
            {zoneLabel("02", "짠", "예산 안에서")}
            <label htmlFor={sliderId} className="text-body-sm font-semibold text-ink-2">
              오늘 쓸 돈
            </label>
            <Money value={budget} duration={500} className="money block text-price-lg text-ink" />
            <input
              id={sliderId}
              type="range"
              className="jj-range mt-3"
              style={{ "--fill": `${((budget - MIN) / (MAX - MIN)) * 100}%` } as CSSProperties}
              min={MIN}
              max={MAX}
              step={STEP}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
              aria-valuetext={`${won(budget)}, ${party}명`}
            />
            <div className="mt-3 grid grid-cols-3 gap-2" role="group" aria-label="자주 쓰는 예산">
              {PRESETS.map((p) => (
                <BudgetChip key={p.value} amount={`${p.value / 10000}만 원`} hint={p.hint} selected={budget === p.value} onSelect={() => setBudget(p.value)} className="justify-center" />
              ))}
            </div>

            <div className="mt-4 flex items-center gap-2.5">
              <Jjani mood={mood} className="h-auto w-10 shrink-0" />
              <AnimatePresence mode="wait" initial={false}>
                <motion.p
                  key={say}
                  aria-live="polite"
                  initial={reduced ? false : { opacity: 0, y: 3 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduced ? undefined : { opacity: 0, y: -3 }}
                  transition={{ duration: 0.16 }}
                  className="tabular rounded-lg rounded-bl-sm bg-white px-3 py-1.5 text-body-sm font-semibold text-ink shadow-soft"
                >
                  {say}
                </motion.p>
              </AnimatePresence>
            </div>

            <Button asChild variant="brand" size="xl" className="group mt-4 w-full">
              <Link href={href} onClick={() => track("plan_started", { entry: "landing_hero" })}>
                이 예산으로 하루 짜기 <ArrowRight aria-hidden className="transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            {/* 증거는 지어내지 않는다: 지금 DB 에 실제로 있는 숫자만 */}
            {proof ? (
              <p className="tabular mt-2 text-center text-caption font-semibold text-muted-foreground">
                전국 실제 장소 {proof.toLocaleString("ko-KR")}곳 · 가입 없이 바로
              </p>
            ) : null}
          </div>

          {/* ③ 데이 — 그 돈으로 짜인 하루: 영수증 줄마다 시각이 붙은 시간표 */}
          <div className="lg:col-span-4">
            {zoneLabel("03", "데이", "하루가 나와요")}
            <div className="relative">
              <Receipt heading={`예시 · ${party}명 · ${PURPOSE_SHORT[purpose] ?? ""} · 업종 평균가`} items={dayItems} budget={budget} className="drop-shadow-[0_14px_24px_rgba(40,32,20,.12)]" />
              {/* 상태 도장: 색만이 아니라 글자로 */}
              <span aria-hidden className={cn("hero-stamp", left < 0 && "is-over")}>{left < 0 ? "초과" : "예산 안"}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
