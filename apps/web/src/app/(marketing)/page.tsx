import { BrandIntro } from "@/components/landing/BrandIntro";

/**
 * 홈페이지 주소(/) = 브랜드 인트로 (docs/38 · docs/40). 2026-09-24 창업자: "홈페이지에 들어갔을 때 인트로가 먼저".
 * 한 번 봤다고 건너뛰지 않는다 — 들어올 때마다 인트로이고, "입장하기" · "건너뛰기"로 서비스 홈(/home)에 간다.
 * 서비스 안의 "홈" 링크(로고 · 탭 · 푸터)는 모두 /home 이라, 쓰는 중에 인트로로 되돌아오지는 않는다.
 */
export default function IntroHome() {
  return <BrandIntro />;
}
