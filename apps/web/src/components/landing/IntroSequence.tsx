"use client";

import { useEffect, useState } from "react";
import { DAY_LINE_PATH, DAY_LINE_STOPS, DAY_LINE_TEAR, tearHoles } from "@/components/brand/day-line";
import { Jjani } from "@/components/mascot/Jjani";

/** 한 번 본 사람에게는 다시 틀지 않는다 (탭을 닫기 전까지) */
export const INTRO_KEY = "jj-intro-seen";
/** CSS 시간표의 끝(초). globals.css 의 .jj-intro 애니메이션과 같은 값 */
const END_MS = 3900;

/**
 * 인라인 스크립트: 첫 페인트 전에 인트로를 건너뛸지 정한다 → 건너뛸 사람에게는 한 프레임도 보이지 않는다.
 * 건너뛰는 경우: 이미 봤음 · 모션 최소화 · 자동화 브라우저(검증 · E2E — 가려진 버튼을 누르지 못한다) · ?intro=0
 */
export const INTRO_GATE = `(function(){try{var d=document.documentElement;var skip=sessionStorage.getItem("${INTRO_KEY}")||navigator.webdriver||matchMedia("(prefers-reduced-motion: reduce)").matches||/[?&]intro=0/.test(location.search);if(skip){d.setAttribute("data-intro","skip")}else{sessionStorage.setItem("${INTRO_KEY}","1")}}catch(e){document.documentElement.setAttribute("data-intro","skip")}})();`;

const RECEIPT = { x: 912, w: 236, top: DAY_LINE_TEAR.y + 6, bottom: 462 };
/** 한 번의 방문(자바스크립트가 살아 있는 동안)에 한 번만: 다른 화면에 갔다가 로고로 돌아와도 다시 틀지 않는다 */
let playedThisVisit = false;

/**
 * 첫 진입 시퀀스 (docs/25 §4, 약 3.9초): 종이 → 금빛 점 → 동전처럼 구르며 지나간 자리에 선 → 그 선이 지붕선 · 스카이라인 ·
 * 경로가 되고 → 절취선에서 영수증이 출력 → "내가 짠 하루가, 오늘의 영수증이 됩니다." → 짠이 → 랜딩이 드러난다.
 * 절제: 웅장한 음악 · 3D · 사진 없이 선 하나. 아무 입력(클릭 · 키 · 스크롤 · 터치)에도 바로 걷힌다.
 * 모든 움직임은 CSS/SVG 시간표라 자바스크립트가 늦어도 제때 재생되고, 끝나면 CSS 가 스스로 걷는다(JS 는 정리만 한다).
 */
