"use client";

import { useEffect, useRef, type CSSProperties } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { Wordmark } from "@/components/brand/Wordmark";
import { track } from "@/lib/analytics";

const CHIPS = ["홍대", "2명", "50,000원", "데이트"];
const LINES: [string, string][] = [
  ["식사", "22,000원"],
  ["카페", "6,000원"],
  ["산책", "무료"],
  ["놀거리", "14,000원"],
];
const DAY: [string, string][] = [
  ["18:00", "식사"],
  ["19:20", "카페"],
  ["20:10", "산책"],
  ["21:00", "놀거리"],
];

/**
 * 홈페이지 주소(/)의 브랜드 인트로 (약 4초 · docs/38 · docs/40): 이름을 세 번에 나눠 보여 준 뒤, 스스로 들어오게 한다(→ /home).
 *   내가 — 조건 칩(홍대 · 2명 · 50,000원 · 데이트)이 손으로 고른 듯 톡톡 놓인다
 *   짠   — 도장이 찍히고, 영수증이 한 줄씩 인쇄되고, 합계가 나온다
 *   데이 — 영수증이 하루의 시간표로 펼쳐지고, "남은 돈 8,000원" 도장
 *   → 세 조각이 워드마크 하나로 모이고, 한 줄 설명과 "입장하기" · "내 하루 짜기"
 * 자동으로 넘어가지 않는다. 시간표는 전부 CSS(globals.css `.brand-intro`) — 스크립트가 늦게 붙어도 제 시간에 돈다.
 * 모션 최소화: 움직임 없이 마지막 화면(워드마크 · 세 낱말의 뜻 · 버튼)이 바로 보인다.
 */
export function BrandIntro() {
  const router = useRouter();
  const enterRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    // 버튼이 나타날 즈음 키보드 초점을 그리로 — Enter 한 번이면 들어간다
    const t = window.setTimeout(() => enterRef.current?.focus({ preventScroll: true }), 3600);
    return () => window.clearTimeout(t);
  }, []);

  const enter = (to: string, entry: "intro_enter" | "intro_plan" | "intro_skip") => {
    track("intro_left", { via: entry });
    if (to === "/plan") track("plan_started", { entry: "intro" });
    router.push(to);
  };

  return (
    <main id="main" className="brand-intro paper-map" aria-label="내가짠데이 소개 인트로">
      <button type="button" onClick={() => enter("/home", "intro_skip")} className="brand-intro-skip">
        건너뛰기
      </button>

      <div className="brand-intro-stage" aria-hidden>
        {/* 내가 */}
        <section className="bi-col bi-nae">
          <p className="bi-word">
            <span className="wordmark-nae">내가</span>
          </p>
          <ul className="bi-chips">
            {CHIPS.map((c, i) => (
              <li key={c} style={{ "--i": i } as CSSProperties} className="bi-chip">
                {c}
              </li>
            ))}
          </ul>
          <p className="bi-cap">조건은 내가 정하고</p>
        </section>

        {/* 짠 */}
        <section className="bi-col bi-jjan">
          <p className="bi-word">
            <span className="wordmark-jjan bi-stamp-word">짠</span>
          </p>
          <div className="bi-receipt">
            <ol>
              {LINES.map(([k, v], i) => (
                <li key={k} style={{ "--i": i } as CSSProperties} className="bi-line">
                  <span>{k}</span>
                  <span className="bi-leader" />
                  <b className="tabular">{v}</b>
                </li>
              ))}
            </ol>
            <p className="bi-total tabular">
              <span>합계</span>
              <b>42,000원</b>
            </p>
          </div>
          <p className="bi-cap">예산 안에서 짠!</p>
        </section>

        {/* 데이 */}
        <section className="bi-col bi-day">
          <p className="bi-word">
            <span className="wordmark-day">데이</span>
          </p>
          <ol className="bi-timeline">
            {DAY.map(([t, k], i) => (
              <li key={t} style={{ "--i": i } as CSSProperties} className="bi-stop">
                <span className="bi-dot" />
                <time className="tabular">{t}</time>
                <span>{k}</span>
              </li>
            ))}
          </ol>
          <p className="bi-left tabular">
            남은 돈 <b>8,000원</b>
          </p>
        </section>
      </div>

      <div className="brand-intro-end">
        <h1>
          <Wordmark size="lg" />
        </h1>
        <p className="bi-tagline">얼마 쓸지만 정하세요. 하루는 짠이가 짜 볼게요.</p>
        {/* 세 낱말의 뜻: 애니메이션을 못 본 사람(모션 최소화 · 건너뛴 뒤 돌아온 사람)도 이름을 읽고 간다 */}
        <dl className="bi-meaning">
          <div>
            <dt>내가</dt>
            <dd>지역 · 인원 · 예산 · 목적은 내가 정하고</dd>
          </div>
          <div>
            <dt>짠</dt>
            <dd>짠이가 예산 안에서 맞춰 짜고</dd>
          </div>
          <div>
            <dt>데이</dt>
            <dd>먹고 · 걷고 · 노는 하루가 영수증 한 장으로</dd>
          </div>
        </dl>
        <div className="bi-cta">
          <Link
            ref={enterRef}
            href="/home"
            onClick={(e) => {
              e.preventDefault();
              enter("/home", "intro_enter");
            }}
            className="bi-enter"
          >
            입장하기 <ArrowRight aria-hidden className="size-5" />
          </Link>
          <Link
            href="/plan"
            onClick={(e) => {
              e.preventDefault();
              enter("/plan", "intro_plan");
            }}
            className="bi-plan"
          >
            내 하루 바로 짜기
          </Link>
        </div>
      </div>
    </main>
  );
}
