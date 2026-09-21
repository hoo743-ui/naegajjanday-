"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useFeatures } from "@/lib/api/hooks";
import { Reveal } from "./Reveal";

export function FinalCta() {
  const chatOff = useFeatures().data?.chat === false;
  return (
    <section id="start" className="pt-6 pb-10 lg:pb-16">
      <div className="wrap">
        <Reveal className="relative overflow-hidden rounded-[40px] bg-navy bg-[radial-gradient(90%_120%_at_50%_0%,rgba(233,180,76,.16),transparent_60%)] px-6 py-16 text-center text-white shadow-float sm:px-8 sm:py-20">
          <div className="relative">
            <Jjani
              mood="cheers"
              size={130}
              floating
              className="mx-auto drop-shadow-[0_14px_24px_rgba(20,33,61,.25)]"
            />
            <h2 className="my-3.5 text-[clamp(29px,4.4vw,54px)] font-extrabold font-serif">
              얼마 쓸 거예요?
              <br />
              코스는 짠이가 짤게요
            </h2>
            <p className="mb-8 text-lg text-white/80">
              지역 · 인원 · 예산, 세 가지면 충분합니다.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <Button
                asChild
                variant="white"
                size="xl"
                className="group h-[62px] px-9 text-lg"
              >
                <Link
                  href="/plan"
                  onClick={() =>
                    track("plan_started", { entry: "landing_cta" })
                  }
                >
                  무료로 추천받기{" "}
                  <ArrowRight
                    aria-hidden
                    className="transition-transform group-hover:translate-x-1"
                  />
                </Link>
              </Button>
              {chatOff ? (
                <Button
                  asChild
                  size="xl"
                  className="h-[62px] border border-white/50 bg-white/10 px-7 text-lg font-extrabold text-white backdrop-blur hover:bg-white/20"
                >
                  <Link href="/explore">갈 만한 곳 먼저 둘러보기</Link>
                </Button>
              ) : (
                <Button
                  asChild
                  size="xl"
                  className="h-[62px] border border-white/50 bg-white/10 px-7 text-lg font-extrabold text-white backdrop-blur hover:bg-white/20"
                >
                  <Link href="/chat">짠이에게 말로 부탁하기</Link>
                </Button>
              )}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
