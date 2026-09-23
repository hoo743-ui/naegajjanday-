"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { Wordmark } from "@/components/brand/Wordmark";

/** 전체 길이(ms): globals.css `.brand-intro` 의 퇴장(3.25s 시작 · 0.4s)과 같다 */
const INTRO_MS = 3650;

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
 * 첫 방문의 브랜드 인트로 (약 3.5초, 한 세션에 한 번 · docs/38): 이름을 세 번에 나눠 보여 준다.
 *   내가 — 조건 칩(홍대 · 2명 · 50,000원 · 데이트)이 손으로 고른 듯 톡톡 놓인다
 *   짠   — 도장이 찍히고, 영수증이 한 줄씩 인쇄되고, 합계가 나온다
 *   데이 — 영수증이 하루의 시간표로 펼쳐지고, "남은 돈 8,000원" 도장
 * 그다음 세 조각이 워드마크 하나로 모이고, 홈의 세 칸(내가 · 짠 · 데이)으로 이어진다.
 *
 * 시간표는 전부 CSS(globals.css `.brand-intro`)다 → 스크립트가 붙기 전(느린 폰 · 개발 서버)에도 제 시간에 돈다.
 * 틀지 말지는 첫 페인트 전의 게이트(Hero.tsx HERO_INTRO_GATE)가 html[data-intro=play] 로 정한다.
 * 이 컴포넌트는 끝났을 때 · 건너뛰기를 눌렀을 때 그 표식을 지워 덮개를 걷는 일만 한다.
 */
export function BrandIntro() {
  const [done, setDone] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    if (root.getAttribute("data-intro") !== "play") return;
    const t = window.setTimeout(() => finish(), INTRO_MS);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "Enter" || e.key === " ") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
      root.removeAttribute("data-intro"); // 다른 화면에 갔다 돌아오면 다시 틀지 않는다
    };
  }, []);

  function finish() {
    document.documentElement.removeAttribute("data-intro");
    setDone(true);
  }

  if (done) return null;
  return (
    <div className="brand-intro paper-map" role="dialog" aria-modal="true" aria-label="내가짠데이 소개">
      <button type="button" onClick={finish} className="brand-intro-skip">
        건너뛰기
      </button>

      <div className="brand-intro-stage">
        {/* 내가 */}
        <section className="bi-col bi-nae" aria-label="내가: 조건을 정해요">
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
        <section className="bi-col bi-jjan" aria-label="짠: 예산 안에서 맞춰요">
          <p className="bi-word">
            <span className="wordmark-jjan bi-stamp-word">짠</span>
          </p>
          <div className="bi-receipt">
            <ol>
              {LINES.map(([k, v], i) => (
                <li key={k} style={{ "--i": i } as CSSProperties} className="bi-line">
                  <span>{k}</span>
                  <span aria-hidden className="bi-leader" />
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
        <section className="bi-col bi-day" aria-label="데이: 하루가 나와요">
          <p className="bi-word">
            <span className="wordmark-day">데이</span>
          </p>
          <ol className="bi-timeline">
            {DAY.map(([t, k], i) => (
              <li key={t} style={{ "--i": i } as CSSProperties} className="bi-stop">
                <span aria-hidden className="bi-dot" />
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
        <Wordmark size="lg" />
        <p>얼마 쓸지만 정하세요. 하루는 짠이가 짜 볼게요.</p>
      </div>
    </div>
  );
}
