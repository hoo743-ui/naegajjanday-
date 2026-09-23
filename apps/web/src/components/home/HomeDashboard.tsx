"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PlacePlaceholder } from "@/components/brand/PlacePlaceholder";
import { Hero } from "@/components/landing/Hero";
import { Jjani } from "@/components/mascot/Jjani";
import { track } from "@/lib/analytics";

/**
 * 서비스 홈 = 오늘 바로 쓰는 대시보드 (docs/40). 설명은 소개(/about)가, 이름의 뜻은 인트로(/intro)가 맡는다.
 * 위에서 아래로: 오늘의 두 갈래(예산부터 짜기 · 갈 곳부터 보기) → 빠른 코스 만들기(내가 · 짠 · 데이) → 오늘의 둘러보기 → 예산 · 목적으로 바로 시작.
 */
const TODAY = [
  { href: "/explore?type=park", kind: "WALK", title: "무료 산책", line: "돈 안 드는 공원 · 산책길" },
  { href: "/explore?type=exhibition", kind: "SIGHT", title: "이번 주 전시", line: "지금 열려 있는 전시" },
  { href: "/explore?type=festival", kind: "ACTIVITY", title: "이번 주 축제", line: "7일 안에 열리는 축제" },
  { href: "/explore?type=culture", kind: "CAFE", title: "비 오는 날 실내", line: "지붕 있는 문화공간" },
];
const BUDGETS = [
  { value: 30000, hint: "가볍게" },
  { value: 50000, hint: "무난하게" },
  { value: 100000, hint: "넉넉하게" },
];
const PURPOSES = [
  { code: "date", label: "데이트" },
  { code: "friends", label: "친구" },
  { code: "solo", label: "혼자" },
  { code: "family", label: "가족" },
  { code: "travel", label: "여행" },
];

export function HomeDashboard() {
  return (
    <div className="paper-map bg-paper pt-[calc(var(--header-h)+20px)] pb-16 lg:pt-[calc(var(--header-h)+28px)] short:pt-[calc(var(--header-h)+12px)]">
      <div className="wrap grid gap-8 lg:gap-10">
        {/* 오늘의 두 갈래: 영수증 한 장을 절취선으로 반 가른 표 — 왼쪽은 예산부터(코스 짜기), 오른쪽은 갈 곳부터(둘러보기) */}
        <section aria-labelledby="home-heading" className="grid items-center gap-5 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <h1 id="home-heading" className="text-h1 font-extrabold tracking-[-0.02em] text-ink">
              오늘 어떤 하루를 짜 볼까요?
            </h1>
            <p className="mt-1.5 text-body text-ink-2">예산부터 정해도, 갈 곳부터 봐도 돼요.</p>
          </div>
          <nav aria-label="시작하는 두 갈래" className="home-ticket grid grid-cols-2 lg:col-span-7">
            <Link href="/plan" onClick={() => track("plan_started", { entry: "home_ticket" })} className="home-ticket-half group is-plan">
              <span className="flex items-center gap-2">
                <Jjani mood="hi" className="h-auto w-8 shrink-0" />
                <span className="text-body-sm font-semibold text-white">예산이 먼저예요?</span>
              </span>
              <b className="mt-1 flex items-center gap-1.5 text-h3 font-extrabold text-white">
                짜 볼래요 <ArrowRight aria-hidden className="size-5 transition-transform group-hover:translate-x-1" />
              </b>
              <span className="text-caption font-semibold text-white">코스 짜기 · 예산 안에서 하루를</span>
            </Link>
            <Link href="/explore" className="home-ticket-half group is-explore">
              <span className="flex items-center gap-2">
                <Jjani mood="wink" className="h-auto w-8 shrink-0" />
                <span className="text-body-sm font-semibold text-ink-2">갈 곳부터 볼까요?</span>
              </span>
              <b className="mt-1 flex items-center gap-1.5 text-h3 font-extrabold text-ink">
                둘러볼래요 <ArrowRight aria-hidden className="size-5 transition-transform group-hover:translate-x-1" />
              </b>
              <span className="text-caption font-semibold text-muted-foreground">둘러보기 · 관광지 · 공원 · 전시 · 축제</span>
            </Link>
          </nav>
        </section>

        {/* 빠른 코스 만들기: 내가(조건) → 짠(예산 · 행동) → 데이(하루의 영수증) */}
        <div className="home-panel">
          <Hero compact />
        </div>

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

        {/* 바로 시작: 예산으로 · 약속으로 */}
        <section aria-label="바로 시작" className="grid gap-5 border-t border-dashed border-ink/20 pt-6 md:grid-cols-2">
          <div>
            <h2 className="mb-2.5 text-body-sm font-semibold text-ink-2">예산으로 바로 시작</h2>
            <div className="flex flex-wrap gap-2">
              {BUDGETS.map((b) => (
                <Link
                  key={b.value}
                  href={`/plan?budget=${b.value}&party=2`}
                  onClick={() => track("plan_started", { entry: "home_budget" })}
                  className="tabular inline-flex min-h-12 items-center gap-2 rounded-xl border border-ink/35 bg-paper px-3.5 hover:border-tomato hover:bg-tomato-soft"
                >
                  <b className="text-body-sm font-bold text-ink">{b.value / 10000}만 원</b>
                  <span className="text-caption text-muted-foreground">{b.hint}</span>
                </Link>
              ))}
            </div>
          </div>
          <div>
            <h2 className="mb-2.5 text-body-sm font-semibold text-ink-2">약속으로 바로 시작</h2>
            <div className="flex flex-wrap gap-2">
              {PURPOSES.map((p) => (
                <Link
                  key={p.code}
                  href={`/plan?purpose=${p.code}`}
                  onClick={() => track("plan_started", { entry: "home_purpose" })}
                  className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-ink/20 bg-paper px-4 text-body-sm font-semibold text-ink-2 hover:border-tomato hover:bg-tomato-soft hover:text-ink"
                >
                  {p.label}
                </Link>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
