"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { PurposeIcon } from "@/components/PurposeIcon";
import { Skeleton } from "@/components/ui/skeleton";
import { track } from "@/lib/analytics";
import { usePurposes } from "@/lib/api/hooks";
import { wonCompact } from "@/lib/format";

/** 목적 카드 — 목록은 GET /meta/purposes 에서 온다. 목적이 추가되면 카드도 알아서 늘어난다. */
export function PurposeCards() {
  const purposes = usePurposes();
  const reduced = useReducedMotion();

  return (
    <section id="purposes" className="scroll-mt-20 py-20 lg:py-28">
      <div className="wrap">
        <div className="text-center">
          <span className="inline-flex rounded-full bg-blue-soft px-3.5 py-2 text-sm font-extrabold text-blue-deep">어떤 약속이든</span>
          <h2 className="mt-4 mb-4 text-[clamp(29px,4.2vw,50px)] font-extrabold font-serif">오늘은 어떤 약속인가요?</h2>
          <p className="mx-auto max-w-[640px] text-[clamp(16px,1.6vw,19px)] text-muted-foreground">
            같은 예산이어도 목적이 다르면 코스가 달라져요. 데이트는 분위기를, 혼밥은 웨이팅 없는 곳을 먼저 봅니다.
          </p>
        </div>

        <div className="mt-12">
          {purposes.isPending ? (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5" aria-busy="true" aria-label="목적 불러오는 중">
              {Array.from({ length: 5 }, (_, i) => (
                <Skeleton key={i} className="h-[196px] rounded-card" />
              ))}
            </div>
          ) : purposes.isError ? (
            <ErrorState error={purposes.error} onRetry={() => void purposes.refetch()} />
          ) : purposes.data.items.length === 0 ? (
            <EmptyState title="아직 준비된 목적이 없어요" description="곧 채워 둘게요. 그동안 바로 코스를 짜 볼까요?" />
          ) : (
            <ul className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
              {purposes.data.items.map((p, i) => (
                <motion.li
                  key={p.code}
                  initial={reduced ? false : { opacity: 0, y: 24 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.6, delay: i * 0.06, ease: [0.2, 0.8, 0.2, 1] }}
                >
                  <Link
                    href={`/plan?purpose=${encodeURIComponent(p.code)}`}
                    onClick={() => track("plan_started", { entry: "landing_cta" })}
                    className="group flex h-full flex-col rounded-card border border-line bg-white p-5 shadow-soft transition-[transform,box-shadow] duration-300 hover:-translate-y-1.5 hover:-rotate-1 hover:shadow-card sm:p-6"
                  >
                    <span className="bg-grad-soft grid size-12 place-items-center rounded-2xl text-blue-deep">
                      <PurposeIcon icon={p.icon} className="size-6" />
                    </span>
                    <b className="mt-4 text-lg font-extrabold tracking-tight">{p.name}</b>
                    {p.description ? <span className="mt-1 text-sm text-muted-foreground">{p.description}</span> : null}
                    <span className="tabular mt-auto flex items-center justify-between pt-4 text-[13px] font-extrabold text-blue-deep">
                      1인 {wonCompact(p.budget_range.min)}부터
                      <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-1" />
                    </span>
                  </Link>
                </motion.li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
