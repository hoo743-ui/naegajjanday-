import { Suspense } from "react";
import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { JjaniLoader } from "@/components/mascot/JjaniLoader";
import { PlanWizard } from "@/components/plan/PlanWizard";

export const metadata: Metadata = {
  title: "코스 짜기",
  description: "지역, 목적, 인원과 예산, 취향. 네 가지만 알려 주면 짠이가 예산 안에서 하루 코스를 짜 드려요.",
};

export default function PlanPage() {
  return (
    <PageShell tinted footer={false}>
      {/* useSearchParams 를 쓰는 클라이언트 컴포넌트는 Suspense 경계가 필요하다 */}
      <Suspense fallback={<JjaniLoader />}>
        <PlanWizard />
      </Suspense>
    </PageShell>
  );
}
