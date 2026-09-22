import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * 글자 계단 토큰(docs/26)을 tailwind-merge 에 "글자 크기"로 알려 준다.
 * 모르면 text-body-lg 를 글자 색으로 보고, 같은 요소의 text-white 를 지워 버린다
 * (파란 버튼의 글자가 검게 찍혔다 — 타이포그래피 재설계 직후 캡처에서 잡았다).
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["display-xl", "display", "h1", "h2", "h3", "body-lg", "body", "body-sm", "caption", "price-lg", "price", "price-sm"] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
