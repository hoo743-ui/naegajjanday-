"use client";

import { useEffect, useId, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, Minus, Plus } from "lucide-react";
import { DayRoute } from "@/components/brand/DayRoute";
import { Money } from "@/components/brand/Money";
import { sampleCourse } from "@/components/brand/sample-course";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useRegions } from "@/lib/api/hooks";
import type { JjaniMood } from "@/lib/mascot-copy";

/**
 * 히어로 = 서비스를 한 번 써 보는 장면 (docs/31 §4). 광고 문구 + 떠 있는 카드가 아니라, 위에서 아래로
 * **오늘 쓸 돈 → 오늘의 하루 → 영수증**이 이어진다. 돈을 움직이면 하루가 다시 짜이고 영수증의 남은 돈이 바뀐다.
 * 왼쪽의 작은 이름표(오늘 쓸 돈 · 오늘의 하루 · 영수증)가 세 장면을 한 장의 서식처럼 묶는다.
 *
 * 하루의 품목은 실제 가게가 아니라 **업종 평균가로 만든 예시**다 — 그렇게 적어 둔다.
 */
const MIN = 10000;
const MAX = 120000;
const STEP = 5000;
/** 예시 하루는 저녁 6시에 시작한다. 머무는 시간은 업종의 보통값, 사이마다 걸어서 10분 */
const START_MIN = 18 * 60;
const STAY_MIN: Record<string, number> = { 식사: 70, 카페: 50, 산책: 40, 한잔: 60, 놀거리: 60 };
const WALK_MIN = 10;

function reaction(left: number, budget: number): { mood: JjaniMood; say: string } {
  const ratio = left / budget;
  if (ratio <= 0.05) return { mood: "cheers", say: "예산을 꽉 채웠어요. 한 푼도 안 넘겨요" };
  if (ratio <= 0.2) return { mood: "done", say: `여기서 ${left.toLocaleString("ko-KR")}원 남아요` };
  return { mood: "wink", say: `${left.toLocaleString("ko-KR")}원 남으니 디저트 하나 더?` };
}

/** 한 세션에 한 번 (탭을 닫기 전까지) */
const INTRO_KEY = "jj-hero-intro";
/**
 * 인라인 스크립트: 첫 페인트 전에 랜딩 시퀀스(docs/32)를 틀지 정한다 → 틀지 않을 사람에게는 한 프레임도 흔들리지 않는다.
 * 건너뛰는 경우: 이번 세션에 이미 봤음 · 모션 최소화 · 자동화 브라우저(검증 · E2E · 캡처가 중간 프레임을 찍지 않게) · ?intro=0
 */
export const HERO_INTRO_GATE = `(function(){try{var d=document.documentElement;if(sessionStorage.getItem("${INTRO_KEY}")||navigator.webdriver||matchMedia("(prefers-reduced-motion: reduce)").matches||/[?&]intro=0/.test(location.search))return;sessionStorage.setItem("${INTRO_KEY}","1");d.setAttribute("data-intro","play")}catch(e){}})();`;
/** 예산이 세어지기 시작하는 때(ms) — globals.css 의 [data-beat="money"] 등장과 같은 시각 */
const COUNT_AT_MS = 1100;

