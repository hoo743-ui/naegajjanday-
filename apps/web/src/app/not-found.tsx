import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/layout/PageShell";
import { EmptyState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "길을 잃었어요" };

export default function NotFound() {
  return (
    <PageShell tinted className="grid place-items-center">
      <EmptyState
        mood="think"
        size="lg"
        title="여긴 지도에 없는 곳이에요"
        description="주소가 바뀌었거나 사라진 페이지예요. 짠이랑 다시 출발해 볼까요?"
      >
        <Button asChild variant="brand" size="md">
          <Link href="/plan">코스 짜러 가기</Link>
        </Button>
        <Button asChild variant="soft" size="md">
          <Link href="/">홈으로</Link>
        </Button>
      </EmptyState>
    </PageShell>
  );
}
