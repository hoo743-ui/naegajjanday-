"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PlacePlaceholder } from "@/components/brand/PlacePlaceholder";
import { Jjani } from "@/components/mascot/Jjani";
import { track } from "@/lib/analytics";
import { QuickCourse } from "./QuickCourse";

/**
 * 서비스 홈 = 오늘 바로 쓰는 대시보드 (docs/40 · docs/41). 설명은 소개(/about)가, 이름의 뜻은 인트로(/intro)가 맡는다.
 * 첫 화면의 핵심은 둘뿐: 예산부터 짜기 · 갈 곳부터 둘러보기. 그 아래 세 줄짜리 빠른 코스 만들기, 더 아래 오늘의 둘러보기.
 */
const TODAY = [
  { href: "/explore?type=park", kind: "WALK", title: "무료 산책", line: "돈 안 드는 공원 · 산책길" },
  { href: "/explore?type=exhibition", kind: "SIGHT", title: "이번 주 전시", line: "지금 열려 있는 전시" },
  { href: "/explore?type=festival", kind: "ACTIVITY", title: "이번 주 축제", line: "7일 안에 열리는 축제" },
  { href: "/explore?type=culture", kind: "CAFE", title: "비 오는 날 실내", line: "지붕 있는 문화공간" },
];
export function HomeDashboard() {
  return (
    <div className="paper-map bg-paper pt-[calc(var(--header-h)+20px)] pb-16 lg:pt-[calc(var(--header-h)+28px)] short:pt-[calc(var(--header-h)+12px)]">
      <div className="wrap grid gap-8 lg:gap-10">
        {/* 오늘의 두 갈래: 영수증 한 장을 절취선으로 반 가른 표 — 왼쪽은 예산부터(코스 짜기), 오른쪽은 갈 곳부터(둘러보기) */}
        <section aria-labelledby="home-heading" className="grid gap-5">
          <div>
            <h1 id="home-heading" className="text-h1 font-extrabold tracking-[-0.02em] text-ink">
              오늘 어떤 하루를 짜 볼까요?
            </h1>
            <p className="mt-1.5 text-body text-ink-2">얼마를 쓰든, 오늘의 주인공은 같이 보낼 시간이에요.</p>
          </div>
          <nav aria-label="시작하는 두 갈래" className="home-ticket grid grid-cols-2">
            <Link href="/plan" onClick={() => track("plan_started", { entry: "home_ticket" })} className="home-ticket-half group is-plan">
              <span className="flex items-center gap-2">
                <Jjani mood="hi" className="h-auto w-8 shrink-0" />
                <span className="text-body-sm font-semibold text-white">예산이 먼저예요?</span>
              </span>
              <b className="mt-1 flex items-center gap-1.5 text-h3 font-extrabold text-white sm:text-h2">
                <span className="sm:hidden">짜 볼래요</span>
                <span className="max-sm:hidden">예산부터 짜기</span> <ArrowRight aria-hidden className="size-5 transition-transform group-hover:translate-x-1" />
              </b>
              <span className="text-caption font-semibold text-white">코스 짜기</span>
            </Link>
            <Link href="/explore" className="home-ticket-half group is-explore">
              <span className="flex items-center gap-2">
                <Jjani mood="wink" className="h-auto w-8 shrink-0" />
                <span className="text-body-sm font-semibold text-ink-2">갈 곳부터 볼까요?</span>
              </span>
              <b className="mt-1 flex items-center gap-1.5 text-h3 font-extrabold text-ink sm:text-h2">
                <span className="sm:hidden">둘러볼래요</span>
                <span className="max-sm:hidden">갈 곳부터 둘러보기</span> <ArrowRight aria-hidden className="size-5 transition-transform group-hover:translate-x-1" />
              </b>
              <span className="text-caption font-semibold text-muted-foreground">관광지 · 공원 · 전시 · 축제</span>
            </Link>
          </nav>
        </section>

        {/* 빠른 코스 만들기: 세 줄(어디서 · 얼마로 · 누구랑)과 한 줄 요약 */}
        <QuickCourse />

        {/* 오늘의 둘러보기 */}
        <section aria-labelledby="today-heading">
          <h2 id="today-heading" className="mb-3 text-h3 font-bold text-ink">
            오늘의 둘러보기
          </h2>
          <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {TODAY.map((t) => (
              <li key={t.href}>
                <Link href={t.href} className="group grid overflow-hidden rounded-lg border border-ink/15 bg-white hover:border-tomato">
                  <PlacePlaceholder kind={t.kind} size="lg" className="aspect-[16/9]" />
                  <span className="grid gap-0.5 px-3.5 py-3">
                    <b className="text-body font-bold text-ink group-hover:text-tomato-deep">{t.title}</b>
                    <span className="text-caption text-muted-foreground">{t.line}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

      </div>
    </div>
  );
}
