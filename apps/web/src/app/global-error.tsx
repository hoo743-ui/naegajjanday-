"use client";

/** 루트 레이아웃까지 깨졌을 때의 최후 방어선. Provider·폰트·Tailwind 에 기대지 않는다. */
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="ko">
      <body
        style={{
          margin: 0,
          minHeight: "100dvh",
          display: "grid",
          placeItems: "center",
          fontFamily: '"Apple SD Gothic Neo","Malgun Gothic",sans-serif',
          color: "#14213D",
          background: "#F5F8FE",
          textAlign: "center",
          padding: 24,
        }}
      >
        <div>
          <svg viewBox="0 0 200 220" width="120" height="132" role="img" aria-label="미안해하는 표정의 짠이">
            <ellipse cx="100" cy="207" rx="52" ry="8" fill="#14213D" opacity=".12" />
            <circle cx="100" cy="112" r="80" fill="#F5B93A" stroke="#E29A14" strokeWidth="6" />
            <g transform="rotate(-8 100 59)">
              <path d="M100 4c-13 0-22 9-22 21 0 16 22 34 22 34s22-18 22-34c0-12-9-21-22-21z" fill="#2F6BEA" />
              <circle cx="100" cy="25" r="7.5" fill="#fff" />
            </g>
            <g fill="none" stroke="#14213D" strokeWidth="3.5" strokeLinecap="round">
              <path d="M65 101L87 93" />
              <path d="M113 93L135 101" />
            </g>
            <circle cx="76" cy="116" r="7" fill="#14213D" />
            <circle cx="124" cy="116" r="7" fill="#14213D" />
            <path d="M90 133Q100 140 110 133" fill="none" stroke="#14213D" strokeWidth="4" strokeLinecap="round" />
          </svg>
          <h1 style={{ fontSize: 22, margin: "12px 0 6px" }}>앗, 짠이가 실수했어요</h1>
          <p style={{ color: "#5F6C87", margin: "0 0 20px" }}>문제가 생겼어요. 잠시 뒤에 다시 시도해 주세요.</p>
          <button
            type="button"
            onClick={reset}
            style={{
              height: 48,
              padding: "0 24px",
              border: 0,
              borderRadius: 14,
              background: "#2F6BEA",
              color: "#fff",
              fontWeight: 800,
              fontSize: 16,
              cursor: "pointer",
            }}
          >
            다시 시도
          </button>
        </div>
      </body>
    </html>
  );
}
