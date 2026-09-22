import { Suspense } from "react";
import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { LoginCard } from "@/components/login/LoginCard";
import { JjaniLoader } from "@/components/mascot/JjaniLoader";

export const metadata: Metadata = { title: "로그인", robots: { index: false } };

export default function LoginPage() {
  return (
    <PageShell footer={false} className="paper-grain grid place-items-center px-5 py-14">
      <Suspense fallback={<JjaniLoader />}>
        <LoginCard />
      </Suspense>
    </PageShell>
  );
}
