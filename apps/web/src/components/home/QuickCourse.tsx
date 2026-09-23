"use client";

import { useId, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, MapPin, Minus, Plus } from "lucide-react";
import { BudgetChip } from "@/components/brand/BudgetChip";
import { sampleCourse } from "@/components/brand/sample-course";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { useDebounced, useRegions } from "@/lib/api/hooks";
import type { Region } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const BUDGETS = [
  { value: 30000, hint: "가볍게" },
  { value: 50000, hint: "무난하게" },
  { value: 100000, hint: "넉넉하게" },
];
/** 목적 코드 → 짧은 이름 · 기본 인원 · 최대 인원 */
const PURPOSES = [
  { code: "date", label: "데이트", party: 2, max: 2 },
  { code: "friends", label: "친구", party: 3, max: 8 },
  { code: "solo", label: "혼자", party: 1, max: 1 },
  { code: "family", label: "가족", party: 4, max: 8 },
  { code: "travel", label: "여행", party: 2, max: 8 },
];
const won = (n: number) => `${n.toLocaleString("ko-KR")}원`;

/**
 * 빠른 코스 만들기 (docs/41): 세 줄 — 어디서 · 얼마로 · 누구랑. 영수증은 한 줄 요약(예상 총액 · 남는 돈 · 몇 곳)만,
 * 자세한 영수증은 위저드와 결과 화면이 크게 보여 준다. 버튼은 고른 값을 들고 위저드의 다음 단계로 간다.
 */
