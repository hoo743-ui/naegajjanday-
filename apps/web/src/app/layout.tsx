import type { Metadata, Viewport } from "next";
import { Jua } from "next/font/google";
import { MockBadge } from "@/components/MockBadge";
import { Providers } from "./providers";
// 본문 서체: Pretendard Variable 셀프호스팅. 한글은 unicode-range 조각(dynamic subset)으로 필요한 글자만 받는다.
// 빌드 시점에 외부 폰트 서버에 의존하지 않는다 → 오프라인·CI 에서도 같은 화면이 나온다.
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./globals.css";

/** 짠이 말풍선 등 브랜드 강조에만 쓰는 둥근 서체. 받지 못하면 본문 서체로 떨어진다. */
const jua = Jua({
  weight: "400",
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jua",
  preload: false,
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "내가짠데이 — 내 예산에 맞게, 내가 짠 데이", template: "%s · 내가짠데이" },
  description: "지역, 인원, 예산만 입력하면 식당, 카페, 놀거리까지 예산 안에서 하루 코스를 짜 주는 지도, 내가짠데이.",
  applicationName: "내가짠데이",
  openGraph: {
    type: "website",
    locale: "ko_KR",
    siteName: "내가짠데이",
    title: "내가짠데이 — 내 예산에 맞게, 내가 짠 데이",
    description: "지역 · 인원 · 예산, 세 가지면 충분합니다. 코스는 짠이가 짤게요.",
  },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#2F6BEA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className={jua.variable}>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[100] focus:rounded-xl focus:bg-white focus:px-4 focus:py-2 focus:font-bold focus:shadow-card"
        >
          본문으로 건너뛰기
        </a>
        <Providers>{children}</Providers>
        <MockBadge />
      </body>
    </html>
  );
}
