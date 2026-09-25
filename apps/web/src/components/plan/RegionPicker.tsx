"use client";

import { useId, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, ChevronRight, GraduationCap, MapPin, Search, ShoppingBag, TrainFront } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { decodeCampus, decodeErrand, decodeStation, encodeCampus, encodeErrand, encodeStation, useDebounced, useRegions, useSpots, useStations, useUniversities, type Spot, type University } from "@/lib/api/hooks";
import type { Region } from "@/lib/api/types";
import { num } from "@/lib/format";
import { cn } from "@/lib/utils";

interface RegionPickerProps {
  /** 지역 slug · encodeStation() · encodeCampus() · encodeErrand() 값 */
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

/** 가는 김에: 그곳에서 보낼 시간. 0 = 볼일 없이 그 근처로만 */
const ERRAND_MINUTES = [
  { minutes: 0, label: "근처로만" },
  { minutes: 30, label: "30분" },
  { minutes: 60, label: "1시간" },
  { minutes: 120, label: "2시간" },
] as const;

// 지역 목록은 카드 격자가 아니라 노선도의 역 목록처럼: 줄 하나에 이름과 숫자 (docs/31 §6)
const card =
  "flex w-full items-center gap-3 border-b border-line px-2 py-3.5 text-left transition-colors duration-150 hover:bg-white/70";

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
  // 랜딩에서 동네 이름만 적고 왔으면(?q=성수) 그 글자로 찾기부터 시작한다
  const params = useSearchParams();
  const [q, setQ] = useState(() => params.get("q") ?? "");
  // 행정구역 목록은 보조 수단이다: 먼저 검색 · 많이 찾는 동네, 목록은 펼쳐야 보인다 (목록 안으로 들어간 뒤에는 계속 보인다)
  const [browse, setBrowse] = useState(false);
  // 많이 찾는 동네는 여섯 곳만 먼저, 나머지는 "더 보기"
  const [moreHot, setMoreHot] = useState(false);
  // docs/34: 하루의 중심 — 동네 · 역, 또는 대학교(캠퍼스와 학교 앞, 그날의 축제까지)
  // 가는 김에(docs/51 B1): 꼭 들를 매장 · 가게 · 랜드마크를 중심으로 앞뒤를 짠다
  const [mode, setMode] = useState<"area" | "campus" | "errand">(() => (decodeErrand(value) ? "errand" : decodeCampus(value) ? "campus" : "area"));
  const query = useDebounced(q.trim(), 200);
  const stations = useStations(mode === "area" ? query : "");
  const spots = useSpots(mode === "errand" ? query : "");
  // 동네 검색에도 학교가 함께 나온다("가천대"를 지역 칸에 쳐도 찾는다)
  const universities = useUniversities(query, mode === "campus" ? query.length >= 1 : query.length >= 2);
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
  const pickedCampus = decodeCampus(value);
  const pickedErrand = decodeErrand(value);
  const campusRows = query && !universities.isPlaceholderData ? (universities.data?.items ?? []) : [];

