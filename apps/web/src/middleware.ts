// Next.js 는 src/middleware.ts 만 인식한다. 로직은 lib/auth/middleware.ts 에 있다.
import type { NextRequest } from "next/server";
import { authMiddleware } from "@/lib/auth/middleware";

export function middleware(request: NextRequest) {
  return authMiddleware(request);
}

export const config = {
  matcher: ["/my/:path*", "/admin/:path*"],
};
