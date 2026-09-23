"use client";

import { useEffect, useId, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, Minus, Plus } from "lucide-react";
import { DayRoute } from "@/components/brand/DayRoute";
import { Money } from "@/components/brand/Money";
import { Receipt } from "@/components/brand/Receipt";
import { sampleCourse } from "@/components/brand/sample-course";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useRegions } from "@/lib/api/hooks";
import type { JjaniMood } from "@/lib/mascot-copy";

/**
 * 히어로 = 서울이라는 공간 위에서 하루를 한 번 짜 보는 장면 (docs/31 §4 · docs/33). 서울은 카드가 아니라 배경(공간)이고,
 * 그 위에 약속 한 줄 → **오늘 쓸 돈 → 오늘의 하루**, 전경에 **영수증 한 장**과 남은 돈을 말하는 짠이.
 * 돈을 움직이면 하루가 다시 짜이고 영수증이 다시 찍힌다.
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
/** 장면 그림의 sizes: 좁은 화면 · 넓은 화면 두 곳이 같은 값을 써야 같은 파일을 받는다 */
const SCENE_SIZES = "(max-width: 1024px) 100vw, 1400px";
/** 빠른 선택: 슬라이더를 끌지 않고 한 번에 */
const PRESETS = [30000, 50000, 100000];
/** 장면 그림(1536×1024) 속 지도 핀의 머리 — 경복궁 · 종로 · 남대문 · 명동 */
const SCENE_STOPS: [number, number][] = [
  [1040, 76],
  [1160, 160],
  [1159, 297],
  [1299, 256],
];

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
const COUNT_AT_MS = 560;

