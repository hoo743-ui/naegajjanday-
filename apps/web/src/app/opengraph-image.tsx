import { ImageResponse } from "next/og";
import { OG_BACKGROUND, OG_SIZE, OgJjani, loadOgFonts } from "@/lib/og";

export const alt = "내가짠데이 — 내 예산에 맞게, 내가 짠 데이";
export const size = OG_SIZE;
export const contentType = "image/png";

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          width: "100%",
          height: "100%",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 96px",
          ...OG_BACKGROUND,
          fontFamily: "Pretendard",
          color: "#14213d",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 22, maxWidth: 720 }}>
          <div
            style={{
              display: "flex",
              alignSelf: "flex-start",
              padding: "10px 22px",
              borderRadius: 999,
              background: "#eaf1ff",
              color: "#2f6bea",
              fontSize: 26,
              fontWeight: 800,
            }}
          >
            “내 예산에 맞게, 내가 짠 데이.”
          </div>
          <div style={{ display: "flex", flexDirection: "column", fontSize: 76, fontWeight: 800, lineHeight: 1.18, letterSpacing: -3 }}>
            <div style={{ display: "flex" }}>
              내&nbsp;<span style={{ color: "#2f6bea" }}>예산 안에서</span>
            </div>
            <div style={{ display: "flex" }}>오늘 먹고 놀 곳을</div>
            <div style={{ display: "flex" }}>한 번에 짜주는 지도</div>
          </div>
          <div style={{ display: "flex", fontSize: 30, fontWeight: 500, color: "#5f6c87" }}>지역 · 인원 · 예산, 세 가지면 충분해요</div>
        </div>
        <OgJjani size={280} />
      </div>
    ),
    { ...size, fonts: await loadOgFonts() },
  );
}
