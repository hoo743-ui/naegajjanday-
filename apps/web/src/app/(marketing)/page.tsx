import { Differentiators } from "@/components/landing/Differentiators";
import { FinalCta } from "@/components/landing/FinalCta";
import { Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { INTRO_GATE, IntroSequence } from "@/components/landing/IntroSequence";
import { KoreaDay } from "@/components/landing/KoreaDay";
import { PurposeCards } from "@/components/landing/PurposeCards";
import { BannerStrip } from "@/components/layout/BannerStrip";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";

/**
 * 랜딩 = 한 장의 긴 영수증 (docs/25 §5): 첫 진입 시퀀스 → 히어로(약속 + 살아 있는 영수증) →
 * 01 과거 × 현재 → 02 예산 → 영수증 → 코스 → 03 무엇이 다른가 → 04 어떤 약속 → 05 나의 하루.
 */
export default function LandingPage() {
  return (
    <>
      {/* 첫 페인트 전에 인트로를 틀지 정한다 (이미 봤음 · 모션 최소화 · 자동화 브라우저면 건너뜀) */}
      <script dangerouslySetInnerHTML={{ __html: INTRO_GATE }} />
      <IntroSequence />
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
    </>
  );
}
