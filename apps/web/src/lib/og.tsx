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

export function OgBrand() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 34, fontWeight: 800, color: "#14213d" }}>
      <OgJjani size={46} />
      내가짠데이
    </div>
  );
}
