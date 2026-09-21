"use client";

import { useId, useMemo, useState } from "react";
import { Check, ChevronRight, MapPin, Search, TrainFront } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { decodeStation, encodeStation, useDebounced, useRegions, useStations } from "@/lib/api/hooks";
import type { Region } from "@/lib/api/types";
import { num } from "@/lib/format";
import { cn } from "@/lib/utils";

interface RegionPickerProps {
  /** 지역 slug 또는 encodeStation() 값 */
  value: string;
  onChange: (value: string) => void;
}

/** 화면에 그리는 한 칸. 실제 지역이거나, "수원시"처럼 구를 묶는 가상의 시 묶음이다. */
interface Node {
  key: string;
  name: string;
  region: Region | null; // null = 가상 묶음(선택할 수 없고 들어가기만 한다)
  children: Node[];
  placeCount: number;
}

/** 동 · 읍 · 면 (구 안의 동네). 구를 열면 그때 불러온다. */
const DONG_LEVEL = 4;

const card =
  "flex w-full items-center gap-3.5 rounded-[20px] border-2 bg-white p-4 text-left shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card";

/**
 * 전국 지역을 시도 → 시·군 → 구 → 동네 순으로 들어가며 고른다.
 * API 는 평평한 목록을 주므로(parent slug 포함) 트리는 여기서 만든다. "수원시 팔달구"처럼 이름에 시가 붙은
 * 구는 같은 시끼리 묶어 한 단계를 더 둔다 — 경기도를 열었을 때 구 이름 수십 개가 쏟아지지 않게.
 */
function buildTree(regions: Region[]): Node[] {
  const byParent = new Map<string | null, Region[]>();
  for (const r of regions) {
    const key = r.parent?.slug ?? null;
    byParent.set(key, [...(byParent.get(key) ?? []), r]);
  }
  const toNode = (r: Region): Node => {
    const kids = (byParent.get(r.slug) ?? []).map(toNode);
    const grouped: Node[] = [];
    const cities = new Map<string, Node>();
    for (const kid of kids) {
      const [city, ...rest] = kid.name.split(" ");
      if (r.level === 1 && rest.length > 0 && city) {
        let group = cities.get(city);
        if (!group) {
          group = { key: `${r.slug}/${city}`, name: city, region: null, children: [], placeCount: 0 };
          cities.set(city, group);
          grouped.push(group);
        }
        group.children.push({ ...kid, name: rest.join(" ") });
        group.placeCount += kid.placeCount;
      } else {
        grouped.push(kid);
      }
    }
    grouped.sort((a, b) => b.placeCount - a.placeCount);
    return { key: r.slug, name: r.name, region: r, children: grouped, placeCount: r.place_count };
  };
  return (byParent.get(null) ?? []).map(toNode).sort((a, b) => b.placeCount - a.placeCount);
}

