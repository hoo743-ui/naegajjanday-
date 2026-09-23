import { BrandIntro } from "@/components/landing/BrandIntro";
import { Differentiators } from "@/components/landing/Differentiators";
import { FinalCta } from "@/components/landing/FinalCta";
import { HERO_INTRO_GATE, Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { KoreaDay } from "@/components/landing/KoreaDay";
import { PurposeCards } from "@/components/landing/PurposeCards";
import { BannerStrip } from "@/components/layout/BannerStrip";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { TabBar } from "@/components/layout/TabBar";

/**
 * 랜딩 = 한 번 써 보는 하루 (docs/31 · docs/32): 히어로(오늘 쓸 돈 → 오늘의 하루 → 영수증, 첫 방문엔 그 순서로 놓인다) →
 * 그 하루가 일어나는 곳 → 예산 → 영수증 → 코스 → 무엇이 다른가 → 어떤 약속 → 나의 하루. 장면 사이는 경로의 점선으로 잇는다.
 */
export default function LandingPage() {
  return (
    <>
      {/* 첫 페인트 전에 브랜드 인트로(내가 → 짠 → 데이)를 틀지 정한다 (이번 세션에 봤음 · 모션 최소화 · 자동화 브라우저면 건너뜀, docs/38) */}
      <script dangerouslySetInnerHTML={{ __html: HERO_INTRO_GATE }} />
      <BrandIntro />
      <SiteHeader overlay />
      <main id="main">
        <Hero />
        <BannerStrip placement="home" />
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