export function IntroSequence() {
  const [gone, setGone] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    // 인라인 스크립트는 처음 문서를 받을 때만 돈다 → 화면 전환으로 들어온 경우는 여기서 같은 규칙을 다시 본다
    const skip =
      document.documentElement.getAttribute("data-intro") === "skip" ||
      playedThisVisit ||
      navigator.webdriver ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    playedThisVisit = true;
    if (skip) {
      setGone(true);
      return;
    }
    try {
      sessionStorage.setItem(INTRO_KEY, "1");
    } catch {
      // 저장소를 못 쓰는 환경: 이번 방문 동안만 기억한다
    }
    let leaveTimer = 0;
    const leave = () => {
      setLeaving(true);
      window.clearTimeout(leaveTimer);
      leaveTimer = window.setTimeout(() => setGone(true), 280);
      remove();
    };
    const events = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
    const remove = () => events.forEach((e) => window.removeEventListener(e, leave));
    events.forEach((e) => window.addEventListener(e, leave, { passive: true, once: true }));
    const endTimer = window.setTimeout(() => setGone(true), END_MS + 80);
    return () => {
      remove();
      window.clearTimeout(endTimer);
      window.clearTimeout(leaveTimer);
    };
  }, []);

  if (gone) return null;

  const holes = tearHoles();
  return (
    <div aria-hidden className={`jj-intro paper-grain${leaving ? " is-leaving" : ""}`}>
      <div className="jj-intro-stage">
        <svg viewBox="0 0 1200 520" className="block w-full overflow-visible" role="presentation">
          <defs>
            <clipPath id="jj-intro-print">
              <rect x={RECEIPT.x - 20} y={RECEIPT.top} width={RECEIPT.w + 40} height={0}>
                <animate attributeName="height" from="0" to={RECEIPT.bottom - RECEIPT.top + 30} begin="2.16s" dur="0.62s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.16 1 0.3 1" />
              </rect>
            </clipPath>
            <filter id="jj-intro-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="14" stdDeviation="14" floodColor="#483618" floodOpacity="0.14" />
            </filter>
          </defs>

          {/* 선: 지붕선 → 스카이라인 → 경로 */}
          <path d={DAY_LINE_PATH} pathLength={1} className="jj-intro-line" fill="none" stroke="#10192E" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
          {DAY_LINE_STOPS.map(([x, y], i) => (
            <circle key={x} cx={x} cy={y} r={5.5} className="jj-intro-stop" style={{ animationDelay: `${1.62 + i * 0.16}s` }} fill="#2A5BD7" stroke="#fff" strokeWidth={2} />
          ))}
          {/* 절취선 */}
          {holes.map((x, i) => (
            <circle key={x} cx={x} cy={DAY_LINE_TEAR.y} r={2.4} className="jj-intro-hole" style={{ animationDelay: `${1.98 + i * 0.012}s` }} fill="#10192E" />
          ))}

          {/* 절취선에서 출력되는 영수증 */}
          <g clipPath="url(#jj-intro-print)">
            <g filter="url(#jj-intro-shadow)">
              <path
                d={`M ${RECEIPT.x} ${RECEIPT.top} H ${RECEIPT.x + RECEIPT.w} V ${RECEIPT.bottom} ${Array.from({ length: Math.round(RECEIPT.w / 20) }, (_, i) => `L ${RECEIPT.x + RECEIPT.w - (i + 0.5) * (RECEIPT.w / Math.round(RECEIPT.w / 20))} ${RECEIPT.bottom + 9} L ${RECEIPT.x + RECEIPT.w - (i + 1) * (RECEIPT.w / Math.round(RECEIPT.w / 20))} ${RECEIPT.bottom}`).join(" ")} Z`}
                fill="#FFFDF7"
              />
            </g>
            <text x={RECEIPT.x + RECEIPT.w / 2} y={RECEIPT.top + 44} textAnchor="middle" className="jj-intro-wordmark">
              내가짠데이
            </text>
            <line x1={RECEIPT.x + 18} x2={RECEIPT.x + RECEIPT.w - 18} y1={RECEIPT.top + 64} y2={RECEIPT.top + 64} stroke="#10192E" strokeOpacity={0.22} strokeWidth={1.5} strokeDasharray="5 4" />
            {[
              ["식사", "22,000원"],
              ["카페", "6,000원"],
              ["산책", "무료"],
              ["보드게임", "14,000원"],
            ].map(([k, v], i) => (
              <g key={k} className="jj-intro-row" style={{ animationDelay: `${2.3 + i * 0.07}s` }}>
                <text x={RECEIPT.x + 20} y={RECEIPT.top + 96 + i * 30} className="jj-intro-item">
                  {k}
                </text>
                <text x={RECEIPT.x + RECEIPT.w - 20} y={RECEIPT.top + 96 + i * 30} textAnchor="end" className="jj-intro-item is-price">
                  {v}
                </text>
              </g>
            ))}
            <rect x={RECEIPT.x + 16} y={RECEIPT.top + 206} width={RECEIPT.w - 32} height={78} rx={14} fill="#FFF3D6" className="jj-intro-row" style={{ animationDelay: "2.62s" }} />
            <text x={RECEIPT.x + 32} y={RECEIPT.top + 232} className="jj-intro-left-label jj-intro-row" style={{ animationDelay: "2.62s" }}>
              남은 돈
            </text>
            <text x={RECEIPT.x + 32} y={RECEIPT.top + 270} className="jj-intro-left jj-intro-row" style={{ animationDelay: "2.62s" }}>
              8,000원
            </text>
          </g>

          {/* 금빛 점 → 구르는 동전: 화면 가운데에서 태어나 선의 시작으로 가고, 선을 그리며 끝까지 간다 */}
          <g className="jj-intro-coin">
            <animateMotion path="M 600 190 L 30 190" begin="0.34s" dur="0.52s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.65 0 0.35 1" />
            <animateMotion path={DAY_LINE_PATH} begin="0.86s" dur="1.1s" fill="freeze" />
            <g>
              <animateTransform attributeName="transform" type="scale" values="1 1;0.25 1;1 1;0.25 1;1 1" begin="0.34s" dur="0.6s" fill="freeze" />
              <circle r={10} fill="#E9B44C" stroke="#B8842A" strokeWidth={1.6} />
              <circle r={5.2} fill="none" stroke="#B8842A" strokeWidth={1.2} strokeOpacity={0.7} />
            </g>
          </g>
        </svg>

        {/* 짠이: 동전이 사라진 자리에서, 막 나온 영수증을 들여다본다 */}
        <div className="jj-intro-jjani" style={{ left: `calc(${(RECEIPT.x / 1200) * 100}% - clamp(44px, 6vw, 72px))`, top: `${((RECEIPT.top + 120) / 520) * 100}%` }}>
          <Jjani mood="wink" animated={false} decorative className="h-auto w-[clamp(44px,6vw,72px)]" />
        </div>
      </div>

      <p className="jj-intro-copy font-serif">
        내가 짠 하루가,
        <br />
        오늘의 영수증이 됩니다.
      </p>
    </div>
  );
}
