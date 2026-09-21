"use client";

import { useId, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, Minus, Plus } from "lucide-react";
import { Receipt } from "@/components/brand/Receipt";
import { sampleCourse } from "@/components/brand/sample-course";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useRegions } from "@/lib/api/hooks";
import type { JjaniMood } from "@/lib/mascot-copy";

/**
 * 히어로 = 제품 그 자체. 예산을 움직이면 영수증이 바뀐다.
 * (이전 히어로는 3,000px 짜리 스크롤 고정 데모였다: 아무리 내려도 같은 화면이고, 장면마다 패널 절반이 비어 있었다.)
 *
 * 영수증의 품목은 실제 가게가 아니라 **업종 평균가로 만든 예시**다 — 그렇게 적어 둔다.
 * 실제 코스는 "이 예산으로 코스 받기"를 눌러야 전국 데이터에서 짜인다.
 */
const MIN = 10000;
const MAX = 120000;
const STEP = 5000;

function reaction(left: number, budget: number): { mood: JjaniMood; say: string } {
  const ratio = left / budget;
  if (ratio <= 0.05) return { mood: "cheers", say: "예산을 꽉 채웠어요. 한 푼도 안 넘겨요!" };
  if (ratio <= 0.2) return { mood: "done", say: `짠! ${left.toLocaleString("ko-KR")}원이 남아요` };
  return { mood: "wink", say: `${left.toLocaleString("ko-KR")}원 남으니 디저트 하나 더?` };
}

export function Hero() {
  const reduced = useReducedMotion();
  const sliderId = useId();
  const [budget, setBudget] = useState(40000); // 브랜드의 대표 장면: 둘이서 4만원
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
    reduced ? {} : { initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6, delay, ease: [0.16, 1, 0.3, 1] as const } };

  return (
    <section className="bg-hero relative overflow-hidden pt-[calc(var(--header-h)+36px)] pb-16 lg:pt-[calc(var(--header-h)+64px)] lg:pb-24">
      <div className="wrap grid items-center gap-12 lg:grid-cols-[1.05fr_.95fr] lg:gap-16">
        <div className="text-center lg:text-left">
          <motion.p {...rise(0)} className="inline-flex items-center gap-2 rounded-full bg-white/80 px-3.5 py-1.5 text-[13px] font-bold text-blue-deep shadow-soft">
            내 예산에 맞게, 내가 짠 데이
          </motion.p>
          <motion.h1 {...rise(0.05)} className="my-5 text-[clamp(36px,5vw,62px)] font-extrabold">
            예산만 말해요.
            <br />
            하루는 <span className="gt">짠이가 짤게요.</span>
          </motion.h1>
          <motion.p {...rise(0.1)} className="mx-auto max-w-[540px] text-[clamp(16px,1.5vw,18px)] leading-[1.7] text-muted-foreground lg:mx-0">
            지역 · 인원 · 예산 세 가지면 식사부터 카페, 놀거리까지 한 코스로. 얼마를 쓰고 <b className="font-bold text-ink">얼마가 남는지</b> 영수증으로 먼저 보여 드려요.
          </motion.p>

          {/* 바로 만져 보는 입력 — 설명 대신 제품 */}
          <motion.div {...rise(0.16)} className="mx-auto mt-8 max-w-[540px] rounded-[28px] bg-white p-5 text-left shadow-card sm:p-6 lg:mx-0">
            <div className="flex items-end justify-between gap-4">
              <label htmlFor={sliderId} className="text-sm font-extrabold text-muted-foreground">
                오늘 쓸 돈
              </label>
              <b className="tabular text-[30px] leading-none font-extrabold tracking-tight text-ink">{budget.toLocaleString("ko-KR")}원</b>
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
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2" role="group" aria-label="인원">
                <button type="button" onClick={() => setParty((p) => Math.max(1, p - 1))} disabled={party <= 1} aria-label="인원 줄이기" className="grid size-10 place-items-center rounded-xl bg-[#F0F4FA] transition-colors hover:bg-line disabled:opacity-40">
                  <Minus aria-hidden className="size-4" />
                </button>
                <output aria-live="polite" className="tabular min-w-12 text-center text-[17px] font-extrabold">
                  {party}명
                </output>
                <button type="button" onClick={() => setParty((p) => Math.min(6, p + 1))} disabled={party >= 6} aria-label="인원 늘리기" className="grid size-10 place-items-center rounded-xl bg-[#F0F4FA] transition-colors hover:bg-line disabled:opacity-40">
                  <Plus aria-hidden className="size-4" />
                </button>
                <span className="tabular ml-1 text-[13px] font-bold text-muted-foreground">1인 {Math.floor(budget / party).toLocaleString("ko-KR")}원</span>
              </div>
              <Button asChild variant="brand" size="lg" className="group max-sm:w-full">
                <Link href="/plan" onClick={() => track("plan_started", { entry: "landing_hero" })}>
                  이 예산으로 코스 받기 <ArrowRight aria-hidden className="transition-transform group-hover:translate-x-1" />
                </Link>
              </Button>
            </div>
          </motion.div>

          {proof ? (
            <motion.dl {...rise(0.22)} className="tabular mx-auto mt-7 flex max-w-[540px] flex-wrap justify-center gap-x-7 gap-y-2 text-sm lg:mx-0 lg:justify-start">
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

        {/* 영수증 무대 */}
        <motion.div {...rise(0.12)} className="relative mx-auto w-full max-w-[400px]">
          <div className="mb-3 flex items-end gap-2">
            <Jjani mood={mood} className="h-auto w-[88px] shrink-0 lg:w-[104px]" />
            <div className="relative mb-6 min-w-0 rounded-[20px] rounded-bl-md bg-white px-4 py-3 shadow-card" aria-live="polite">
              <AnimatePresence mode="wait" initial={false}>
                <motion.b
                  key={say}
                  initial={reduced ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduced ? undefined : { opacity: 0, y: -6 }}
                  transition={{ duration: 0.18 }}
                  className="block font-round text-[17px] leading-snug font-normal text-ink lg:text-[18px]"
                >
                  {say}
                </motion.b>
              </AnimatePresence>
            </div>
          </div>
          <Receipt
            heading={`${party}명 · 저녁 코스 · 예시`}
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
          <span aria-hidden className="absolute -top-8 -right-6 -z-10 size-44 rounded-full bg-pink/25 blur-3xl" />
          <span aria-hidden className="absolute -bottom-6 -left-10 -z-10 size-52 rounded-full bg-blue/25 blur-3xl" />
        </motion.div>
      </div>
    </section>
  );
}
