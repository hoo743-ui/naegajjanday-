import type { Metadata } from "next";
import { AboutName } from "@/components/landing/AboutName";
import { Differentiators } from "@/components/landing/Differentiators";
import { FinalCta } from "@/components/landing/FinalCta";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { KoreaDay } from "@/components/landing/KoreaDay";
import { PurposeCards } from "@/components/landing/PurposeCards";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { TabBar } from "@/components/layout/TabBar";

export const metadata: Metadata = {
  title: "소개",
  description: "내가짠데이는 예산 안에서 하루를 짜 주는 서비스예요. 내가 정하면, 짠이가 예산 안에서, 하루를 짜요.",
};

/**
 * 소개 (docs/40): 예전 랜딩의 설명은 모두 여기로 — 이름의 뜻 → 그 하루가 일어나는 곳 → 예산 · 영수증 · 코스 → 무엇이 다른가 → 어떤 약속 → 시작.
 * 홈은 시작하는 곳, 여기는 읽는 곳.
 */
export default function AboutPage() {
  return (
    <>
      <SiteHeader />
      <main id="main">
        <AboutName />
        <KoreaDay />
        <HowItWorks />
        <Differentiators />
        <PurposeCards />
        <FinalCta />
      </main>
      <SiteFooter />
      <TabBar />
    </>
  );
}
