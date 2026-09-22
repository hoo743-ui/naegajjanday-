import type { Metadata } from "next";
import { CourseView } from "@/components/course/CourseView";
import { PageShell } from "@/components/layout/PageShell";
import { api } from "@/lib/api/client";

interface PageProps {
  params: Promise<{ id: string }>;
}

/** 공유 링크 미리보기(OG). API 가 죽어 있어도 페이지는 떠야 하므로 실패하면 기본 메타로 떨어진다. */
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const fallback: Metadata = {
    title: "추천 코스",
    description: "예산 안에서 짠 하루 코스를 확인해 보세요.",
    robots: { index: false },
  };
  try {
    // 서버에서 직접 부르므로 hooks.ts 의 정규화를 거치지 않는다 → API 의 og 모양(title·description)만 읽는다.
    const { og } = await api.get<{ og: { title: string; description: string } }>(`/courses/${encodeURIComponent(id)}`, {
      timeoutMs: 3000,
      retryOnUnauthorized: false,
      next: { revalidate: 300 },
    });
    // 미리보기 이미지는 같은 폴더의 opengraph-image.tsx 가 코스 내용으로 그려 자동으로 붙는다.
    return {
      title: og.title,
      description: og.description,
      robots: { index: false }, // 개인 코스는 검색에 노출하지 않는다
      openGraph: { title: og.title, description: og.description, type: "article", url: `/course/${id}` },
      twitter: { card: "summary_large_image", title: og.title, description: og.description },
    };
  } catch {
    return fallback;
  }
}

export default async function CoursePage({ params }: PageProps) {
  const { id } = await params;
  return (
    <PageShell footer={false} header={false} className="bg-soft">
      <CourseView id={id} />
    </PageShell>
  );
}
