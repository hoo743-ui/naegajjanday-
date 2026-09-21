"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/mascot/EmptyState";
import { track } from "@/lib/analytics";
import { ApiError } from "@/lib/api/client";

/** 라우트 에러 바운더리. ApiError 면 code 로, 아니면 일반 오류로 짠이가 안내한다. */
export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
    track("error_shown", { code: ApiError.from(error).code, where: "route_boundary" });
  }, [error]);

  // 렌더링 중 터진 일반 예외는 "다시 시도"가 의미 있으므로 INTERNAL_ERROR 로 본다
  const shown =
    error instanceof ApiError
      ? error
      : new ApiError({ code: "INTERNAL_ERROR", status: 500, title: error.message, traceId: error.digest });

  return (
    <main id="main" className="bg-hero grid min-h-dvh place-items-center">
      <ErrorState error={shown} onRetry={reset} size="lg" />
    </main>
  );
}
