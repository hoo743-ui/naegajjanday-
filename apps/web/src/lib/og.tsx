/**
 * OG 이미지 공용 조각 (next/og · satori).
 * satori 는 자식이 둘 이상인 요소에 display:flex 를 요구하고, 한글을 그리려면 글꼴 파일을 직접 넘겨야 한다.
 * 글꼴은 서비스와 같은 SUIT(@sun-typeface/suit)의 정적 OTF 를 읽는다 → 외부 네트워크 없이 빌드·렌더된다 (docs/35).
 */
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const OG_SIZE = { width: 1200, height: 630 };

const FONT_DIR = join(process.cwd(), "node_modules", "@sun-typeface", "suit", "fonts", "static", "otf");

export async function loadOgFonts() {
  const [bold, regular] = await Promise.all([
    readFile(join(FONT_DIR, "SUIT-ExtraBold.otf")),
    readFile(join(FONT_DIR, "SUIT-Medium.otf")),
  ]);
  return [
    { name: "SUIT", data: bold, weight: 800 as const, style: "normal" as const },
    { name: "SUIT", data: regular, weight: 500 as const, style: "normal" as const },
  ];
}

/** satori 는 `background` 단축 속성 안의 단색을 이미지로 해석해 실패한다 → 색과 그라디언트를 나눠 준다 */
export const OG_BACKGROUND = {
  backgroundColor: "#ffffff",
  backgroundImage:
    "radial-gradient(circle at 0% 0%, #dce8ff 0%, rgba(220,232,255,0) 55%), radial-gradient(circle at 100% 10%, #ffe0ec 0%, rgba(255,224,236,0) 55%), radial-gradient(circle at 50% 100%, #eee8ff 0%, rgba(238,232,255,0) 60%)",
};

/** 짠이 — 머리에 지도 핀을 꽂은 금화 (OG 용 단순화 버전) */
export function OgJjani({ size = 200 }: { size?: number }) {
  const pin = size * 0.3;
  return (
    <div style={{ display: "flex", position: "relative", width: size, height: size * 1.12 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "absolute",
          left: 0,
          top: size * 0.12,
          width: size,
          height: size,
          borderRadius: size,
          background: "linear-gradient(135deg, #ffd873 0%, #f5b93a 55%, #e29a14 100%)",
          border: `${Math.round(size * 0.045)}px solid #e29a14`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: size * 0.2, marginTop: -size * 0.04 }}>
          <div style={{ width: size * 0.075, height: size * 0.1, borderRadius: size, background: "#14213d" }} />
          <div style={{ width: size * 0.075, height: size * 0.1, borderRadius: size, background: "#14213d" }} />
        </div>
        <div
          style={{
            position: "absolute",
            top: size * 0.56,
            left: size * 0.4,
            width: size * 0.2,
            height: size * 0.1,
            borderBottom: `${Math.round(size * 0.035)}px solid #14213d`,
            borderRadius: `0 0 ${size}px ${size}px`,
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "absolute",
          left: size / 2 - pin / 2,
          top: 0,
          width: pin,
          height: pin,
          borderRadius: `${pin}px ${pin}px ${pin}px 0`,
          transform: "rotate(-45deg)",
          background: "#2f6bea",
        }}
      >
        <div style={{ width: pin * 0.36, height: pin * 0.36, borderRadius: pin, background: "#ffffff" }} />
      </div>
    </div>
  );
}

/**
 * 워드마크 "내가 · 짠 · 데이"를 satori 용 인라인 스타일로 (components/brand/Wordmark.tsx 와 같은 모양):
 * 테두리 칩 "내가" · 기울어 찍힌 토마토 도장 "짠" · 아래로 점선과 점 셋이 이어지는 "데이".
 */
export function OgWordmark({ size = 34 }: { size?: number }) {
  const ink = "#10192e";
  const tomato = "#d63f28";
  const dot = size * 0.16;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.12, fontSize: size, fontWeight: 800, color: ink, letterSpacing: -size * 0.03, lineHeight: 1 }}>
      <div style={{ display: "flex", fontSize: size * 0.78, border: `${size * 0.06}px solid ${ink}`, borderRadius: size * 0.22, padding: `${size * 0.08}px ${size * 0.16}px ${size * 0.1}px`, background: "#fffdf7" }}>내가</div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: size * 1.18, height: size * 1.18, borderRadius: size * 0.3, background: tomato, color: "#ffffff", fontSize: size * 0.92, transform: "rotate(-6deg)" }}>짠</div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "stretch" }}>
        <div style={{ display: "flex" }}>데이</div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: size * 0.1, height: dot, position: "relative" }}>
          <div style={{ display: "flex", position: "absolute", left: dot / 2, right: dot / 2, top: dot / 2 - 1, borderTop: `2px dashed ${ink}` }} />
          <div style={{ display: "flex", width: dot, height: dot, borderRadius: dot, background: ink }} />
          <div style={{ display: "flex", width: dot, height: dot, borderRadius: dot, background: ink }} />
          <div style={{ display: "flex", width: dot, height: dot, borderRadius: dot, background: tomato }} />
        </div>
      </div>
    </div>
  );
}

export function OgBrand() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <OgJjani size={46} />
      <OgWordmark size={34} />
    </div>
  );
}
