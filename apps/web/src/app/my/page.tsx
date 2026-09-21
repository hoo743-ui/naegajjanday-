import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { MyView } from "@/components/my/MyView";

export const metadata: Metadata = { title: "내 코스", robots: { index: false } };

export default function MyPage() {
  return (
    <PageShell className="bg-soft">
      <MyView />
    </PageShell>
  );
}