const hhmm = (min: number) => `${String(Math.floor(min / 60) % 24).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

/** 서식의 한 칸: 왼쪽에 작은 이름표, 오른쪽에 내용. 칸 사이는 점선 한 줄 — 영수증 칸만 뜯는 자리(구멍 줄) */
function Field({ name, children, tear = false, beat }: { name: string; children: React.ReactNode; tear?: boolean; beat?: string }) {
  return (
    <div data-beat={beat} className="relative grid gap-4 py-7 lg:grid-cols-[152px_minmax(0,1fr)] lg:gap-10 lg:py-9">
      {tear ? <hr aria-hidden className="tear-line absolute inset-x-0 top-0 -translate-y-1/2" /> : <span aria-hidden className="absolute inset-x-0 top-0 border-t-[1.5px] border-dashed border-ink/20" />}
      <p className="text-body-sm font-bold text-muted-foreground lg:pt-1">{name}</p>
      <div>{children}</div>
    </div>
  );
}

export function Hero() {
  const reduced = useReducedMotion();
  const sliderId = useId();
  // 둘이서 5만 원: 식사 · 카페 · 산책 · 놀거리를 다 하고 8,000원이 남는 하루 (첫 진입 시퀀스의 영수증과 같은 계산)
  const [budget, setBudget] = useState(50000);
  const [party, setParty] = useState(2);
  const regions = useRegions();
  // 첫 방문의 시퀀스: 예산은 0원에서 세어 올라간다(돈이 이 서비스의 주인공). 그 전에는 숫자 칸이 아직 보이지 않는다
  const [counting, setCounting] = useState(false);
  useEffect(() => {
    const root = document.documentElement;
    if (root.getAttribute("data-intro") !== "play") return;
    // CSS 시간표는 첫 페인트에서 시작하지만 이 코드는 하이드레이션 뒤에 돈다(느린 폰 · 개발 서버는 몇 초 뒤).
    // 숫자가 이미 보이기 시작했으면 0 으로 되돌렸다 세지 않는다 — 50,000 → 0 → 50,000 깜빡임보다 그냥 50,000 이 낫다
    const paint = performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? 0;
    const wait = paint + COUNT_AT_MS - performance.now();
    let t = 0;
    if (wait > 60) {
      setCounting(true);
      t = window.setTimeout(() => setCounting(false), wait);
    }
    // 다른 화면에 갔다가 돌아오면 다시 틀지 않는다
    return () => {
      window.clearTimeout(t);
      root.removeAttribute("data-intro");
    };
  }, []);

  const items = useMemo(() => sampleCourse(Math.floor(budget / party), party), [budget, party]);
  const total = items.reduce((sum, i) => sum + i.price, 0);
  const left = budget - total;
  const { mood, say } = reaction(left, budget);
  const day = useMemo(() => {
    let at = START_MIN;
    return items.map((item) => {
      const time = hhmm(at);
      at += (STAY_MIN[item.label] ?? 60) + WALK_MIN;
      return { key: `${item.label}-${item.name}`, time, label: item.label, name: item.name, price: item.price === 0 ? "무료" : `${item.price.toLocaleString("ko-KR")}원` };
    });
  }, [items]);

  // 증거는 지어내지 않는다: 지금 DB 에 실제로 있는 숫자만 보여 준다
  const proof = useMemo(() => {
    const all = regions.data?.items ?? [];
    const places = all.filter((r) => r.level === 1).reduce((sum, r) => sum + r.place_count, 0);
    return all.length && places ? { places, regions: all.length } : null;
  }, [regions.data]);

  return (
    <section className="hero-intro paper-grain relative bg-paper pt-[calc(var(--header-h)+36px)] pb-14 lg:pt-[calc(var(--header-h)+64px)] lg:pb-20">
      <div className="wrap">
        {/* 약속 한 줄은 크지만 화면의 주인공은 아니다: 두 줄, 그리고 오른쪽에 짧은 설명 (7 : 5) */}
        <div data-beat="type" className="grid items-end gap-x-16 gap-y-5 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <div>
            <p className="text-body-sm font-semibold text-ink-2">
              내 예산에 맞게, 내가 짠 데이
            </p>
            <h1 className="mt-4 font-serif text-display">
              예산만 말하면,
              <br />
              하루가 영수증으로 나온다.
            </h1>
          </div>
          <p className="max-w-[440px] text-body text-ink-2 lg:pb-1.5">
            지역 · 인원 · 예산을 말하면, 짠이가 전국의 실제 장소로 식사부터 카페, 놀거리까지 한 코스로 이어요. 얼마를 쓰고 <b className="font-bold text-ink">얼마가 남는지</b>부터 영수증으로 보여 드려요.
          </p>
        </div>

        <div className="mt-10 lg:mt-14">
          {/* 1. 오늘 쓸 돈: 이 화면에서 손으로 만지는 유일한 것 */}
          <Field name="오늘 쓸 돈">
            <div className="grid items-end gap-x-12 gap-y-5 md:grid-cols-[minmax(0,1fr)_auto]">
              <div className="max-w-[560px]">
                <label htmlFor={sliderId} className="sr-only">
                  오늘 쓸 돈
                </label>
                <div data-beat="money">
                  <Money value={counting ? 0 : budget} duration={900} className="money block text-price-lg text-ink" />
                </div>
                <input
                  id={sliderId}
                  type="range"
                  className="jj-range mt-5"
                  min={MIN}
                  max={MAX}
                  step={STEP}
                  value={budget}
                  onChange={(e) => setBudget(Number(e.target.value))}
                  aria-valuetext={`${budget.toLocaleString("ko-KR")}원, ${party}명`}
                />
              </div>
              <div className="flex items-center gap-1.5" role="group" aria-label="인원">
                <button type="button" onClick={() => setParty((p) => Math.max(1, p - 1))} disabled={party <= 1} aria-label="인원 줄이기" className="grid size-11 place-items-center rounded-full border border-line bg-white/70 hover:border-ink-2 disabled:opacity-40">
                  <Minus aria-hidden className="size-4" />
                </button>
                <output aria-live="polite" className="tabular min-w-12 text-center text-body-lg font-bold">
                  {party}명
                </output>
                <button type="button" onClick={() => setParty((p) => Math.min(6, p + 1))} disabled={party >= 6} aria-label="인원 늘리기" className="grid size-11 place-items-center rounded-full border border-line bg-white/70 hover:border-ink-2 disabled:opacity-40">
                  <Plus aria-hidden className="size-4" />
                </button>
                <span className="tabular ml-2 text-body-sm font-semibold text-muted-foreground">1인 {Math.floor(budget / party).toLocaleString("ko-KR")}원</span>
              </div>
            </div>
          </Field>

          {/* 2. 오늘의 하루: 그 돈으로 짜인 순서 (경로) */}
          <Field name="오늘의 하루">
            <DayRoute stops={day} />
          </Field>

          {/* 3. 영수증: 뜯는 자리(구멍 줄) 아래에 합계와 남은 돈. 짠이는 여기서만 — 남은 돈을 알려 줄 때 */}
          <Field name="영수증" tear beat="receipt">
            <div className="grid items-end gap-x-10 gap-y-6 md:grid-cols-[auto_auto_minmax(0,1fr)]">
              <dl className="tabular grid gap-1.5 text-body-sm">
                <div className="flex items-baseline justify-between gap-8">
                  <dt className="font-semibold text-muted-foreground">예산</dt>
                  <dd className="font-semibold text-ink-2">{budget.toLocaleString("ko-KR")}원</dd>
                </div>
                <div className="flex items-baseline justify-between gap-8">
                  <dt className="font-semibold text-muted-foreground">합계</dt>
                  <dd className="money text-body-lg text-ink">
                    <Money value={total} />
                  </dd>
                </div>
              </dl>
              <div className="flex items-end gap-3 md:border-l md:border-line md:pl-10">
                <div className="grid">
                  <span className="text-body-sm font-semibold text-gold-ink">남은 돈</span>
                  <Money value={left} className="money text-price-lg text-gold-ink" />
                </div>
                <span data-beat="jjani" className="mb-1 shrink-0">
                  <Jjani mood={mood} className="h-auto w-[52px]" />
                </span>
                <AnimatePresence mode="wait" initial={false}>
                  <motion.p
                    key={say}
                    aria-live="polite"
                    initial={reduced ? false : { opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduced ? undefined : { opacity: 0, y: -4 }}
                    transition={{ duration: 0.18 }}
                    className="tabular mb-2 max-w-[160px] text-body-sm leading-snug font-semibold text-ink-2"
                  >
                    {say}
                  </motion.p>
                </AnimatePresence>
              </div>
              <div data-beat="act" className="md:justify-self-end">
                <Button asChild variant="brand" size="xl" className="group max-md:w-full">
                  <Link href="/plan" onClick={() => track("plan_started", { entry: "landing_hero" })}>
                    이 예산으로 짜기 <ArrowRight aria-hidden className="transition-transform group-hover:translate-x-1" />
                  </Link>
                </Button>
              </div>
            </div>
            <p className="mt-5 text-caption text-muted-foreground">전국 업종 평균가로 만든 예시예요. 실제 코스는 고른 동네의 진짜 가게로 짜 드려요.</p>
          </Field>
        </div>

        {proof ? (
          <dl data-beat="act" className="tabular flex flex-wrap gap-x-7 gap-y-2 border-t border-line pt-5 text-body-sm">
            {[
              { k: "전국 장소", v: `${proof.places.toLocaleString("ko-KR")}곳` },
              { k: "코스를 짜는 동네", v: `${proof.regions}곳` },
              { k: "가입", v: "없이 바로" },
            ].map((p) => (
              <div key={p.k} className="flex items-baseline gap-1.5">
                <dt className="font-semibold text-muted-foreground">{p.k}</dt>
                <dd className="font-bold text-ink">{p.v}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </section>
  );
}
