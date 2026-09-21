import { Differentiators } from "@/components/landing/Differentiators";
import { FinalCta } from "@/components/landing/FinalCta";
import { Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { PurposeCards } from "@/components/landing/PurposeCards";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";

export default function LandingPage() {
  return (
    <>
      <SiteHeader overlay />
      <main id="main">
        <Hero />
        <HowItWorks />
        <Differentiators />
        <PurposeCards />
        <FinalCta />
      </main>
      <SiteFooter />
    </>
  );
}
