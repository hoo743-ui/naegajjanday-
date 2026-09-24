"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Bell, CalendarDays, Gauge } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useEvents, useQuotas, type QuotaItem } from "@/lib/api/hooks";
import type { EventItem } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { cn } from "@/lib/utils";

/**
 * 오른쪽 위 알림 (docs/47). 화면 격자 · 디자인은 그대로 두고 헤더 끝에 종 하나만 둔다.
 *  - 누구에게나: 축제 · 행사 — **보는 사람의 기기 시각**으로 "오늘 시작 · 오늘 마감 · 내일 · 이번 주말"을 가른다.
 *    마지막으로 본 코스의 동네(jj-last-area)가 있으면 그 동네 것이 먼저.
 *  - 관리자 · 운영자에게만: 한도가 있는 외부 API 가 80% 를 넘었거나 다 썼을 때.
 * 읽은 알림은 이 기기에만 기억한다(jj-notif-seen). 저장이 막혀 있어도 알림은 그대로 보인다.
 */
const SEEN_KEY = "jj-notif-seen";
export const LAST_AREA_KEY = "jj-last-area";
const MAX_EVENTS = 6;
const MAX_NEAR = 4;

const SIDO_SHORT: Record<string, string> = {
  경기도: "경기", 강원도: "강원", 강원특별자치도: "강원", 충청북도: "충북", 충청남도: "충남", 전라북도: "전북", 전북특별자치도: "전북",
  전라남도: "전남", 경상북도: "경북", 경상남도: "경남", 제주도: "제주", 제주특별자치도: "제주", 세종특별자치시: "세종",
};

/** "서울특별시 종로구 창경궁로 185 (와룡동)" → "서울 종로구" */
function shortArea(venue: string | null | undefined): string | null {
  const [sido, sigungu] = (venue ?? "").split(" ");
  if (!sido) return null;
  const short = SIDO_SHORT[sido] ?? sido.replace(/(특별자치시|특별자치도|특별시|광역시)$/, "");
  return [short, sigungu].filter(Boolean).join(" ");
}

interface Notice {
  id: string;
  kind: "event" | "quota";
  title: string;
  line: string;
  href: string;
  tone: "info" | "warn" | "alert";
}

function localYmd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function plusDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

/** 기기 시각으로 본 이 행사의 때: 오늘 시작 · 오늘 마감 · 내일 시작 · 이번 주말 · 진행 중 */
function when(e: EventItem, now: Date): { label: string; rank: number } | null {
  const today = localYmd(now);
  const tomorrow = localYmd(plusDays(now, 1));
  const dow = now.getDay(); // 0 일 ~ 6 토
  const sat = localYmd(plusDays(now, (6 - dow + 7) % 7));
  const sun = localYmd(plusDays(now, dow === 0 ? 0 : 7 - dow));
  if (e.ends_on < today) return null;
  if (e.starts_on === today) return { label: "오늘 시작", rank: 0 };
  if (e.ends_on === today) return { label: "오늘 마감", rank: 1 };
  if (e.starts_on === tomorrow) return { label: "내일 시작", rank: 2 };
  if (e.starts_on <= sun && e.ends_on >= sat) return { label: "이번 주말", rank: 3 };
  if (e.starts_on <= today) return { label: "진행 중", rank: 4 };
  return null;
}

function quotaNotice(q: QuotaItem): Notice | null {
  if (q.status !== "warn" && q.status !== "critical" && q.status !== "exhausted") return null;
  const per = q.period === "month" ? "이번 달" : "오늘";
  const pct = q.share !== null ? `${Math.round(q.share * 100)}%` : "";
  return {
    id: `quota:${q.provider}:${q.status}:${localYmd(new Date())}`,
    kind: "quota",
    title: q.status === "exhausted" ? `${q.name} 한도를 다 썼어요` : `${q.name} 한도 ${pct} 사용`,
    line: `${per} ${q.used.toLocaleString()} / ${q.limit?.toLocaleString() ?? "?"}회${q.where ? ` · 확인: ${q.where}` : ""}`,
    href: "/admin",
    tone: q.status === "warn" ? "warn" : "alert",
  };
}

