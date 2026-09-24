"use client";

import { useState } from "react";
import Image from "next/image";
import type { ImageRef } from "@/lib/api/types";
import { canOptimize } from "@/lib/photo-credit";
import { cn } from "@/lib/utils";
import { PlacePlaceholder } from "./PlacePlaceholder";

/**
 * 카드의 그림 한 장 (docs/43) — 세 가지를 한 규칙으로 그린다.
 * - actual(그 장소의 사진): 보통 사진 카드. 손대지 않는다(한국관광공사 사진 다수가 공공누리 3유형 = 변경금지).
 *   출처 문구가 있으면 큰 카드에서는 사진 위에, 작은 칸에서는 툴팁으로.
 * - category(분위기 이미지): 작게 "분위기 이미지" 띠 + 작가 · 라이선스. 그 가게 사진처럼 보이지 않게 살짝 가라앉힌다.
 * - branded-placeholder: 종류별 브랜드 그림.
 * 사진을 못 받으면(깨진 주소 · 원본 서버 오류) 빈 상자 대신 그림으로 내려간다.
 * 겉 상자(크기 · 모서리 · photo-edge)는 부르는 쪽이 className 으로 준다.
 */
interface PlacePhotoProps {
  image: ImageRef;
  /** sm = 썸네일 칸(72~80px), lg = 카드 · 시트의 큰 사진 */
  size?: "sm" | "lg";
  className?: string;
  /** next/image sizes */
  sizes: string;
  priority?: boolean;
  /** lg 에서 출처를 사진 위에 적을지 (따로 적는 화면이면 false) */
  showCredit?: boolean;
  imgClassName?: string;
}

export function PlacePhoto({ image, size = "sm", className, sizes, priority, showCredit = true, imgClassName }: PlacePhotoProps) {
  const src = size === "sm" ? (image.thumbnail_url ?? image.image_url) : (image.image_url ?? image.thumbnail_url);
  // 깨진 주소를 기억한다 — 바꾸기로 다른 장소가 오면(주소가 달라지면) 다시 시도한다
  const [brokenSrc, setBrokenSrc] = useState<string | null>(null);
  const broken = brokenSrc !== null && brokenSrc === src;

  if (image.image_type === "branded-placeholder" || !src || broken) {
    return <PlacePlaceholder kind={image.placeholder_kind} size={size} className={className} />;
  }

  const mood = image.image_type === "category";
  const credit = image.attribution_text;
  return (
    <span
      className={cn("relative overflow-hidden", className)}
      title={mood ? `이 장소의 사진이 아니라 같은 종류의 분위기 이미지예요${credit ? ` · ${credit.replace(/^분위기 이미지 · /, "")}` : ""}` : (credit ?? undefined)}
      data-image-type={image.image_type}
    >
      <Image
        src={src}
        alt=""
        fill
        sizes={sizes}
        priority={priority}
        unoptimized={!canOptimize(src)}
        onError={() => setBrokenSrc(src)}
        className={cn("object-cover", mood && "opacity-90 saturate-[.8]", imgClassName)}
      />
      {mood ? (
        size === "sm" ? (
          <span className="absolute inset-x-0 bottom-0 bg-ink/65 py-0.5 text-center text-[10px] leading-tight font-semibold tracking-tight text-white">분위기 이미지</span>
        ) : (
          <>
            <span className="absolute bottom-2 left-2 rounded-md bg-ink/70 px-1.5 py-0.5 text-caption font-semibold text-white">분위기 이미지</span>
            {showCredit && credit ? (
              <a
                href={image.source_url ?? src}
                target="_blank"
                rel="noreferrer"
                className="absolute right-2 bottom-2 z-10 max-w-[60%] truncate rounded-md bg-black/45 px-1.5 py-0.5 text-caption font-medium text-white/95 hover:bg-black/65"
              >
                {credit.replace(/^분위기 이미지 · /, "")}
              </a>
            ) : null}
          </>
        )
      ) : size === "lg" && showCredit && credit ? (
        <span className="absolute right-2 bottom-2 rounded-md bg-black/45 px-1.5 py-0.5 text-caption font-medium text-white/95">{credit}</span>
      ) : null}
    </span>
  );
}