  if (regions.isPending) {
    return (
      <div className="grid gap-x-8 sm:grid-cols-2" aria-busy="true">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-[56px] rounded-md" />
        ))}
      </div>
    );
  }
  if (regions.isError) return <ErrorState error={regions.error} onRetry={() => void regions.refetch()} size="sm" />;

  const campusButton = (u: University) => {
    const selected = pickedCampus?.id === u.id;
    return (
      <button key={u.id} type="button" role="radio" aria-checked={selected} onClick={() => onChange(encodeCampus(u))} className={cn(card, selected && "bg-tomato-soft text-tomato-deep")}>
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-paper-2 text-ink">
          <GraduationCap aria-hidden className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-body-lg font-semibold">{u.name}</b>
          <span className="block truncate text-body-sm text-muted-foreground">{u.address ?? "대학교"}</span>
        </span>
        {selected ? <Check aria-hidden className="size-5 shrink-0 text-tomato-deep" /> : null}
      </button>
    );
  };

  const spotButton = (sp: Spot) => {
    const selected = pickedErrand?.name === sp.name && Math.abs(pickedErrand.lat - sp.lat) < 1e-5;
    return (
      <button
        key={`${sp.source}:${sp.name}:${sp.lat}`}
        type="button"
        role="radio"
        aria-checked={selected}
        onClick={() => {
          onChange(encodeErrand({ name: sp.name, lat: sp.lat, lng: sp.lng, place_id: sp.place_id, minutes: 30 }));
          setQ("");
        }}
        className={cn(card, selected && "bg-tomato-soft text-tomato-deep")}
      >
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-paper-2 text-ink">
          <ShoppingBag aria-hidden className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-body-lg font-semibold">{sp.name}</b>
          <span className="block truncate text-body-sm text-muted-foreground">{sp.address ?? "주소 정보 없음"}</span>
        </span>
        <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-caption font-semibold", sp.source === "ours" ? "bg-blue-soft text-blue-deep" : "bg-paper-2 text-ink-2")}>
          {sp.source === "ours" ? "우리 장소" : "지도 검색"}
        </span>
        {selected ? <Check aria-hidden className="size-5 shrink-0 text-tomato-deep" /> : null}
      </button>
    );
  };

  const regionButton = (r: Region, label = r.name, sub?: string) => {
    const selected = value === r.slug;
    return (
      <button
        key={r.slug}
        type="button"
        role="radio"
        aria-checked={selected}
        onClick={() => onChange(r.slug)}
        className={cn(card, selected && "bg-tomato-soft text-tomato-deep")}
      >
        <span className="min-w-0 flex-1">
          <b className="block truncate text-body-lg font-semibold">{label}</b>
          <span className="tabular block truncate text-body-sm text-muted-foreground">{sub ?? `${r.parent ? `${r.parent.name} · ` : ""}장소 ${num(r.place_count)}곳`}</span>
        </span>
        {selected ? <Check aria-hidden className="size-5 shrink-0 text-tomato-deep" /> : null}
      </button>
    );
  };

  return (
    <div>
      {/* 하루의 중심: 동네 · 역 / 대학교. 새 서비스가 아니라 같은 코스의 다른 출발점이다 (docs/34) */}
      <div role="tablist" aria-label="어디를 중심으로 짤까요" className="mb-3 inline-flex rounded-full bg-paper-2 p-1">
        {(
          [
            { key: "area", label: "동네 · 역", Icon: MapPin },
            { key: "campus", label: "대학교", Icon: GraduationCap },
            { key: "errand", label: "꼭 들를 곳", Icon: ShoppingBag },
          ] as const
        ).map(({ key, label, Icon }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={mode === key}
            onClick={() => {
              setMode(key);
              setQ("");
            }}
            className={cn("inline-flex min-h-11 items-center gap-1.5 rounded-full px-4 text-body-sm font-semibold transition-colors", mode === key ? "bg-white text-ink shadow-soft" : "text-ink-2 hover:text-ink")}
          >
            <Icon aria-hidden className="size-4" />
            {label}
          </button>
        ))}
      </div>
      <label htmlFor={searchId} className="sr-only">
        {mode === "campus" ? "대학교 검색" : mode === "errand" ? "꼭 들를 곳 검색" : "지역 · 역 검색"}
      </label>
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-muted-foreground" />
        <input
          id={searchId}
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={
            mode === "campus"
              ? "학교 이름으로 찾기 (예: 가천대, 홍익대, 부산대)"
              : mode === "errand"
                ? "매장 · 가게 · 랜드마크 이름 (예: 애플 가로수길)"
                : "동네나 역 이름으로 찾기 (예: 신도림, 반포, 성수)"
          }
          autoComplete="off"
          className="h-14 w-full rounded-2xl border border-input bg-white pr-4 pl-12 text-body font-bold shadow-soft placeholder:font-medium placeholder:text-muted-foreground focus-visible:border-tomato"
        />
      </div>

      {/* 역·장소 주변은 아래 지역 트리에 없는 값이다(검색 결과나 둘러보기의 "이 근처로 코스 짜기"로 들어온다) → 골라 둔 것을 따로 보여 준다 */}
      {pickedStation && !query ? (
        <div role="status" className="mt-4 flex items-center gap-3.5 rounded-[20px] border-2 border-tomato bg-tomato-soft p-4 shadow-soft">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-white text-tomato-deep">
            <MapPin aria-hidden className="size-5" />
          </span>
          <span className="min-w-0 flex-1">
            <b className="block truncate text-body-lg font-semibold">{pickedStation.name} 주변</b>
            <span className="block truncate text-body-sm text-ink-2">여기서 걸어서 다닐 거리로 짜요</span>
          </span>
          <button type="button" onClick={() => onChange("")} className="shrink-0 rounded-full bg-white px-3.5 py-2 text-body-sm font-semibold text-ink-2 shadow-soft hover:text-ink" aria-label={`${pickedStation.name} 주변 선택 취소하고 다른 곳 고르기`}>
            다른 곳 고르기
          </button>
        </div>
      ) : null}

      {pickedErrand && !query ? (
        <div role="status" className="mt-4 grid gap-3 rounded-[20px] border-2 border-tomato bg-tomato-soft p-4 shadow-soft">
          <div className="flex items-center gap-3.5">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-white text-tomato-deep">
              <ShoppingBag aria-hidden className="size-5" />
            </span>
            <span className="min-w-0 flex-1">
              <b className="block truncate text-body-lg font-semibold">{pickedErrand.name} 가는 김에</b>
              <span className="block truncate text-body-sm text-ink-2">
                {pickedErrand.minutes > 0 ? "여기서 볼일을 보고, 그 뒤부터 근처로 이어서 짜요" : "이곳을 중심으로 걸어서 다닐 거리로 짜요"}
              </span>
            </span>
            <button type="button" onClick={() => onChange("")} className="shrink-0 rounded-full bg-white px-3.5 py-2 text-body-sm font-semibold text-ink-2 shadow-soft hover:text-ink" aria-label={`${pickedErrand.name} 선택 취소하고 다른 곳 고르기`}>
              다른 곳 고르기
            </button>
          </div>
          <div role="radiogroup" aria-label="그곳에서 보낼 시간" className="flex flex-wrap gap-2">
            {ERRAND_MINUTES.map(({ minutes, label }) => {
              const on = pickedErrand.minutes === minutes;
              return (
                <button
                  key={minutes}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => onChange(encodeErrand({ ...pickedErrand, minutes }))}
                  className={cn("min-h-11 rounded-full border px-4 text-body-sm", on ? "border-tomato bg-tomato font-bold text-white" : "border-line bg-white font-medium text-ink-2 hover:border-tomato")}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {pickedCampus && !query ? (
        <div role="status" className="mt-4 flex items-center gap-3.5 rounded-[20px] border-2 border-tomato bg-tomato-soft p-4 shadow-soft">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-white text-tomato-deep">
            <GraduationCap aria-hidden className="size-5" />
          </span>
          <span className="min-w-0 flex-1">
            <b className="block truncate text-body-lg font-semibold">{pickedCampus.name}</b>
            <span className="block truncate text-body-sm text-ink-2">캠퍼스와 학교 앞, 그날 축제까지 이어서 짜요</span>
          </span>
          <button type="button" onClick={() => onChange("")} className="shrink-0 rounded-full bg-white px-3.5 py-2 text-body-sm font-semibold text-ink-2 shadow-soft hover:text-ink" aria-label={`${pickedCampus.name} 선택 취소하고 다른 곳 고르기`}>
            다른 곳 고르기
          </button>
        </div>
      ) : null}

      <div className="mt-4" role="radiogroup" aria-label={mode === "campus" ? "대학교 선택" : mode === "errand" ? "꼭 들를 곳 선택" : "지역 선택"} aria-live="polite">
        {mode === "errand" ? (
          query.length < 2 ? (
            pickedErrand ? null : (
              <p className="text-body-sm text-ink-2">꼭 가야 하는 곳이 있으면 이름을 써 주세요. 그곳에 들르는 김에 앞뒤로 갈 곳을 예산 안에서 짜 드려요.</p>
            )
          ) : spots.isPending ? (
            <div className="grid gap-x-8 sm:grid-cols-2" aria-busy="true">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-[56px] rounded-md" />
              ))}
            </div>
          ) : (spots.data?.items.length ?? 0) === 0 ? (
            <EmptyState size="sm" mood="think" title={`‘${query}’ 은(는) 찾지 못했어요`} description="매장 이름에 동네를 붙여 다시 찾아볼까요? (예: 애플 가로수길)" />
          ) : (
            <div className="grid gap-x-8 sm:grid-cols-2">{(spots.data?.items ?? []).map(spotButton)}</div>
          )
        ) : mode === "campus" ? (
          query && universities.isPending ? (
            <div className="grid gap-x-8 sm:grid-cols-2" aria-busy="true">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-[56px] rounded-md" />
              ))}
            </div>
          ) : campusRows.length === 0 ? (
            <EmptyState size="sm" mood="think" title={query ? `‘${query}’ 은(는) 찾지 못했어요` : "학교 이름을 써 주세요"} description="전국 대학 · 전문대학 중 위치를 확인한 곳만 있어요. 없으면 ‘동네 · 역’에서 가까운 역으로 골라 주세요." />
          ) : (
            <div className="grid gap-x-8 sm:grid-cols-2">{campusRows.map(campusButton)}</div>
          )
        ) : query ? (
          matches.length === 0 && (stations.data?.items.length ?? 0) === 0 && campusRows.length === 0 && !stations.isFetching ? (
            <EmptyState size="sm" mood="think" title={`‘${query}’ 은(는) 찾지 못했어요`} description="가까운 지하철역이나 구 이름으로 다시 찾아볼까요?">
              <button type="button" onClick={() => setQ("")} className="rounded-full bg-soft px-4 py-2 text-body-sm font-semibold text-ink-2 hover:bg-line">
                전체 지역 보기
              </button>
            </EmptyState>
          ) : (
            <div className="grid gap-x-8 sm:grid-cols-2">
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
                    className={cn(card, selected && "bg-tomato-soft text-tomato-deep")}
                  >
                    <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-success-soft text-success">
                      <TrainFront aria-hidden className="size-5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <b className="block truncate text-body-lg font-semibold">{s.name} 주변</b>
                      <span className="block truncate text-body-sm text-muted-foreground">지하철역 · 걸어서 다닐 거리로 짜요</span>
                    </span>
                    {selected ? <Check aria-hidden className="size-5 shrink-0 text-tomato-deep" /> : null}
                  </button>
                );
              })}
              {campusRows.map(campusButton)}
            </div>
          )
        ) : (
          <>
            {path.length === 0 && hotspots.length > 0 ? (
              <div className="mb-5">
                <p className="mb-2 text-body-sm font-semibold text-ink-2">많이 찾는 동네</p>
                <div className="flex flex-wrap gap-2">
                  {(moreHot ? hotspots : hotspots.slice(0, 6)).map((r) => (
                    <button
                      key={r.slug}
                      type="button"
                      role="radio"
                      aria-checked={value === r.slug}
                      onClick={() => onChange(r.slug)}
                      className={cn(
                        "inline-flex min-h-11 items-center rounded-full border-2 px-3.5 text-body-sm font-semibold transition-colors",
                        value === r.slug ? "border-tomato bg-tomato text-white" : "border-transparent bg-white text-ink-2 shadow-soft hover:bg-tomato-soft",
                      )}
                    >
                      {r.name}
                    </button>
                  ))}
                  {hotspots.length > 6 ? (
                    <button type="button" aria-expanded={moreHot} onClick={() => setMoreHot((v) => !v)} className="inline-flex min-h-11 items-center rounded-full px-3 text-body-sm font-semibold text-ink-2 underline decoration-line underline-offset-4 hover:text-ink">
                      {moreHot ? "접기" : `더 보기 +${hotspots.length - 6}`}
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}

            {path.length === 0 && !browse ? (
              <button
                type="button"
                aria-expanded={false}
                onClick={() => setBrowse(true)}
                className="inline-flex min-h-11 w-full items-center justify-between gap-2 border-t border-dashed border-line pt-3 text-left text-body-sm font-semibold text-ink-2 hover:text-ink"
              >
                <span>
                  지역에서 직접 고르기 <span className="font-normal text-muted-foreground">시 · 도 → 구 → 동네</span>
                </span>
                <ChevronRight aria-hidden className="size-4 shrink-0" />
              </button>
            ) : (
              <>
                {/* 어디까지 들어왔는지 — 누르면 그 단계로 돌아간다 */}
                <nav aria-label="지역 단계" className="mb-3 flex flex-wrap items-center gap-1 text-body-sm font-semibold text-muted-foreground">
                  <button type="button" aria-current={path.length === 0 ? "location" : undefined} onClick={() => setPath([])} className={cn("inline-flex min-h-11 items-center rounded-lg px-2 hover:bg-ink/[0.05] hover:text-ink", path.length === 0 && "text-ink")}>
                    전국
                  </button>
                  {path.map((node, i) => (
                    <span key={node.key} className="flex items-center gap-1">
                      <ChevronRight aria-hidden className="size-3.5" />
                      <button
                        type="button"
                        aria-current={i === path.length - 1 ? "location" : undefined}
                        onClick={() => setPath(path.slice(0, i + 1))}
                        className={cn("inline-flex min-h-11 items-center rounded-lg px-2 hover:bg-ink/[0.05] hover:text-ink", i === path.length - 1 && "text-ink")}
                      >
                        {node.name}
                      </button>
                    </span>
                  ))}
                </nav>

                <div className="grid animate-page gap-x-8 sm:grid-cols-2" key={current?.key ?? "root"}>
                  {current?.region ? regionButton(current.region, `${current.name} 전체`, `이 안에서 어디든 · 장소 ${num(current.region.place_count)}곳`) : null}
                  {nodes
                    .filter((n) => n.placeCount > 0)
                    .map((node) =>
                      node.children.length > 0 || node.region?.level === 2 ? (
                        <button
                          key={node.key}
                          type="button"
                          onClick={() => setPath([...path, node])}
                          className={card}
                          aria-label={`${node.name} 안으로 들어가기, 장소 ${num(node.placeCount)}곳`}
                        >
                          <span className="min-w-0 flex-1">
                            <b className="block truncate text-body-lg font-semibold">{node.name}</b>
                            <span className="tabular block truncate text-body-sm text-muted-foreground">
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
                    <div className="mt-5 grid gap-x-8 sm:grid-cols-2" aria-busy="true">
                      {Array.from({ length: 4 }, (_, i) => (
                        <Skeleton key={i} className="h-[56px] rounded-md" />
                      ))}
                    </div>
                  ) : dongs.length > 0 ? (
                    <div className="mt-5">
                      <p className="mb-2 text-body-sm font-semibold text-ink-2">동네까지 좁히기 · {district.name}의 동 {dongs.length}곳</p>
                      <div className="grid gap-x-8 sm:grid-cols-2">{dongs.map((r) => regionButton(r, r.name, `걸어서 다닐 범위 · 장소 ${num(r.place_count)}곳`))}</div>
                    </div>
                  ) : null
                ) : null}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