export function NotificationBell() {
  const { isStaff } = useAuth();
  // 기기 시각은 화면이 뜬 뒤에 읽는다 (서버 렌더와 어긋나지 않게)
  const [now, setNow] = useState<Date | null>(null);
  const [seen, setSeen] = useState<string[]>([]);
  const [area, setArea] = useState<string>("");
  useEffect(() => {
    setNow(new Date());
    setSeen(read<string[]>(SEEN_KEY, []));
    setArea(read<string>(LAST_AREA_KEY, ""));
  }, []);

  const range = now ? { from: localYmd(now), to: localYmd(plusDays(now, 7)) } : {};
  // 기기 날짜를 읽기 전에는 부르지 않는다 (날짜 없이 부르면 전국의 모든 행사가 온다)
  const events = useEvents(range, now !== null);
  const quotas = useQuotas(isStaff);

  const notices = useMemo<Notice[]>(() => {
    const out: Notice[] = [];
    for (const q of quotas.data?.items ?? []) {
      const n = quotaNotice(q);
      if (n) out.push(n);
    }
    if (now && events.data) {
      const picked = events.data.items
        .map((e) => ({ e, w: when(e, now), near: area !== "" && (e.region?.name ?? e.venue ?? "").includes(area.split(" ").at(-1) ?? "") }))
        .filter((x): x is { e: EventItem; w: { label: string; rank: number }; near: boolean } => x.w !== null)
        .sort((a, b) => Number(b.near) - Number(a.near) || a.w.rank - b.w.rank || a.e.ends_on.localeCompare(b.e.ends_on));
      // 최근 본 동네는 넷까지 — 나머지 자리는 전국의 "오늘 시작 · 오늘 마감"에
      const near = picked.filter((x) => x.near).slice(0, MAX_NEAR);
      const rest = picked.filter((x) => !x.near).slice(0, MAX_EVENTS - near.length);
      const shown = [...near, ...rest];
      for (const { e, w, near } of shown) {
        out.push({
          id: `event:${e.id}:${w.label}`,
          kind: "event",
          title: e.title,
          line: [w.label, near ? "최근 본 동네" : null, e.region?.name ?? shortArea(e.venue), e.is_free ? "무료" : null].filter(Boolean).join(" · "),
          href: `/explore?type=festival&q=${encodeURIComponent(e.title)}`,
          tone: w.rank <= 1 ? "warn" : "info",
        });
      }
    }
    return out;
  }, [quotas.data, events.data, now, area]);

  const unseen = notices.filter((n) => !seen.includes(n.id)).length;
  const markSeen = (open: boolean) => {
    if (!open || unseen === 0) return;
    const ids = [...new Set([...seen, ...notices.map((n) => n.id)])].slice(-200);
    setSeen(ids);
    try {
      localStorage.setItem(SEEN_KEY, JSON.stringify(ids));
    } catch {
      /* 저장이 막혀 있으면 이번 방문 동안만 기억한다 */
    }
  };

  return (
    <DropdownMenu onOpenChange={markSeen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={unseen > 0 ? `알림 ${unseen}개` : "알림"}
          className="relative grid size-11 place-items-center rounded-lg text-ink-2 hover:bg-ink/[0.05] hover:text-ink"
        >
          <Bell aria-hidden className="size-5" />
          {unseen > 0 ? (
            <span aria-hidden className="tabular absolute top-1.5 right-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-tomato px-1 text-[10px] leading-none font-bold text-white">
              {unseen > 9 ? "9+" : unseen}
            </span>
          ) : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(22rem,calc(100vw-2rem))] rounded-xl p-1.5">
        <p className="px-2.5 pt-1.5 pb-1 text-caption font-semibold text-muted-foreground">
          {now ? `${now.getMonth() + 1}월 ${now.getDate()}일 기준 · 이 기기 시각` : "알림"}
        </p>
        {notices.length === 0 ? (
          <p className="px-2.5 py-4 text-body-sm text-muted-foreground">{events.isPending ? "불러오는 중…" : "이번 주에 알려 드릴 축제 · 행사가 없어요."}</p>
        ) : (
          <ul className="grid max-h-[60vh] gap-0.5 overflow-y-auto">
            {notices.map((n) => {
              const Icon = n.kind === "quota" ? Gauge : CalendarDays;
              return (
                <li key={n.id}>
                  <Link href={n.href} className="flex gap-2.5 rounded-lg px-2.5 py-2 hover:bg-ink/[0.04]">
                    <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", n.tone === "alert" ? "text-tomato-deep" : n.tone === "warn" ? "text-gold-ink" : "text-blue-deep")} />
                    <span className="min-w-0">
                      <b className={cn("block text-body-sm font-bold text-ink", !seen.includes(n.id) && "after:ml-1.5 after:inline-block after:size-1.5 after:rounded-full after:bg-tomato after:align-middle after:content-['']")}>{n.title}</b>
                      <span className="block text-caption text-muted-foreground">{n.line}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        <Link href="/explore?type=festival" className="mt-1 block rounded-lg px-2.5 py-2 text-center text-body-sm font-semibold text-blue-deep hover:bg-blue-soft">
          축제 · 행사 전체 보기
        </Link>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
