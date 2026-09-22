"use client";

import { useId, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, Minus, Plus } from "lucide-react";
import { DAY_LINE_PATH, DAY_LINE_STOPS, DAY_LINE_VIEWBOX, tearHoles, DAY_LINE_TEAR } from "@/components/brand/day-line";
import { Money } from "@/components/brand/Money";
import { Receipt } from "@/components/brand/Receipt";
import { sampleCourse } from "@/components/brand/sample-course";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useRegions } from "@/lib/api/hooks";
import type { JjaniMood } from "@/lib/mascot-copy";

/**
 * 히어로 = 제품 그 자체 (docs/25 §5). 왼쪽은 약속 한 문장, 오른쪽은 살아 있는 영수증. 예산을 움직이면 영수증이 다시 찍힌다.
 * 뒤에는 한옥 지붕 너머 도시가 보이는 사진을 아주 옅게 — 깊이만 준다. 주인공은 돈 → 영수증 → 하루다.
 * 바닥에는 첫 진입 시퀀스가 그린 "하루의 선"이 옅게 남아 있다.
 *
 * 영수증의 품목은 실제 가게가 아니라 **업종 평균가로 만든 예시**다 — 그렇게 적어 둔다.
 */
const MIN = 10000;
const MAX = 120000;
const STEP = 5000;

function reaction(left: number, budget: number): { mood: JjaniMood; say: string } {
  const ratio = left / budget;
  if (ratio <= 0.05) return { mood: "cheers", say: "예산을 꽉 채웠어요. 한 푼도 안 넘겨요" };
  if (ratio <= 0.2) return { mood: "done", say: `여기서 ${left.toLocaleString("ko-KR")}원 남아요` };
  return { mood: "wink", say: `${left.toLocaleString("ko-KR")}원 남으니 디저트 하나 더?` };
}

