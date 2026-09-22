"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useFeatures } from "@/lib/api/hooks";
import { ChapterMark } from "./ChapterMark";
import { Reveal } from "./Reveal";

/**
 * 장면 05 — 나의 하루. 긴 영수증의 끝: 한강의 밤 위에 깊은 잉크 한 장, 위쪽 가장자리는 영수증의 톱니.
 * 짠이는 크게 둥실거리지 않고, 문장 옆에서 작게 건배한다.
 */
export function FinalCta() {
  // 채팅 입구는 쓸 수 있다고 확인된 뒤에만 보인다. 확인 전에 보여 주면, LLM 이 없는 환경(지금의 실제 환경)에서는
  // 입구가 떴다가 1~2초 뒤에 사라진다 — 누르려던 버튼이 손 밑에서 바뀐다(버튼 전수 검사가 잡았다).
  const chatOff = useFeatures().data?.chat !== true;
  return (
    <section id="start" className="pt-[clamp(40px,6vw,80px)] pb-12 lg:pb-20">
      <div className="wrap">
        <Reveal className="receipt-wrap">
          <div className="tear-top relative isolate overflow-hidden bg-navy">
            <Image src="/images/story/hangang-night.jpg" alt="" fill sizes="(max-width: 1200px) 100vw, 1136px" className="-z-10 object-cover object-[70%_60%] opacity-55" />
            <span aria-hidden className="absolute inset-0 -z-10 bg-gradient-to-r from-navy via-navy/80 to-navy/5" />
            <div className="grid gap-10 px-7 pt-16 pb-14 sm:px-12 sm:pt-20 sm:pb-16 lg:grid-cols-[1.2fr_.8fr] lg:items-end lg:px-16 lg:pt-24 lg:pb-20">
              <div>
                <ChapterMark n="05" label="나의 하루" tone="light" className="max-w-[420px]" />
                <h2 className="mt-8 font-serif text-display text-white">
                  얼마 쓸 거예요?
                  <br />
                  코스는 짠이가 짤게요
                </h2>
                <p className="mt-5 text-body-lg text-white/75">지역 · 인원 · 예산, 세 가지면 충분합니다.</p>
                <div className="mt-9 flex flex-wrap gap-3">
                  <Button asChild variant="white" size="xl" className="group h-[60px] px-8 text-body-lg">
                    <Link href="/plan" onClick={() => track("plan_started", { entry: "landing_cta" })}>
                      무료로 추천받기 <ArrowRight aria-hidden className="transition-transform group-hover:translate-x-1" />
                    </Link>
                  </Button>
                  {chatOff ? (
                    <Button asChild size="xl" className="h-[60px] border border-white/35 bg-transparent px-7 text-body-lg font-extrabold text-white hover:bg-white/10">
                      <Link href="/explore">갈 만한 곳 먼저 둘러보기</Link>
                    </Button>
                  ) : (
                    <Button asChild size="xl" className="h-[60px] border border-white/35 bg-transparent px-7 text-body-lg font-extrabold text-white hover:bg-white/10">
                      <Link href="/chat">짠이에게 말로 부탁하기</Link>
                    </Button>
                  )}
                </div>
              </div>
              <div className="flex items-end justify-between gap-4 lg:flex-col lg:items-end">
                <Jjani mood="cheers" size={96} className="drop-shadow-[0_14px_24px_rgba(0,0,0,.3)]" />
                <p className="text-caption font-medium text-white/50">사진 ©한국관광공사 · 한강의 밤</p>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
