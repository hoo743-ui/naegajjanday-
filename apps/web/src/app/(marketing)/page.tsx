import { ENTRY_GATE } from "@/lib/entry";
import { HomeDashboard } from "@/components/home/HomeDashboard";
import { BannerStrip } from "@/components/layout/BannerStrip";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { TabBar } from "@/components/layout/TabBar";

/**
 * 서비스 홈 (docs/40): 설명하는 곳이 아니라 시작하는 곳 — 두 갈래(짜 볼래요 · 둘러볼래요) → 빠른 코스 만들기 → 오늘의 둘러보기 → 바로 시작.
 * 처음 온 사람은 첫 페인트 전에 브랜드 인트로(/intro)로 간다. 설명은 소개(/about)에 있다.
 */
export default function HomePage() {
  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: ENTRY_GATE }} />
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
