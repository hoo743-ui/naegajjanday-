import { Suspense } from "react";
import type { Metadata } from "next";
import { ExploreView } from "@/components/explore/ExploreView";
import { PageShell } from "@/components/layout/PageShell";
import { JjaniLoader } from "@/components/mascot/JjaniLoader";

export const metadata: Metadata = {
  title: "둘러보기",
  description: "관광지, 공원, 전시, 축제, 문화공간까지. 예산 코스에 넣을 만한 곳을 둘러보세요.",
};

export default function ExplorePage() {
  return (
    <PageShell>
      {/* useSearchParams 를 쓰는 클라이언트 트리는 Suspense 경계가 필요하다 */}
      <Suspense fallback={<JjaniLoader stages={["갈 만한 곳을 모으는 중…"]} />}>
        <ExploreView />
      </Suspense>
    </PageShell>
  );
}
