import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker 이미지는 .next/standalone 만 복사해서 실행한다.
  output: "standalone",
  // 모노레포 루트에 다른 lockfile이 생겨도 추적 루트가 흔들리지 않게 고정한다.
  outputFileTracingRoot: path.join(__dirname),
  // OG 이미지는 요청 때 node_modules 의 SUIT OTF 를 직접 읽는다(lib/og.tsx) → 서버리스 함수 묶음에 넣어 둔다 (docs/37)
  outputFileTracingIncludes: {
    "/course/[id]/opengraph-image": ["./node_modules/@sun-typeface/suit/fonts/static/otf/SUIT-{ExtraBold,Medium}.otf"],
    "/opengraph-image": ["./node_modules/@sun-typeface/suit/fonts/static/otf/SUIT-{ExtraBold,Medium}.otf"],
  },
  reactStrictMode: true,
  poweredByHeader: false,
  images: {
    // 장소 썸네일은 수집 출처(CDN)가 다양하다. 운영에서는 이미지 프록시 도메인 하나로 좁힌다.
    remotePatterns: [{ protocol: "https", hostname: "**" }],
  },
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts", "motion"],
  },
};

export default nextConfig;
