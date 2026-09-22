import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/layout/PageShell";
import { EmptyState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "길을 잃었어요" };

export default function NotFound() {
  return (
    <PageShell className="paper-grain grid place-items-center">
      {/* 짠이 + 한 문장 + 하나의 행동 (docs/25 §5). 홈은 헤더의 로고가 있다 */}
      <EmptyState mood="think" size="lg" scene="lost" title="앗, 여긴 지도에 없는 곳이에요" description="주소가 바뀌었거나 사라진 페이지예요. 짠이랑 다시 출발해요.">
        <Button asChild variant="brand" size="lg">
          <Link href="/plan">다시 찾기</Link>
        </Button>
      </EmptyState>
    </PageShell>
  );
}