export function QuickCourse() {
  const placeId = useId();
  const [placeText, setPlaceText] = useState("");
  const [picked, setPicked] = useState<Region | null>(null);
  const [open, setOpen] = useState(false);
  const [budget, setBudget] = useState(50000);
  const [purpose, setPurpose] = useState(PURPOSES[0]!);
  const [party, setParty] = useState(2);

  const regions = useRegions();
  const hot = useMemo(
    () => [...(regions.data?.items ?? [])].filter((r) => r.level === 3 && r.place_count > 0).sort((a, b) => b.place_count - a.place_count).slice(0, 4),
    [regions.data],
  );
  const query = placeText.trim();
  const asked = useDebounced(query, 200);
  const found = useRegions(asked.length >= 2 && picked?.name !== placeText ? { q: asked } : undefined);
  const matches = useMemo(() => {
    if (!query || picked?.name === placeText) return [];
    const seen = new Set<string>();
    return [...(regions.data?.items ?? []), ...(asked.length >= 2 ? (found.data?.items ?? []) : [])]
      .filter((r) => r.place_count > 0 && r.name.includes(query) && !seen.has(r.slug) && seen.add(r.slug))
      .sort((a, b) => Math.min(b.level, 3) - Math.min(a.level, 3) || b.place_count - a.place_count)
      .slice(0, 5);
  }, [query, placeText, picked, regions.data, asked, found.data]);

  // 증거는 지어내지 않는다: 지금 DB 에 실제로 있는 숫자만
  const proof = useMemo(() => {
    const all = regions.data?.items ?? [];
    const places = all.filter((r) => r.level === 1).reduce((sum, r) => sum + r.place_count, 0);
    return all.length && places ? places : null;
  }, [regions.data]);
  const items = useMemo(() => sampleCourse(Math.floor(budget / party), party), [budget, party]);
  const total = items.reduce((sum, i) => sum + i.price, 0);
  const left = budget - total;

  const choose = (r: Region) => {
    setPicked(r);
    setPlaceText(r.name);
    setOpen(false);
  };
  const pickPurpose = (p: (typeof PURPOSES)[number]) => {
    setPurpose(p);
    setParty(p.party);
  };
  const href = useMemo(() => {
    const q = new URLSearchParams({ budget: String(budget), party: String(party), purpose: purpose.code });
    if (picked && picked.name === placeText) q.set("region", picked.slug);
    else if (query) q.set("q", query);
    return `/plan?${q.toString()}`;
  }, [budget, party, purpose, picked, placeText, query]);

  const label = "mb-1.5 block text-body-sm font-semibold text-ink-2";

  return (
    <section aria-labelledby="quick-heading" className="rounded-lg border border-ink/15 bg-white p-4 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="quick-heading" className="text-h3 font-bold text-ink">
          빠른 코스 만들기
        </h2>
        <p className="text-body-sm text-muted-foreground">세 가지만 정하면 돼요</p>
      </div>

      <div className="mt-4 grid gap-5 md:grid-cols-3 md:gap-6">
        {/* 어디서 */}
        <div>
          <label htmlFor={placeId} className={label}>
            어디서
          </label>
          <div className="relative">
            <MapPin aria-hidden className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              id={placeId}
              value={placeText}
              onChange={(e) => {
                setPlaceText(e.target.value);
                setOpen(true);
              }}
              onFocus={() => setOpen(true)}
              onBlur={() => window.setTimeout(() => setOpen(false), 120)}
              placeholder="홍대, 성수 …"
              autoComplete="off"
              role="combobox"
              aria-expanded={open && matches.length > 0}
              aria-controls={`${placeId}-list`}
              className="h-12 w-full rounded-xl border border-ink/35 bg-white pr-3 pl-10 text-body text-ink outline-none placeholder:text-muted-foreground focus-visible:border-ink"
            />
            {open && matches.length > 0 ? (
              <ul id={`${placeId}-list`} role="listbox" className="absolute inset-x-0 top-[calc(100%+4px)] z-20 overflow-hidden rounded-xl border border-line bg-white shadow-card">
                {matches.map((r) => (
                  <li key={r.slug} role="option" aria-selected={picked?.slug === r.slug}>
                    <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => choose(r)} className="flex min-h-11 w-full items-center justify-between gap-3 px-3.5 text-left text-body-sm hover:bg-tomato-soft">
                      <span className="font-semibold text-ink">{r.name}</span>
                      <span className="tabular text-caption text-muted-foreground">장소 {r.place_count.toLocaleString("ko-KR")}곳</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          {hot.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="많이 찾는 동네">
              {hot.map((r) => {
                const on = picked?.slug === r.slug && placeText === r.name;
                return (
                  <button
                    key={r.slug}
                    type="button"
                    aria-pressed={on}
                    onClick={() => choose(r)}
                    className={cn("inline-flex min-h-9 items-center rounded-full border px-3 text-body-sm transition-colors", on ? "border-tomato bg-tomato font-bold text-white" : "border-ink/20 bg-paper font-medium text-ink-2 hover:border-tomato hover:bg-tomato-soft")}
                  >
                    {r.name}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>

        {/* 얼마로 */}
        <div>
          <p className={label}>얼마로</p>
          <div className="grid grid-cols-3 gap-2" role="group" aria-label="예산">
            {BUDGETS.map((b) => (
              <BudgetChip key={b.value} amount={`${b.value / 10000}만 원`} hint={b.hint} selected={budget === b.value} onSelect={() => setBudget(b.value)} />
            ))}
          </div>
        </div>

        {/* 누구랑 */}
        <div>
          <p className={label}>누구랑</p>
          <div role="radiogroup" aria-label="어떤 약속" className="grid grid-cols-5 rounded-xl border border-ink/20 bg-paper p-1">
            {PURPOSES.map((p) => {
              const on = purpose.code === p.code;
              return (
                <button key={p.code} type="button" role="radio" aria-checked={on} onClick={() => pickPurpose(p)} className={cn("min-h-10 rounded-lg text-body-sm transition-colors", on ? "bg-tomato font-extrabold text-white" : "font-medium text-ink-2 hover:bg-tomato-soft")}>
                  {p.label}
                </button>
              );
            })}
          </div>
          <div className="mt-2 flex items-center justify-end gap-1.5" role="group" aria-label="인원">
            <button type="button" onClick={() => setParty((n) => Math.max(1, n - 1))} disabled={party <= 1} aria-label="인원 줄이기" className="grid size-9 place-items-center rounded-full border border-ink/25 hover:border-ink disabled:opacity-35">
              <Minus aria-hidden className="size-3.5" />
            </button>
            <output aria-live="polite" className="tabular min-w-10 text-center text-body font-bold">
              {party}명
            </output>
            <button type="button" onClick={() => setParty((n) => Math.min(purpose.max, n + 1))} disabled={party >= purpose.max} aria-label="인원 늘리기" className="grid size-9 place-items-center rounded-full border border-ink/25 hover:border-ink disabled:opacity-35">
              <Plus aria-hidden className="size-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* 영수증은 한 줄로: 자세한 것은 위저드 · 결과가 크게 */}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-dashed border-ink/20 pt-4">
        <div className="grid gap-0.5">
          <p className="tabular text-body-sm text-ink-2" aria-live="polite">
            예시로 <b className="font-bold text-ink">{won(total)}</b> · <b className="font-bold text-tomato-deep">{won(left)} 남아요</b> · {items.length}곳 코스
          </p>
          {proof ? <p className="tabular text-caption text-muted-foreground">전국 실제 장소 {proof.toLocaleString("ko-KR")}곳 · 가입 없이 바로</p> : null}
        </div>
        <Button asChild variant="brand" size="xl" className="group max-sm:w-full">
          <Link href={href} onClick={() => track("plan_started", { entry: "landing_hero" })}>
            이 조건으로 코스 짜기 <ArrowRight aria-hidden className="transition-transform group-hover:translate-x-1" />
          </Link>
        </Button>
      </div>
    </section>
  );
}
