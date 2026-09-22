"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useFeatures } from "@/lib/api/hooks";
import { ChapterMark } from "./ChapterMark";
import { Reveal } from "./Reveal";

/**
 * 장면 — 나의 하루. 긴 영수증의 끝: 사진 위 짙은 배너가 아니라 종이 위의 뜯는 자리(구멍 줄) 하나.
 * 행동은 하나만 크게(코스 짜기), 다른 길은 글자 링크로. 짠이는 여기서 한 번, 길을 알려 준다 (docs/31 §9 · §10).
 */
export function FinalCta() {
  // 채팅 입구는 쓸 수 있다고 확인된 뒤에만 보인다. 확인 전에 보여 주면, LLM 이 없는 환경(지금의 실제 환경)에서는
  // 입구가 떴다가 1~2초 뒤에 사라진다 — 누르려던 버튼이 손 밑에서 바뀐다(버튼 전수 검사가 잡았다).
  const chatOff = useFeatures().data?.chat !== true;
  return (
    <section id="start" className="pt-[clamp(48px,7vw,96px)] pb-16 lg:pb-24">
      <div className="wrap">
        <ChapterMark label="나의 하루" />
        <hr aria-hidden className="tear-line mt-8" />
        <Reveal className="grid items-end gap-x-16 gap-y-10 pt-12 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:pt-16">
          <div>
            <h2 className="font-serif text-display">
              얼마 쓸 거예요?
              <br />
              코스는 짠이가 짤게요
            </h2>
            <p className="mt-5 text-body-lg text-ink-2">지역 · 인원 · 예산, 세 가지면 충분합니다.</p>
          </div>
          <div className="grid gap-5">
            <p className="flex items-center gap-3 text-body-sm font-semibold text-ink-2">
              <Jjani mood="cheers" size={48} animated={false} />
              예산만 정하면 나머지는 제가 맞춰 볼게요.
            </p>
            <Button asChild variant="brand" size="xl" className="group justify-self-start max-sm:w-full">
              <Link href="/plan" onClick={() => track("plan_started", { entry: "landing_cta" })}>
                예산 정하고 코스 짜기 <ArrowRight aria-hidden className="transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            {chatOff ? (
              <Link href="/explore" className="justify-self-start text-body-sm font-semibold text-ink-2 underline decoration-line decoration-2 underline-offset-4 hover:text-ink hover:decoration-ink">
                갈 만한 곳 먼저 둘러보기
              </Link>
            ) : (
              <Link href="/chat" className="justify-self-start text-body-sm font-semibold text-ink-2 underline decoration-line decoration-2 underline-offset-4 hover:text-ink hover:decoration-ink">
                짠이에게 말로 부탁하기
              </Link>
            )}
          </div>
        </Reveal>
      </div>
    </section>
  );
}