export function Hero() {
  const reduced = useReducedMotion();
  const sliderId = useId();
  // 둘이서 5만 원: 식사 · 카페 · 산책 · 놀거리를 다 하고 8,000원이 남는 하루 (첫 진입 시퀀스의 영수증과 같은 계산)
  const [budget, setBudget] = useState(50000);
  const [party, setParty] = useState(2);
  const regions = useRegions();

  const items = useMemo(() => sampleCourse(Math.floor(budget / party), party), [budget, party]);
  const total = items.reduce((sum, i) => sum + i.price, 0);
  const { mood, say } = reaction(budget - total, budget);

  // 증거는 지어내지 않는다: 지금 DB 에 실제로 있는 숫자만 보여 준다
  const proof = useMemo(() => {
    const all = regions.data?.items ?? [];
    const places = all.filter((r) => r.level === 1).reduce((sum, r) => sum + r.place_count, 0);
    return all.length && places ? { places, regions: all.length } : null;
  }, [regions.data]);

  const rise = (delay: number) =>
    reduced ? {} : { initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] as const } };

  return (
    <section className="paper-grain relative isolate overflow-hidden bg-paper pt-[calc(var(--header-h)+40px)] pb-20 lg:pt-[calc(var(--header-h)+72px)] lg:pb-28">
      {/* 깊이: 한옥 지붕 너머의 도시. 영수증 뒤쪽에만, 아주 옅게 */}
      <div aria-hidden className="absolute inset-y-0 right-0 -z-10 w-full lg:w-[62%]">
        <Image
          src="/images/story/bukchon-roofs.jpg"
          alt=""
          fill
          priority
          sizes="(max-width: 1024px) 100vw, 62vw"
          className="object-cover opacity-[0.16] grayscale-[35%] [mask-image:linear-gradient(to_left,black_20%,transparent_92%),linear-gradient(to_top,transparent,black_30%)] [mask-composite:intersect]"
        />
      </div>

      {/* 하루의 선: 인트로가 그린 선이 바닥에 옅게 남아 있다 */}
      <svg aria-hidden viewBox={DAY_LINE_VIEWBOX} preserveAspectRatio="xMidYMax meet" className="pointer-events-none absolute inset-x-0 bottom-0 -z-10 mx-auto h-auto w-[min(1400px,140vw)] max-w-none translate-x-[-1%] opacity-[0.13] lg:w-full">
        <path d={DAY_LINE_PATH} fill="none" stroke="#10192E" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
        {DAY_LINE_STOPS.map(([x, y]) => (
          <circle key={x} cx={x} cy={y} r={4.5} fill="#10192E" />
        ))}
        {tearHoles().map((x) => (
          <circle key={x} cx={x} cy={DAY_LINE_TEAR.y} r={2} fill="#10192E" />
        ))}
      </svg>

      {/* 모바일: 약속 → 영수증 → 예산 조절 (예산을 움직이면 바로 위의 영수증이 다시 찍힌다). 데스크톱: 왼쪽 두 칸 · 오른쪽 영수증 */}
      <div className="wrap grid items-center gap-x-20 gap-y-12 lg:grid-cols-[1.08fr_.92fr] lg:grid-rows-[auto_auto]">
        <div className="lg:col-start-1 lg:row-start-1 lg:self-end">
          <motion.p {...rise(0)} className="flex items-center gap-2.5 text-[13px] font-extrabold tracking-[0.02em] text-ink-2">
            <span aria-hidden className="size-2 rounded-full bg-gold" />
            내 예산에 맞게, 내가 짠 데이
          </motion.p>
          <motion.h1 {...rise(0.06)} className="mt-6 text-[clamp(38px,4.9vw,68px)] leading-[1.14] font-bold tracking-[-0.035em]">
            예산만 말하면,
            <br />
            하루가 <span className="relative whitespace-nowrap">영수증<span aria-hidden className="absolute inset-x-0 bottom-[0.08em] -z-10 h-[0.22em] rounded-full bg-gold/45" /></span>으로
            <br />
            나온다.
          </motion.h1>
          <motion.p {...rise(0.12)} className="mt-6 max-w-[500px] text-[clamp(16px,1.4vw,18px)] leading-[1.75] text-ink-2">
            지역 · 인원 · 예산을 말하면, 짠이가 전국의 실제 장소로 식사부터 카페, 놀거리까지 한 코스로 이어요. 얼마를 쓰고 <b className="font-bold text-ink">얼마가 남는지</b>부터 영수증으로 보여 드려요.
          </motion.p>
        </div>

        <div className="order-3 lg:order-none lg:col-start-1 lg:row-start-2 lg:self-start">

          {/* 바로 만져 보는 예산: 카드가 아니라 위아래 선 사이의 한 줄 */}
          <motion.div {...rise(0.18)} className="max-w-[520px] border-y border-ink/10 py-6">
            <div className="flex items-end justify-between gap-4">
              <label htmlFor={sliderId} className="text-[13px] font-extrabold text-muted-foreground">
                오늘 쓸 돈
              </label>
              <Money value={budget} className="text-[clamp(30px,3.4vw,40px)] leading-none font-extrabold tracking-[-0.035em] text-ink" />
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
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-1.5" role="group" aria-label="인원">
                <button type="button" onClick={() => setParty((p) => Math.max(1, p - 1))} disabled={party <= 1} aria-label="인원 줄이기" className="grid size-11 place-items-center rounded-full border border-line bg-white/70 hover:border-ink-2 disabled:opacity-40">
                  <Minus aria-hidden className="size-4" />
                </button>
                <output aria-live="polite" className="tabular min-w-12 text-center text-[17px] font-extrabold">
                  {party}명
                </output>
                <button type="button" onClick={() => setParty((p) => Math.min(6, p + 1))} disabled={party >= 6} aria-label="인원 늘리기" className="grid size-11 place-items-center rounded-full border border-line bg-white/70 hover:border-ink-2 disabled:opacity-40">
                  <Plus aria-hidden className="size-4" />
                </button>
                <span className="tabular ml-1.5 text-[13px] font-bold text-muted-foreground">1인 {Math.floor(budget / party).toLocaleString("ko-KR")}원</span>
              </div>
              <Button asChild variant="brand" size="lg" className="group max-sm:w-full">
                <Link href="/plan" onClick={() => track("plan_started", { entry: "landing_hero" })}>
                  이 예산으로 코스 받기 <ArrowRight aria-hidden className="transition-transform group-hover:translate-x-1" />
                </Link>
              </Button>
            </div>
          </motion.div>

          {proof ? (
            <motion.dl {...rise(0.24)} className="tabular mt-6 flex max-w-[520px] flex-wrap gap-x-7 gap-y-2 text-[13.5px]">
              {[
                { k: "전국 장소", v: `${proof.places.toLocaleString("ko-KR")}곳` },
                { k: "코스를 짜는 동네", v: `${proof.regions}곳` },
                { k: "가입", v: "없이 바로" },
              ].map((p) => (
                <div key={p.k} className="flex items-baseline gap-1.5">
                  <dt className="font-bold text-muted-foreground">{p.k}</dt>
                  <dd className="font-extrabold text-ink">{p.v}</dd>
                </div>
              ))}
            </motion.dl>
          ) : null}
        </div>

        {/* 떠 있는 영수증. 짠이는 옆에서 작게 들여다본다 (콘텐츠 80 : 캐릭터 20) */}
        <motion.div {...rise(0.14)} className="relative mx-auto w-full max-w-[400px] lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:mr-0">
          <div className="absolute -top-2 -left-3 z-10 flex items-end gap-2 sm:-left-14 lg:-left-20">
            <Jjani mood={mood} className="h-auto w-[64px] shrink-0 drop-shadow-[0_8px_14px_rgba(72,54,24,.18)] lg:w-[76px]" />
            <div className="relative mb-9 max-w-[200px] rounded-2xl rounded-bl-sm bg-white px-3.5 py-2 shadow-soft" aria-live="polite">
              <AnimatePresence mode="wait" initial={false}>
                <motion.b
                  key={say}
                  initial={reduced ? false : { opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduced ? undefined : { opacity: 0, y: -5 }}
                  transition={{ duration: 0.18 }}
                  className="tabular block text-[13.5px] leading-snug font-extrabold text-ink"
                >
                  {say}
                </motion.b>
              </AnimatePresence>
            </div>
          </div>
          <Receipt
            className="pt-16"
            size="lg"
            heading={`서울 · ${party}명 · 데이트 · 예시`}
            caption="저녁 6시 ~ 10시"
            items={items}
            budget={budget}
            footer={
              <>
                전국 업종 평균가로 만든 예시예요.
                <br />
                실제 코스는 고른 동네의 진짜 가게로 짜 드려요.
              </>
            }
          />
        </motion.div>
      </div>
    </section>
  );
}
