import type { Metadata } from "next";
import { HomeDashboard } from "@/components/home/HomeDashboard";
import { BannerStrip } from "@/components/layout/BannerStrip";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { TabBar } from "@/components/layout/TabBar";

export const metadata: Metadata = { title: "홈" };

/**
 * 서비스 홈 (docs/40): 설명하는 곳이 아니라 시작하는 곳 — 두 갈래(짜 볼래요 · 둘러볼래요) → 빠른 코스 만들기 → 오늘의 둘러보기 → 바로 시작.
 * 2026-09-24 창업자: 홈페이지 주소(/)에 들어오면 인트로가 먼저 → 인트로가 "/", 이 대시보드는 "/home". 서비스 안의 "홈"은 모두 여기.
 */
export default function HomePage() {
  return (
    <>
      <SiteHeader overlay />
      <main id="main">
        <HomeDashboard />
        <BannerStrip placement="home" />
      </main>
      <SiteFooter />
      <TabBar />
    </>
  );
}
