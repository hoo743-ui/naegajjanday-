import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "내가짠데이",
    short_name: "내가짠데이",
    description: "지역 · 인원 · 예산만 알려 주면 예산 안에서 하루 코스를 짜 주는 지도",
    lang: "ko",
    start_url: "/plan",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#2f6bea",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
