"use client";

import { useCallback, useId, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Check, Search, X } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { track } from "@/lib/analytics";
import { useAttractions, useDebounced, useRegions } from "@/lib/api/hooks";
import type { AttractionType } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { AttractionCard } from "./AttractionCard";
import { ATTRACTION_TYPE_META, ATTRACTION_TYPES, isAttractionType } from "./attraction-meta";
import { EventsStrip } from "./EventsStrip";

const ALL = "all";

export function ExploreView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const ids = { region: useId(), date: useId(), q: useId() };

  const initialType = searchParams.get("type");
  const [type, setType] = useState<AttractionType | typeof ALL>(isAttractionType(initialType) ? initialType : ALL);
  const [region, setRegion] = useState<string>(searchParams.get("region") ?? ALL);
  const [date, setDate] = useState(searchParams.get("date") ?? "");
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const debouncedQ = useDebounced(q.trim(), 300);

  const regions = useRegions();
  const regionSlug = region === ALL ? undefined : region;

  const params = useMemo(
    () => ({
      region: regionSlug,
      type: type === ALL ? undefined : [type],
      date: date || undefined,
      q: debouncedQ || undefined,
    }),
    [regionSlug, type, date, debouncedQ],
  );
  const attractions = useAttractions(params);
  // 실제 사진이 있는 곳을 먼저 (docs/39): 페이지 안에서만 옮긴다 — "더 보기"로 받은 다음 페이지가 앞의 카드를 밀어내지 않게
  const items = useMemo(
    () => attractions.data?.pages.flatMap((p) => [...p.items.filter((i) => i.thumbnail_url), ...p.items.filter((i) => !i.thumbnail_url)]) ?? [],
    [attractions.data],
  );

  const syncUrl = useCallback(
    (next: { type?: string; region?: string; date?: string }) => {
      const sp = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(next)) {
        if (!value || value === ALL) sp.delete(key);
        else sp.set(key, value);
      }
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const changeType = (next: AttractionType | typeof ALL) => {
    setType(next);
    syncUrl({ type: next });
    track("explore_filtered", { type: next, region: regionSlug });
  };
  const changeRegion = (next: string) => {
    setRegion(next);
    syncUrl({ region: next });
    track("explore_filtered", { type, region: next === ALL ? undefined : next });
  };
  const changeDate = (next: string) => {
    setDate(next);
    syncUrl({ date: next });
  };
  const reset = () => {
    setType(ALL);
    setRegion(ALL);
    setDate("");
    setQ("");
    router.replace(pathname, { scroll: false });
  };

  const filtered = type !== ALL || region !== ALL || date !== "" || q !== "";
  const typeOptions: { value: AttractionType | typeof ALL; label: string }[] = [
    { value: ALL, label: "전체" },
    ...ATTRACTION_TYPES.map((t) => ({ value: t, label: ATTRACTION_TYPE_META[t].label })),
  ];

  return (
    <div className="wrap grid grid-cols-[minmax(0,1fr)] gap-8 pt-8 pb-16 sm:pt-12">
      <header className="grid gap-4">
        <p className="flex items-center gap-2.5 text-body-sm font-semibold tracking-[0.02em] text-ink-2">
          <span aria-hidden className="size-2 rounded-full bg-gold" />
          둘러보기
        </p>
        <h1 className="font-serif text-display text-ink">
          돈 안 들이고도
          <br />
          갈 곳은 많아요
        </h1>
        <p className="max-w-xl text-body text-ink-2 sm:text-body-lg">
          관광지, 공원, 전시, 축제, 문화공간까지. 마음에 드는 곳을 찾으면 그 근처로 예산 코스를 짜 드려요.
        </p>
      </header>

      <EventsStrip region={regionSlug} />

      <section aria-labelledby="explore-list-heading" className="grid grid-cols-[minmax(0,1fr)] gap-5">
        <h2 id="explore-list-heading" className="sr-only">
          장소 목록
        </h2>

        {/* 필터: 흰 상자가 아니라 위아래 선 사이의 한 줄 */}
        <div className="grid gap-4 border-y border-ink/10 py-5">
          <div role="group" aria-label="종류" className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1 py-1">
            {typeOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={type === option.value}
                onClick={() => changeType(option.value)}
                className={cn(
                  "inline-flex h-10 shrink-0 items-center gap-1 rounded-full border px-4 text-body transition-colors",
                  // 선택 = 토마토 · 굵게 · 체크 (색 없이도 구분된다, docs/38)
                  type === option.value ? "border-tomato bg-tomato font-extrabold text-white" : "border-ink/20 bg-paper font-semibold text-ink-2 hover:border-tomato hover:bg-tomato-soft",
                )}
              >
                {type === option.value ? <Check aria-hidden strokeWidth={3} className="size-4" /> : null}
                {option.label}
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-cols-[220px_190px_minmax(0,1fr)_auto]">
            <div className="grid gap-1.5">
              <Label htmlFor={ids.region} className="text-caption font-semibold text-muted-foreground">
                지역
              </Label>
              <Select value={region} onValueChange={changeRegion} disabled={regions.isPending}>
                <SelectTrigger id={ids.region} className="h-11 w-full rounded-xl font-bold">
                  <SelectValue placeholder={regions.isPending ? "불러오는 중…" : "전체 지역"} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>전체 지역</SelectItem>
                  {regions.data?.items.map((r) => (
                    <SelectItem key={r.slug} value={r.slug}>
                      {r.name}
                      {r.parent ? <span className="text-muted-foreground"> · {r.parent.name}</span> : null}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {regions.isError ? (
                <p role="alert" className="text-caption font-semibold text-danger">
                  지역 목록을 불러오지 못했어요.{" "}
                  <button type="button" className="underline" onClick={() => void regions.refetch()}>
                    다시 시도
                  </button>
                </p>
              ) : null}
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor={ids.date} className="text-caption font-semibold text-muted-foreground">
                가는 날 (선택)
              </Label>
              <Input
                id={ids.date}
                type="date"
                value={date}
                onChange={(e) => changeDate(e.target.value)}
                className="h-11 rounded-xl font-bold"
              />
            </div>

            <div className="grid gap-1.5 sm:col-span-2 lg:col-span-1">
              <Label htmlFor={ids.q} className="text-caption font-semibold text-muted-foreground">
                검색
              </Label>
              <div className="relative">
                <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id={ids.q}
                  type="search"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="이름이나 주소로 찾기"
                  maxLength={60}
                  autoComplete="off"
                  className="h-11 rounded-xl pl-10 font-bold"
                />
              </div>
            </div>

            {filtered ? (
              <Button type="button" variant="ghost" className="h-11 self-end rounded-xl font-bold text-ink-2" onClick={reset}>
                <X aria-hidden /> 조건 지우기
              </Button>
            ) : null}
          </div>
        </div>

        <p className="sr-only" aria-live="polite">
          {attractions.isSuccess ? `${items.length}곳을 보여 주고 있어요` : ""}
        </p>

        {attractions.isPending ? (
          <div className="grid grid-cols-[minmax(0,1fr)] gap-5 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label="장소를 불러오는 중">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="overflow-hidden rounded-card border border-line bg-white">
                <Skeleton className="aspect-[16/10] w-full rounded-none" />
                <div className="grid gap-2.5 p-5">
                  <Skeleton className="h-5 w-2/3" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-1/2" />
                </div>
              </div>
            ))}
          </div>
        ) : attractions.isError && !attractions.data ? (
          <ErrorState error={attractions.error} onRetry={() => void attractions.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState
            mood="think"
            title="조건에 맞는 곳을 못 찾았어요"
            description="종류나 날짜를 바꿔 보면 더 많은 곳이 나와요."
          >
            {filtered ? (
              <Button variant="soft" size="md" onClick={reset}>
                조건 지우기
              </Button>
            ) : null}
            <Button asChild variant="brand" size="md">
              <Link href="/plan">바로 코스 짜기</Link>
            </Button>
          </EmptyState>
        ) : (
          <>
            {/* 잡지처럼: 맨 위 한 곳은 크게, 나머지는 3열 */}
            <ul className={cn("grid grid-cols-[minmax(0,1fr)] gap-x-6 gap-y-12 sm:grid-cols-2 lg:grid-cols-3", attractions.isPlaceholderData && "opacity-60 transition-opacity")}>
              {items.map((item, i) => (
                <li key={item.id} className={cn(i === 0 && "sm:col-span-2 lg:col-span-3 lg:border-b lg:border-ink/10 lg:pb-12")}>
                  <AttractionCard item={item} feature={i === 0} kicker={regionSlug ? "맨 먼저 볼 곳" : undefined} />
                </li>
              ))}
            </ul>
            {attractions.hasNextPage && !attractions.isError ? (
              <div className="flex justify-center pt-2">
                <Button
                  variant="soft"
                  size="xl"
                  onClick={() => void attractions.fetchNextPage()}
                  disabled={attractions.isFetchingNextPage}
                >
                  {attractions.isFetchingNextPage ? "불러오는 중…" : "더 보기"}
                </Button>
              </div>
            ) : null}
            {attractions.isError ? (
              <ErrorState error={attractions.error} onRetry={() => void attractions.fetchNextPage()} size="sm" />
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
