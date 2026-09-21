"use client";

import { useCallback, useId, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Search, X } from "lucide-react";
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
  const items = useMemo(() => attractions.data?.pages.flatMap((p) => p.items) ?? [], [attractions.data]);

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
      <header className="grid gap-3">
        <span className="inline-flex w-fit items-center rounded-full bg-blue-soft px-3.5 py-2 text-sm font-extrabold text-blue-deep">
          둘러보기
        </span>
        <h1 className="text-[clamp(28px,4vw,44px)] font-extrabold text-ink">
          돈 안 들이고도 <span className="gt">갈 곳은 많아요</span>
        </h1>
        <p className="max-w-xl text-base text-muted-foreground sm:text-lg">
          관광지, 공원, 전시, 축제, 문화공간까지. 마음에 드는 곳을 찾으면 그 근처로 예산 코스를 짜 드려요.
        </p>
      </header>

      <EventsStrip region={regionSlug} />

      <section aria-labelledby="explore-list-heading" className="grid grid-cols-[minmax(0,1fr)] gap-5">
        <h2 id="explore-list-heading" className="sr-only">
          장소 목록
        </h2>

        <div className="grid gap-4 rounded-card border border-line bg-white p-4 shadow-soft sm:p-5">
          <div role="group" aria-label="종류" className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1 py-1">
            {typeOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={type === option.value}
                onClick={() => changeType(option.value)}
                className={cn(
                  "h-10 shrink-0 rounded-full px-4 text-[14.5px] font-extrabold transition-colors",
                  type === option.value ? "bg-ink text-white" : "bg-[#F0F4FA] text-ink-2 hover:bg-line",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-cols-[220px_190px_minmax(0,1fr)_auto]">
            <div className="grid gap-1.5">
              <Label htmlFor={ids.region} className="text-xs font-extrabold text-muted-foreground">
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
                <p role="alert" className="text-xs font-bold text-danger">
                  지역 목록을 불러오지 못했어요.{" "}
                  <button type="button" className="underline" onClick={() => void regions.refetch()}>
                    다시 시도
                  </button>
                </p>
              ) : null}
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor={ids.date} className="text-xs font-extrabold text-muted-foreground">
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
              <Label htmlFor={ids.q} className="text-xs font-extrabold text-muted-foreground">
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
            <ul className={cn("grid grid-cols-[minmax(0,1fr)] gap-5 sm:grid-cols-2 lg:grid-cols-3", attractions.isPlaceholderData && "opacity-60 transition-opacity")}>
              {items.map((item) => (
                <li key={item.id}>
                  <AttractionCard item={item} />
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
