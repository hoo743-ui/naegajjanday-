import type { Metadata, Viewport } from "next";
import { Hahmlet } from "next/font/google";
import localFont from "next/font/local";
import { MockBadge } from "@/components/MockBadge";
import { Providers } from "./providers";
import "./globals.css";

/*
 * 서체는 둘뿐이다 (docs/35 · 최종 폰트 체계):
 *   SUIT Variable — 정보 · 기능 · 신뢰: 메뉴 · 버튼 · 입력 · 칩 · 본문 · 장소 정보 · 가격 · 예산 · 영수증 숫자
 *   Hahmlet       — 감성 · 브랜드 · 기억: 히어로 · 섹션 제목 · 브랜드 한 줄 · 로고 · 영수증 머리
 * SUIT 는 저장소 안에서 셀프호스팅(빌드가 외부 폰트 서버에 기대지 않는다). OFL-1.1, @sun-typeface/suit.
 */
const suit = localFont({
  src: "../../node_modules/@sun-typeface/suit/fonts/variable/woff2/SUIT-Variable.woff2",
  weight: "100 900",
  display: "swap",
  variable: "--font-suit",
});

/** 제목에만 쓰는 세리프. 가변 굵기 하나로 600 · 700 을 쓰고, 한글은 unicode-range 조각으로 쓰는 글자만 받는다. */
const serif = Hahmlet({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-hahmlet",
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
  themeColor: "#FBF8F2",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning: 랜딩의 인트로 게이트 스크립트가 첫 페인트 전에 data-intro 를 단다 (이 요소의 속성만 해당)
    <html lang="ko" className={`${suit.variable} ${serif.variable}`} suppressHydrationWarning data-scroll-behavior="smooth">
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
