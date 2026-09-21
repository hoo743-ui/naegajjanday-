import { ImageResponse } from "next/og";
import { api } from "@/lib/api/client";
import type { Course } from "@/lib/api/types";
import { OG_BACKGROUND, OG_SIZE, OgBrand, OgJjani, loadOgFonts } from "@/lib/og";

export const alt = "내가짠데이 추천 코스";
export const size = OG_SIZE;
export const contentType = "image/png";

interface CourseWire {
  course: Course;
  request: { region: { name: string } | null; purpose: { name: string }; party_size: number; budget_total: number };
}

const won = (n: number) => `${n.toLocaleString("ko-KR")}원`;

/** 공유 링크 미리보기: 받는 사람이 링크를 열기 전에 "얼마로, 어디를" 도는 코스인지 한눈에 본다. */
export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const fonts = await loadOgFonts();
  let data: CourseWire | null = null;
  try {
    data = await api.get<CourseWire>(`/courses/${encodeURIComponent(id)}`, {
      timeoutMs: 3000,
      retryOnUnauthorized: false,
      next: { revalidate: 300 },
    });
  } catch {
    data = null; // API 가 죽어 있어도 기본 카드는 나간다
  }

  const stops = data?.course.stops.slice(0, 5) ?? [];
  const request = data?.request;
  // 결과 화면의 요약 문구("둘이서 42,000원")와 같은 말투
  const PARTY_WORDS: Record<number, string> = { 1: "혼자서", 2: "둘이서", 3: "셋이서", 4: "넷이서" };
  const who = request ? (PARTY_WORDS[request.party_size] ?? `${request.party_size}명이서`) : "";
  const headline = data ? `${who} ${won(data.course.totals.price)}` : "예산 안에서 짠 하루 코스";
  const context = request ? [request.region?.name, request.purpose.name, `예산 ${won(request.budget_total)}`].filter(Boolean).join(" · ") : "내가짠데이";

  // 영수증 — 서비스의 시그니처(docs/19). 링크를 받은 사람이 열기 전에 "무엇에 얼마, 그리고 얼마가 남는지"를 본다.
  const ROLE: Record<string, string> = { MEAL: "식사", CAFE: "카페", DESSERT: "디저트", ATTRACTION: "산책", CULTURE: "문화", ACTIVITY: "놀거리", BAR: "한잔", NIGHTVIEW: "야경" };
  const left = data ? Math.max(0, data.course.totals.budget_left) : 0;
  const teeth = Array.from({ length: 23 }, (_, i) => i);
  const Teeth = ({ at }: { at: "top" | "bottom" }) => (
    <div style={{ display: "flex", position: "absolute", left: 0, right: 0, [at]: -9, justifyContent: "space-between", padding: "0 4px" }}>
      {teeth.map((i) => (
        <div key={i} style={{ display: "flex", width: 18, height: 18, borderRadius: 18, background: "#eef2fb" }} />
      ))}
    </div>
  );

  return new ImageResponse(
    (
      <div style={{ display: "flex", width: "100%", height: "100%", padding: "56px 72px", gap: 56, ...OG_BACKGROUND, fontFamily: "Pretendard", color: "#14213d" }}>
        {/* 왼쪽: 한 줄 요약 */}
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", flex: 1 }}>
          <OgBrand />
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", fontSize: 30, fontWeight: 500, color: "#5f6c87" }}>{context}</div>
            <div style={{ display: "flex", fontSize: 84, fontWeight: 800, letterSpacing: -4, lineHeight: 1.1 }}>{headline}</div>
            {data ? (
              <div style={{ display: "flex", fontSize: 40, fontWeight: 800, color: "#6b4700" }}>
                {left > 0 ? `${won(left)} 남아요` : "예산을 꽉 채웠어요"}
              </div>
            ) : null}
          </div>
          <OgJjani size={150} />
        </div>

        {/* 오른쪽: 영수증 */}
        <div style={{ display: "flex", position: "relative", flexDirection: "column", width: 440, padding: "40px 36px", background: "#fffdf7", boxShadow: "0 24px 60px rgba(47,80,160,.2)" }}>
          <Teeth at="top" />
          <div style={{ display: "flex", justifyContent: "center", fontSize: 26, fontWeight: 800 }}>내가짠데이</div>
          <div style={{ display: "flex", margin: "18px 0", borderTop: "3px dashed rgba(20,33,61,.22)" }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 14, flex: 1 }}>
            {stops.map((stop) => (
              <div key={stop.position} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, fontSize: 25 }}>
                <div style={{ display: "flex", gap: 10, fontWeight: 800, whiteSpace: "nowrap", overflow: "hidden" }}>
                  <div style={{ display: "flex", flexShrink: 0, color: "#5f6c87", fontWeight: 500 }}>{ROLE[stop.role] ?? "코스"}</div>
                  {stop.place.name.length > 8 ? `${stop.place.name.slice(0, 7)}…` : stop.place.name}
                </div>
                <div style={{ display: "flex", flexShrink: 0, fontWeight: 800, whiteSpace: "nowrap" }}>{stop.est_price === 0 ? "무료" : won(stop.est_price)}</div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", margin: "18px 0", borderTop: "3px dashed rgba(20,33,61,.22)" }} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 26, fontWeight: 800 }}>
            <div style={{ display: "flex", color: "#5f6c87", fontWeight: 500 }}>합계</div>
            {data ? won(data.course.totals.price) : "-"}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16, padding: "14px 18px", borderRadius: 18, background: "#fff3d6", color: "#6b4700", fontSize: 24, fontWeight: 800 }}>
            <div style={{ display: "flex" }}>남은 돈</div>
            <div style={{ display: "flex", fontSize: 34 }}>{won(left)}</div>
          </div>
          <Teeth at="bottom" />
        </div>
      </div>
    ),
    { ...size, fonts },
  );
}