export function RegionPicker({ value, onChange }: RegionPickerProps) {
  const regions = useRegions();
  const [path, setPath] = useState<Node[]>([]);
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim(), 200);
  const stations = useStations(query);
  const searchId = useId();

  const tree = useMemo(() => buildTree(regions.data?.items ?? []), [regions.data]);
  const hotspots = useMemo(
    () => [...(regions.data?.items ?? [])].filter((r) => r.level === 3 && r.place_count > 0).sort((a, b) => b.place_count - a.place_count).slice(0, 12),
    [regions.data],
  );
  // 동 · 읍 · 면은 전체 목록에 없다(1,400곳) → 이름으로 찾을 때와 구를 열었을 때만 서버에 묻는다
  const found = useRegions(query.length >= 2 ? { q: query } : undefined);
  const matches = useMemo(() => {
    if (!query) return [];
    const listed = (regions.data?.items ?? []).filter((r) => r.name.includes(query));
    const dongs = query.length >= 2 ? (found.data?.items ?? []).filter((r) => r.level >= DONG_LEVEL && r.name.includes(query)) : [];
    const seen = new Set<string>();
    return [...listed, ...dongs]
      .filter((r) => r.place_count > 0 && !seen.has(r.slug) && seen.add(r.slug))
      .sort((a, b) => Math.min(b.level, 3) - Math.min(a.level, 3) || b.place_count - a.place_count)
      .slice(0, 14);
  }, [query, regions.data, found.data]);

  const current = path[path.length - 1];
  const district = current?.region?.level === 2 ? current.region : null;
  const inside = useRegions(district ? { parent: district.slug } : undefined);
  const dongs = district && inside.data && !inside.isPlaceholderData ? inside.data.items.filter((r) => r.level >= DONG_LEVEL && r.parent?.slug === district.slug).sort((a, b) => b.place_count - a.place_count) : [];
  const nodes = current ? current.children : tree;
  const pickedStation = decodeStation(value);

  if (regions.isPending) {
    return (
      <div className="grid gap-3 sm:grid-cols-2" aria-busy="true">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-[76px] rounded-[20px]" />
        ))}
      </div>
    );
  }
  if (regions.isError) return <ErrorState error={regions.error} onRetry={() => void regions.refetch()} size="sm" />;

  const regionButton = (r: Region, label = r.name, sub?: string) => {
    const selected = value === r.slug;
    return (
      <button
        key={r.slug}
        type="button"
        role="radio"
        aria-checked={selected}
        onClick={() => onChange(r.slug)}
        className={cn(card, selected ? "border-blue-deep bg-blue-soft" : "border-transparent")}
      >
        <span className="bg-grad-soft grid size-11 shrink-0 place-items-center rounded-2xl text-blue-deep">
          <MapPin aria-hidden className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-[17px] font-extrabold tracking-tight">{label}</b>
          <span className="tabular block truncate text-[13px] text-muted-foreground">{sub ?? `${r.parent ? `${r.parent.name} · ` : ""}장소 ${num(r.place_count)}곳`}</span>
        </span>
        {selected ? <Check aria-hidden className="size-5 shrink-0 text-blue-deep" /> : null}
      </button>
    );
  };

  return (
    <div>
      <label htmlFor={searchId} className="sr-only">
        지역 · 역 검색
      </label>
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-muted-foreground" />
        <input
          id={searchId}
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="동네나 역 이름으로 찾기 (예: 신도림, 반포, 성수)"
          autoComplete="off"
          className="h-14 w-full rounded-2xl border border-input bg-white pr-4 pl-12 text-base font-bold shadow-soft placeholder:font-medium placeholder:text-muted-foreground focus-visible:border-blue-deep"
        />
      </div>

      {/* 역·장소 주변은 아래 지역 트리에 없는 값이다(검색 결과나 둘러보기의 "이 근처로 코스 짜기"로 들어온다) → 골라 둔 것을 따로 보여 준다 */}
      {pickedStation && !query ? (
        <div role="status" className="mt-4 flex items-center gap-3.5 rounded-[20px] border-2 border-blue-deep bg-blue-soft p-4 shadow-soft">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-white text-blue-deep">
            <MapPin aria-hidden className="size-5" />
          </span>
          <span className="min-w-0 flex-1">
            <b className="block truncate text-[17px] font-extrabold tracking-tight">{pickedStation.name} 주변</b>
            <span className="block truncate text-[13px] text-ink-2">여기서 걸어서 다닐 거리로 짜요</span>
          </span>
          <button type="button" onClick={() => onChange("")} className="shrink-0 rounded-full bg-white px-3.5 py-2 text-[13px] font-extrabold text-ink-2 shadow-soft hover:text-ink" aria-label={`${pickedStation.name} 주변 선택 취소하고 다른 곳 고르기`}>
            다른 곳 고르기
          </button>
        </div>
      ) : null}

      <div className="mt-4" role="radiogroup" aria-label="지역 선택" aria-live="polite">
        {query ? (
          matches.length === 0 && (stations.data?.items.length ?? 0) === 0 && !stations.isFetching ? (
            <EmptyState size="sm" mood="think" title={`‘${query}’ 은(는) 찾지 못했어요`} description="가까운 지하철역이나 구 이름으로 다시 찾아볼까요?">
              <button type="button" onClick={() => setQ("")} className="rounded-full bg-soft px-4 py-2 text-sm font-extrabold text-ink-2 hover:bg-line">
                전체 지역 보기
              </button>
            </EmptyState>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {matches.map((r) => regionButton(r))}
              {(stations.data?.items ?? []).map((s) => {
                const encoded = encodeStation(s);
                const selected = pickedStation?.name === s.name;
                return (
                  <button
                    key={s.name}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => onChange(encoded)}
                    className={cn(card, selected ? "border-blue-deep bg-blue-soft" : "border-transparent")}
                  >
                    <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-success-soft text-success">
                      <TrainFront aria-hidden className="size-5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <b className="block truncate text-[17px] font-extrabold tracking-tight">{s.name} 주변</b>
                      <span className="block truncate text-[13px] text-muted-foreground">지하철역 · 걸어서 다닐 거리로 짜요</span>
                    </span>
                    {selected ? <Check aria-hidden className="size-5 shrink-0 text-blue-deep" /> : null}
                  </button>
                );
              })}
            </div>
          )
        ) : (
          <>
            {/* 어디까지 들어왔는지 — 누르면 그 단계로 돌아간다 */}
            <nav aria-label="지역 단계" className="mb-3 flex flex-wrap items-center gap-1 text-sm font-semibold text-muted-foreground">
              <button type="button" aria-current={path.length === 0 ? "location" : undefined} onClick={() => setPath([])} className={cn("rounded-lg px-2 py-1 hover:bg-ink/[0.05] hover:text-ink", path.length === 0 && "text-ink")}>
                전국
              </button>
              {path.map((node, i) => (
                <span key={node.key} className="flex items-center gap-1">
                  <ChevronRight aria-hidden className="size-3.5" />
                  <button
                    type="button"
                    aria-current={i === path.length - 1 ? "location" : undefined}
                    onClick={() => setPath(path.slice(0, i + 1))}
                    className={cn("rounded-lg px-2 py-1 hover:bg-ink/[0.05] hover:text-ink", i === path.length - 1 && "text-ink")}
                  >
                    {node.name}
                  </button>
                </span>
              ))}
            </nav>

            {path.length === 0 && hotspots.length > 0 ? (
              <div className="mb-4">
                <p className="mb-2 text-[13px] font-bold text-ink-2">많이 찾는 동네</p>
                <div className="flex flex-wrap gap-2">
                  {hotspots.map((r) => (
                    <button
                      key={r.slug}
                      type="button"
                      role="radio"
                      aria-checked={value === r.slug}
                      onClick={() => onChange(r.slug)}
                      className={cn(
                        "rounded-full border-2 px-3.5 py-1.5 text-sm font-bold transition-colors",
                        value === r.slug ? "border-blue-deep bg-blue-deep text-white" : "border-transparent bg-white text-ink-2 shadow-soft hover:bg-blue-soft",
                      )}
                    >
                      {r.name}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="grid animate-page gap-3 sm:grid-cols-2" key={current?.key ?? "root"}>
              {current?.region ? regionButton(current.region, `${current.name} 전체`, `이 안에서 어디든 · 장소 ${num(current.region.place_count)}곳`) : null}
              {nodes
                .filter((n) => n.placeCount > 0)
                .map((node) =>
                  node.children.length > 0 || node.region?.level === 2 ? (
                    <button
                      key={node.key}
                      type="button"
                      onClick={() => setPath([...path, node])}
                      className={cn(card, "border-transparent")}
                      aria-label={`${node.name} 안으로 들어가기, 장소 ${num(node.placeCount)}곳`}
                    >
                      <span className="bg-grad-soft grid size-11 shrink-0 place-items-center rounded-2xl text-blue-deep">
                        <MapPin aria-hidden className="size-5" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <b className="block truncate text-[17px] font-extrabold tracking-tight">{node.name}</b>
                        <span className="tabular block truncate text-[13px] text-muted-foreground">
                          {node.children.length > 0 ? `${node.children.length}곳으로 나뉘어요` : "동네까지 고를 수 있어요"} · 장소 {num(node.placeCount)}곳
                        </span>
                      </span>
                      <ChevronRight aria-hidden className="size-5 shrink-0 text-muted-foreground" />
                    </button>
                  ) : node.region ? (
                    regionButton(node.region, node.name)
                  ) : null,
                )}
            </div>

            {district ? (
              inside.isFetching && dongs.length === 0 ? (
                <div className="mt-5 grid gap-3 sm:grid-cols-2" aria-busy="true">
                  {Array.from({ length: 4 }, (_, i) => (
                    <Skeleton key={i} className="h-[76px] rounded-[20px]" />
                  ))}
                </div>
              ) : dongs.length > 0 ? (
                <div className="mt-5">
                  <p className="mb-2 text-[13px] font-bold text-ink-2">동네까지 좁히기 · {district.name}의 동 {dongs.length}곳</p>
                  <div className="grid gap-3 sm:grid-cols-2">{dongs.map((r) => regionButton(r, r.name, `걸어서 다닐 범위 · 장소 ${num(r.place_count)}곳`))}</div>
                </div>
              ) : null
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
