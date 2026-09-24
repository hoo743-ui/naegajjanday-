import type { Metadata } from "next";
import { BrandIntro } from "@/components/landing/BrandIntro";
import { MARK_ENTERED } from "@/lib/entry";

export const metadata: Metadata = {
  title: "내가 · 짠 · 데이",
  description: "내가 정하면, 짠이가 예산 안에서, 하루를 짜 드려요. 얼마 쓸지만 정하세요.",
};

/** 첫 진입 브랜드 인트로 (docs/40). 처음 온 사람은 "/" 에서 여기로 온다. 소개 페이지에서 다시 볼 수 있다 */
export default function IntroPage() {
  return (
    <>
      {/* 인트로를 본 것 자체가 입장이다 — 스크립트가 붙기 전에 "입장하기"를 눌러도 다음부터는 바로 홈 */}
      <script dangerouslySetInnerHTML={{ __html: MARK_ENTERED }} />
      <BrandIntro />
    </>
  );
}
