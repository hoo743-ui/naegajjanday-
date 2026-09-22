"use client";

import Image from "next/image";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { PurposeIcon } from "@/components/PurposeIcon";
import { Skeleton } from "@/components/ui/skeleton";
import { track } from "@/lib/analytics";
import { usePurposes } from "@/lib/api/hooks";
import { wonCompact } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ChapterMark } from "./ChapterMark";

/**
 * 목적마다 그 하루가 어울리는 한국의 공간 (한국관광공사 사진). 사진이 없는 새 목적은 아이콘 타일로 떨어진다.
 * 한옥 골목 → 데이트, 바닷가 → 여행, 궁궐 → 가족 나들이, 시장 → 친구들, 성수의 골목 → 혼자.
 */
const PHOTOS: Record<string, { src: string; alt: string; place: string }> = {
  date: { src: "/images/story/ikseon-hanok.jpg", alt: "익선동 한옥 골목의 가게", place: "익선동 한옥거리" },
  travel: { src: "/images/story/haeundae.jpg", alt: "해운대 해수욕장과 해안의 빌딩", place: "해운대" },
  family: { src: "/images/story/deoksugung.jpg", alt: "덕수궁의 넓은 마당", place: "덕수궁" },
  friends: { src: "/images/story/mangwon-market.jpg", alt: "망원시장의 골목", place: "망원시장" },
  solo: { src: "/images/story/seongsu-street.jpg", alt: "성수동의 골목길", place: "성수동" },
};

/**
 * 장면 04 — 오늘은 어떤 약속인가요. 목록은 GET /meta/purposes 에서 온다(목적이 늘면 칸도 늘어난다).
 * 첫 목적은 크게, 나머지는 작게 — 같은 크기의 카드 다섯 장을 늘어놓지 않는다. 글자는 사진 위가 아니라 사진 아래에.
 */
export function PurposeCards() {
  const purposes = usePurposes();
  const reduced = useReducedMotion();

  return (
    <section id="purposes" className="scroll-mt-20 bg-paper-2 py-[clamp(72px,10vw,140px)]">
      <div className="wrap">
        <ChapterMark n="04" label="어떤 약속이든" />
        <div className="mt-12 flex flex-wrap items-end justify-between gap-x-12 gap-y-5">
          <h2 className="font-serif text-[clamp(30px,3.8vw,50px)] leading-[1.22] font-bold tracking-[-0.03em]">오늘은 어떤 약속인가요?</h2>
          <p className="max-w-[440px] text-[16px] leading-[1.75] text-ink-2">
            같은 예산이어도 목적이 다르면 코스가 달라져요. 데이트는 분위기를, 혼밥은 웨이팅 없는 곳을 먼저 봅니다.
          </p>
        </div>

        <div className="mt-12">
          {purposes.isPending ? (
            <div className="grid grid-cols-2 gap-5 lg:grid-cols-4" aria-busy="true" aria-label="목적 불러오는 중">
              {Array.from({ length: 5 }, (_, i) => (
                <Skeleton key={i} className={cn("rounded-[20px]", i === 0 ? "col-span-2 h-[420px] lg:row-span-2 lg:h-auto" : "h-[260px]")} />
              ))}
            </div>
          ) : purposes.isError ? (
            <ErrorState error={purposes.error} onRetry={() => void purposes.refetch()} />
          ) : purposes.data.items.length === 0 ? (
            <EmptyState title="아직 준비된 목적이 없어요" description="곧 채워 둘게요. 그동안 바로 코스를 짜 볼까요?" />
          ) : (
            <ul className="grid grid-cols-2 gap-x-5 gap-y-8 lg:grid-cols-4">
              {purposes.data.items.map((p, i) => {
                const photo = PHOTOS[p.code];
                const lead = i === 0;
                return (
                  <motion.li
                    key={p.code}
                    className={cn(lead && "col-span-2 lg:row-span-2")}
                    initial={reduced ? false : { opacity: 0, y: 18 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "0px 0px 10% 0px" }}
                    transition={{ duration: 0.6, delay: Math.min(i * 0.05, 0.2), ease: [0.16, 1, 0.3, 1] }}
                  >
                    <Link href={`/plan?purpose=${encodeURIComponent(p.code)}`} onClick={() => track("plan_started", { entry: "landing_cta" })} className="group flex h-full flex-col">
                      <span className={cn("photo-edge relative block overflow-hidden rounded-[20px] bg-paper", lead ? "aspect-[4/3] lg:aspect-auto lg:flex-1" : "aspect-[4/3]")}>
                        {photo ? (
                          <Image src={photo.src} alt={photo.alt} fill sizes={lead ? "(max-width: 1024px) 92vw, 560px" : "(max-width: 1024px) 46vw, 270px"} className="object-cover transition-transform duration-700 ease-out group-hover:scale-[1.04]" />
                        ) : (
                          <span className="grid size-full place-items-center text-blue-deep">
                            <PurposeIcon icon={p.icon} className="size-10" />
                          </span>
                        )}
                      </span>
                      <span className="mt-4 flex items-baseline justify-between gap-3">
                        <b className={cn("font-extrabold tracking-tight", lead ? "text-[24px]" : "text-[18px]")}>{p.name}</b>
                        <span className="tabular flex shrink-0 items-center gap-1 text-[13px] font-extrabold text-blue-deep">
                          1인 {wonCompact(p.budget_range.min)}부터
                          <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-1" />
                        </span>
                      </span>
                      {p.description ? <span className={cn("mt-1 text-muted-foreground", lead ? "text-[15px]" : "text-[13.5px]")}>{p.description}</span> : null}
                      {photo ? <span className="mt-1.5 text-[11px] font-medium text-muted-foreground/80">사진 ©한국관광공사 · {photo.place}</span> : null}
                    </Link>
                  </motion.li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
