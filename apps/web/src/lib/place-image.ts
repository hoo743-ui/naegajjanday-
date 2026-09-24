import type { ImageRef, PlaceholderKind } from "@/lib/api/types";
import type { Photo } from "@/lib/api/hooks";
import { categoryImageFor } from "@/lib/api/hooks";
import { photoCredit } from "@/lib/photo-credit";

/**
 * 카드의 그림 한 장 (docs/43). 서버가 준 `image` 가 있으면 그대로 쓰고,
 * 없으면(목 데이터 · 이벤트처럼 서버가 아직 안 주는 곳) 같은 순서로 여기서 고른다:
 * 실제 사진 → 분위기 이미지 → 브랜드 그림.
 */
export function resolvePlaceImage(input: {
  image?: ImageRef | null;
  thumbnailUrl?: string | null;
  /** 업종 코드(food.korean …). 분위기 이미지와 그림 종류를 고른다 */
  category?: string | null;
  /** 역할(MEAL · WALK …)이나 둘러보기 유형(park …). 업종 코드보다 그림 종류를 잘 말해 줄 때 */
  kind?: string | null;
  categoryImages?: Record<string, Photo>;
}): ImageRef {
  const examplesOn = process.env.NEXT_PUBLIC_EXAMPLE_PHOTOS !== "off";
  const server = input.image;
  if (server) {
    // 분위기 이미지를 끈 환경이면 그림으로 내린다 (그림 종류는 서버가 업종 코드로 정한 것)
    return server.image_type === "category" && !examplesOn ? placeholder(server.placeholder_kind) : server;
  }
  // 업종 코드가 역할보다 구체적이다(공원은 역할로는 ATTRACTION 이지만 업종으로는 산책)
  const byCategory = toPlaceholderKind(input.category);
  const kind = byCategory !== "sight" || !input.kind ? byCategory : toPlaceholderKind(input.kind);
  if (input.thumbnailUrl) {
    const credit = photoCredit(input.thumbnailUrl);
    return {
      image_type: "actual",
      image_url: input.thumbnailUrl,
      thumbnail_url: input.thumbnailUrl,
      source: credit ? "tourapi" : "upload",
      source_url: null,
      photographer: credit ? "한국관광공사" : null,
      license: credit ? "공공누리 (출처표시)" : null,
      attribution_text: credit,
      is_actual_place_photo: true,
      is_fallback_image: false,
      placeholder_kind: kind,
    };
  }
  const example = examplesOn ? categoryImageFor(input.categoryImages, input.category ?? "") : undefined;
  if (example) {
    return {
      image_type: "category",
      image_url: example.url,
      thumbnail_url: example.thumbnail_url ?? example.url,
      source: example.source ?? "wikimedia",
      source_url: example.page_url,
      photographer: example.author,
      license: example.license,
      attribution_text: example.attribution_text ?? `분위기 이미지 · © ${example.author} · ${example.license}`,
      is_actual_place_photo: false,
      is_fallback_image: true,
      placeholder_kind: kind,
    };
  }
  return placeholder(kind);
}

function placeholder(kind: PlaceholderKind): ImageRef {
  return {
    image_type: "branded-placeholder",
    image_url: null,
    thumbnail_url: null,
    source: "naegajjanday",
    source_url: null,
    photographer: null,
    license: null,
    attribution_text: null,
    is_actual_place_photo: false,
    is_fallback_image: true,
    placeholder_kind: kind,
  };
}

/** 역할(MEAL …) · 둘러보기 유형(park …) · 업종 코드(food.korean …) → 그림 종류. 서버 image_ref.placeholder_kind 와 같은 규칙 */
export function toPlaceholderKind(code: string | null | undefined): PlaceholderKind {
  const c = (code ?? "").toLowerCase();
  if (/^(cafe|dessert)/.test(c)) return "cafe";
  if (/^(food|meal|restaurant)/.test(c)) return "meal";
  if (/^(bar|pub|drink)/.test(c)) return "bar";
  if (/^(nightview|night)/.test(c)) return "night";
  if (/^(attraction\.(park|nature|trail)|walk|park|nature|trail)/.test(c)) return "walk";
  if (/^(activity|festival|culture\.festival|play|event)/.test(c)) return "activity";
  return "sight";
}
