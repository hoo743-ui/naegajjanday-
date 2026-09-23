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
 * 장면 — 오늘은 어떤 약속인가요. 목록은 GET /meta/purposes 에서 온다(목적이 늘면 줄도 는다).
 * 사진 격자(핀터레스트)가 아니라 가게 앞 메뉴판: 목적 ······ 1인 얼마부터. 사진은 줄마다 작게, 글이 주인공이다 (docs/31 §14).
 * 왼쪽에 제목(sticky) 4 : 오른쪽에 메뉴판 8.
 */
export function PurposeCards() {
  const purposes = usePurposes();
  const reduced = useReducedMotion();

  return (
    <section id="purposes" className="scroll-mt-20 py-[clamp(48px,7vw,96px)]">
      <div className="wrap">
        <ChapterMark label="어떤 약속이든" />
        <div className="mt-10 grid gap-x-16 gap-y-10 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
          <div className="lg:sticky lg:top-[calc(var(--header-h)+48px)] lg:self-start">
            <h2 className="font-serif text-display">오늘은 어떤 약속인가요?</h2>
            <p className="mt-5 max-w-[400px] text-body-lg text-ink-2">같은 예산이어도 목적이 다르면 코스가 달라져요.</p>
          </div>

          <div>
            {purposes.isPending ? (
              <div className="grid gap-3" aria-busy="true" aria-label="목적 불러오는 중">
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-[104px] rounded-lg" />
                ))}
              </div>
            ) : purposes.isError ? (
              <ErrorState error={purposes.error} onRetry={() => void purposes.refetch()} />
            ) : purposes.data.items.length === 0 ? (
              <EmptyState title="아직 준비된 목적이 없어요" description="곧 채워 둘게요. 그동안 바로 코스를 짜 볼까요?" />
            ) : (
              <ul className="border-b border-ink/12">
                {purposes.data.items.map((p, i) => {
                  const photo = PHOTOS[p.code];
                  return (
                    <motion.li
                      key={p.code}
                      className="border-t border-ink/12"
                      initial={reduced ? false : { opacity: 0, y: 12 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true, margin: "0px 0px 10% 0px" }}
                      transition={{ duration: 0.5, delay: Math.min(i * 0.04, 0.16), ease: [0.16, 1, 0.3, 1] }}
                    >
                      <Link
                        href={`/plan?purpose=${encodeURIComponent(p.code)}`}
                        onClick={() => track("plan_started", { entry: "landing_cta" })}
                        className="group grid grid-cols-[88px_minmax(0,1fr)] items-center gap-x-5 gap-y-2 py-5 sm:grid-cols-[132px_minmax(0,1fr)_auto] sm:gap-x-7"
                      >
                        <span className="photo-edge relative block aspect-[4/3] overflow-hidden rounded-lg bg-paper-2">
                          {photo ? (
                            <Image src={photo.src} alt={photo.alt} fill sizes="132px" className="object-cover transition-transform duration-700 ease-out group-hover:scale-[1.05]" />
                          ) : (
                            <span className="grid size-full place-items-center text-blue-deep">
                              <PurposeIcon icon={p.icon} className="size-8" />
                            </span>
                          )}
                        </span>
                        <span className="grid gap-0.5">
                          <b className="text-h3 font-bold group-hover:text-blue-deep">{p.name}</b>
                          {p.description ? <span className="text-body-sm text-ink-2">{p.description}</span> : null}
                        </span>
                        {/* 메뉴판의 가격 칸: 오른쪽 끝, 같은 폭의 숫자 */}
                        <span className="tabular col-start-2 flex items-center gap-1 text-body font-bold text-ink sm:col-start-3 sm:justify-self-end">
                          1인 {wonCompact(p.budget_range.min)}부터
                          <ArrowRight aria-hidden className="size-4 text-blue-deep transition-transform group-hover:translate-x-1" />
                        </span>
                      </Link>
                    </motion.li>
                  );
                })}
              </ul>
            )}
            {/* 사진 출처는 줄마다가 아니라 목록 끝에 한 번 (docs/33) — 공공누리 조건의 출처 표시 */}
            {purposes.data?.items.some((p) => PHOTOS[p.code]) ? (
              <p className="mt-3 text-caption text-muted-foreground">사진 ©한국관광공사 · {purposes.data.items.map((p) => PHOTOS[p.code]?.place).filter(Boolean).join(" · ")}</p>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