const hhmm = (min: number) => `${String(Math.floor(min / 60) % 24).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

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
      return { key: `${item.label}-${item.name}`, time, label: item.label, name: item.name };
    });
  }, [items]);

  // 증거는 지어내지 않는다: 지금 DB 에 실제로 있는 숫자만 보여 준다
  const proof = useMemo(() => {
    const all = regions.data?.items ?? [];
    const places = all.filter((r) => r.level === 1).reduce((sum, r) => sum + r.place_count, 0);
    return all.length && places ? places : null;
  }, [regions.data]);

  return (
    <section className="hero-intro paper-grain relative isolate overflow-hidden bg-paper pt-[calc(var(--header-h)+28px)] pb-10 lg:min-h-[min(920px,100svh)] lg:pt-[calc(var(--header-h)+56px)] lg:pb-20">
      {/* 장면 (docs/33 §Hero 배경): 서울이 카드나 액자가 아니라 이 하루가 놓이는 공간이다. 종이(바탕) → 서울 → 종이로 번지는 가장자리 →
          오늘의 정거장 → 글 → 예산 → 영수증 → 짠이. 넓은 화면은 그림의 원래 비율(3:2)로 오른쪽에 붙여, 정거장 점이 그림 속 지도 핀에 정확히 앉는다.
          그림 왼쪽에 인쇄된 글귀는 종이로 번지는 가장자리 밑에 가려진다 */}
      <div aria-hidden className="hero-scene pointer-events-none absolute top-0 right-0 -z-10 hidden h-full aspect-[3/2] lg:block">
        <div data-beat="scene" className="absolute inset-0">
          <Image src="/images/hero/seoul-scene.jpg" alt="" fill priority sizes={SCENE_SIZES} className="hero-scene-img object-cover" />
        </div>
        {/* 오늘의 정거장: 그림 속 지도 핀(경복궁 · 종로 · 남대문 · 명동) 위에 잉크 점이 차례로 놓인다 */}
        <svg viewBox="0 0 1536 1024" preserveAspectRatio="none" className="hero-scene-stops absolute inset-0 size-full">
          {SCENE_STOPS.map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r="7" style={{ "--i": i } as React.CSSProperties} className="scene-stop" />
          ))}
        </svg>
      </div>

      <div className="wrap grid gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
        {/* 왼쪽: 약속 한 줄 → 오늘 쓸 돈 → 오늘의 하루 → 행동 하나. 작은 이름표 · 캡션은 두지 않는다 (docs/33) */}
        <div className="min-w-0">
          <div data-beat="type">
            {/* 줄바꿈이 리듬을 만든다 (docs/35 §5): 조건 한 줄 → 쉼 → 결과. 강조는 금색이 아니라 크기와 굵기로 */}
            <h1 className="font-serif text-display-xl">
              예산만 말하면,
              <br />
              하루가
              <br />
              <span className="hero-em">영수증</span>으로 나온다.
            </h1>
            <p className="mt-5 max-w-[440px] text-body-lg text-ink-2">짠이가 실제 장소로 하루를 짜고, 얼마가 남는지까지 영수증 한 장으로 보여 드려요.</p>
          </div>

          {/* 오늘 쓸 돈: 떠 있는 카드가 아니라 종이 위의 입력 줄 — 숫자 → 슬라이더 → 빠른 선택 */}
          <div data-beat="money" className="mt-8 max-w-[520px] border-y border-ink/15 py-5">
            <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
              <div className="grid">
                <label htmlFor={sliderId} className="text-body-sm font-semibold text-ink-2">
                  오늘 쓸 돈
                </label>
                <Money value={counting ? 0 : budget} duration={900} className="money text-price-lg text-ink" />
              </div>
              <div className="flex items-center gap-1.5" role="group" aria-label="인원">
                <button type="button" onClick={() => setParty((p) => Math.max(1, p - 1))} disabled={party <= 1} aria-label="인원 줄이기" className="grid size-11 place-items-center rounded-full border border-ink/15 bg-paper/80 hover:border-ink-2 disabled:opacity-40">
                  <Minus aria-hidden className="size-4" />
                </button>
                <output aria-live="polite" className="tabular min-w-12 text-center text-body-lg font-bold">
                  {party}명
                </output>
                <button type="button" onClick={() => setParty((p) => Math.min(6, p + 1))} disabled={party >= 6} aria-label="인원 늘리기" className="grid size-11 place-items-center rounded-full border border-ink/15 bg-paper/80 hover:border-ink-2 disabled:opacity-40">
                  <Plus aria-hidden className="size-4" />
                </button>
              </div>
            </div>
            <input
              id={sliderId}
              type="range"
              className="jj-range mt-4"
              min={MIN}
              max={MAX}
              step={STEP}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
              aria-valuetext={`${budget.toLocaleString("ko-KR")}원, ${party}명`}
            />
            <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="자주 쓰는 예산">
              {PRESETS.map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={budget === value}
                  onClick={() => setBudget(value)}
                  className="tabular inline-flex h-11 items-center rounded-full border border-ink/15 bg-paper/80 px-4 text-body-sm font-semibold text-ink-2 hover:border-ink-2 hover:text-ink aria-pressed:border-ink aria-pressed:bg-ink aria-pressed:text-white"
                >
                  {value / 10000}만 원
                </button>
              ))}
            </div>
          </div>

          {/* 오늘의 하루: 그 돈으로 짜인 순서. 좁은 화면에서는 영수증이 하루를 말한다 */}
          <div className="mt-7 hidden max-w-[520px] sm:block">
            <DayRoute stops={day} />
          </div>

          <div data-beat="act" className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <Button asChild variant="brand" size="xl" className="group max-sm:w-full">
              <Link href="/plan" onClick={() => track("plan_started", { entry: "landing_hero" })}>
                이 예산으로 짜기 <ArrowRight aria-hidden className="transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            {/* 증거는 지어내지 않는다: 지금 DB 에 실제로 있는 숫자만 */}
            {proof ? (
              <p className="tabular text-body-sm font-semibold text-ink-2">
                전국 실제 장소 <b className="font-bold text-ink">{proof.toLocaleString("ko-KR")}곳</b> · 가입 없이 바로
              </p>
            ) : null}
          </div>
        </div>

        {/* 오른쪽: 서울 위, 전경의 영수증 한 장과 짠이. 넓은 화면은 칸의 오른쪽 아래(그림 속 광장 · 뜯긴 영수증 자리)에 놓여 성문의 홍예는 가리지 않는다.
            예시라는 사실은 영수증 머리에 적는다 */}
        <div className="relative h-[660px] lg:h-auto lg:self-stretch">
          {/* 좁은 화면의 장면: 영수증 칸 위쪽에 성문 지붕과 스카이라인이 보이게 (같은 그림 · 같은 sizes → 한 번만 받는다) */}
          <div aria-hidden className="hero-scene pointer-events-none absolute -inset-x-4 -top-5 -z-10 h-[400px] lg:hidden">
            <div data-beat="scene" className="absolute inset-0">
              <Image src="/images/hero/seoul-scene.jpg" alt="" fill sizes={SCENE_SIZES} className="hero-scene-img object-cover object-right" />
            </div>
          </div>
          <div className="hero-par-fg absolute right-0 bottom-0 w-[82%] max-w-[296px] lg:-right-4 lg:bottom-[-28px]">
            <div data-beat="receipt">
              {/* 기울기는 안쪽에: 출력 애니메이션의 transform 이 기울기를 덮어쓰지 않게 */}
              <Receipt heading={`예시 · ${party}명 · 업종 평균가`} items={items} budget={budget} className="-rotate-1 drop-shadow-[0_18px_28px_rgba(40,32,20,.16)]" />
            </div>
          </div>
          {/* 짠이는 여기서 한 번: 영수증 곁에서 남은 돈을 알려 주는 동행 */}
          <div data-beat="jjani" className="absolute top-6 left-0 flex max-w-[150px] flex-col items-start gap-1.5 lg:top-auto lg:right-[300px] lg:bottom-2 lg:left-auto lg:items-end">
            <AnimatePresence mode="wait" initial={false}>
              <motion.p
                key={say}
                aria-live="polite"
                initial={reduced ? false : { opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduced ? undefined : { opacity: 0, y: -4 }}
                transition={{ duration: 0.18 }}
                className="tabular rounded-lg rounded-bl-sm bg-paper px-3 py-2 text-body-sm leading-snug font-semibold text-ink shadow-soft lg:rounded-bl-lg lg:rounded-br-sm"
              >
                {say}
              </motion.p>
            </AnimatePresence>
            <Jjani mood={mood} className="h-auto w-[60px] drop-shadow-sm lg:mr-3" />
          </div>
        </div>
      </div>
    </section>
  );
}
