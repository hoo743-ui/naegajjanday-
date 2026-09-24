"use client";

import { Suspense, useEffect, useState, type ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { initAnalytics, page } from "@/lib/analytics";
import { recordVisit } from "@/lib/analytics/visit";
import { ApiError } from "@/lib/api/client";
import { AuthProvider } from "@/lib/auth/AuthProvider";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // 4xx 는 다시 해도 같다. 네트워크·5xx 만 한 번 더.
        retry: (count, error) => ApiError.from(error).retryable && count < 1,
      },
      mutations: { retry: false },
    },
  });
}

function PageViews() {
  const pathname = usePathname();
  const search = useSearchParams();
  useEffect(() => {
    page(pathname + (search.size ? `?${search.toString()}` : ""));
  }, [pathname, search]);
  // 우리 DB 에 남는 방문(docs/50) — 쿼리는 빼고 경로만
  useEffect(() => recordVisit(pathname), [pathname]);
  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient);

  useEffect(() => {
    void initAnalytics();
  }, []);

  return (
    <QueryClientProvider client={client}>
      {/* reducedMotion="user": OS 의 '동작 줄이기' 설정이면 Motion 의 transform/layout 애니메이션이 꺼진다 */}
      <MotionConfig reducedMotion="user">
        <TooltipProvider delayDuration={200}>
          <AuthProvider>{children}</AuthProvider>
        </TooltipProvider>
      </MotionConfig>
      <Suspense fallback={null}>
        <PageViews />
      </Suspense>
    </QueryClientProvider>
  );
}
