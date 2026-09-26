"use client";

import Link from "next/link";
import { Bookmark, BookmarkCheck, CalendarPlus, Check, ExternalLink, Share2, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Stop } from "@/lib/api/types";
import { clock } from "@/lib/format";
import { cn } from "@/lib/utils";
import { BottomSheet } from "./BottomSheet";
import { kakaoSearchUrl, mayNeedBooking } from "./stop-links";

interface ConfirmSheetProps {
  open: boolean;
  onClose: () => void;
  stops: Stop[];
  /** 확정한 장소 id (이 곳으로 할게요 · 이 코스로 할게요) */
  fixed: string[];
  saved: boolean;
  saving: boolean;
  onSave: () => void;
  onShare: () => void;
  onCalendar: () => void;
  onOutbound: (position: number) => void;
  onCancel: () => void;
}

/**
 * 오늘 코스 확정 (2026-09-26 창업자 "코스를 선택함에 있어서 결국엔 눌렀을 때 신청옵션으로 들어가야"):
 * 고른 코스가 내 계획이 된 자리. 몇 곳을 확정했는지 → 가기 전에 할 일(예약 · 메뉴 확인은 그 가게 페이지로) → 캘린더 · 공유 · 저장.
 * 예약 · 결제는 우리가 하지 않는다 (docs/61) — 예약이 필요한지도 자료가 없어, 대개 예약하는 종류만 "필요할 수 있어요"라고 한다.
 */
export function ConfirmSheet({ open, onClose, stops, fixed, saved, saving, onSave, onShare, onCalendar, onOutbound, onCancel }: ConfirmSheetProps) {
  const count = stops.filter((s) => fixed.includes(s.place.id)).length;
  return (
    <BottomSheet
      open={open}
      onClose={onClose}
      title="오늘 코스 확정"
      description={`${stops.length}곳 중 ${count}곳 확정 · 다시 짜도 확정한 곳은 남아요.`}
      footer={
        <div className="grid gap-2">
          {saved ? (
            <Button asChild variant="brand" size="xl" className="w-full">
              <Link href="/my">
                <BookmarkCheck aria-hidden /> 저장됨 · 내 코스 보기
              </Link>
            </Button>
          ) : (
            <Button type="button" variant="brand" size="xl" className="w-full" onClick={onSave} disabled={saving}>
              <Bookmark aria-hidden /> {saving ? "저장하는 중…" : "내 코스에 저장하기"}
            </Button>
          )}
          <button type="button" onClick={onCancel} className="mx-auto min-h-11 px-3 text-body-sm font-semibold text-muted-foreground hover:text-ink">
            확정 취소
          </button>
        </div>
      }
    >
      <div className="grid grid-cols-2 gap-2">
        <button type="button" onClick={onCalendar} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-ink/20 bg-white text-body-sm font-semibold text-ink hover:border-ink-2">
          <CalendarPlus aria-hidden className="size-4" /> 캘린더에 넣기
        </button>
        <button type="button" onClick={onShare} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-ink/20 bg-white text-body-sm font-semibold text-ink hover:border-ink-2">
          <Share2 aria-hidden className="size-4" /> 같이 갈 사람에게 공유
        </button>
      </div>

      <h3 className="mt-5 mb-2 text-body-sm font-semibold text-ink-2">가기 전에 예약 · 메뉴 확인</h3>
      <ol className="grid gap-1.5">
        {stops.map((s) => {
          const on = fixed.includes(s.place.id);
          const booking = mayNeedBooking(s.place.category);
          return (
            <li key={s.place.id} className="flex items-center gap-3 rounded-xl border border-line bg-white py-2 pr-2 pl-3">
              <span className={cn("grid size-6 shrink-0 place-items-center rounded-full text-caption font-bold", on ? "bg-tomato text-white" : "bg-paper-2 text-ink-2")} aria-label={on ? "확정" : "아직 확정 안 함"}>
                {on ? <Check aria-hidden className="size-3.5" /> : s.position}
              </span>
              <span className="min-w-0 flex-1">
                <b className="block truncate text-body-sm font-bold text-ink">{s.place.name}</b>
                <span className="tabular block text-caption text-muted-foreground">
                  {clock(s.arrive_at)} ~ {clock(s.leave_at)}
                </span>
                {booking ? (
                  <span className="flex items-center gap-1 text-caption font-semibold text-pink-deep">
                    <TriangleAlert aria-hidden className="size-3 shrink-0" /> 예약 · 예매가 필요할 수 있어요
                  </span>
                ) : null}
              </span>
              {s.place.kind !== "event" ? (
                <a
                  href={kakaoSearchUrl(s.place)}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => onOutbound(s.position)}
                  aria-label={`${s.place.name} 예약 · 메뉴 보기`}
                  className="inline-flex min-h-10 shrink-0 items-center gap-1 rounded-lg px-2.5 text-body-sm font-semibold text-blue-deep hover:bg-blue-soft"
                >
                  {booking ? "예약" : "메뉴"} <ExternalLink aria-hidden className="size-3.5" />
                </a>
              ) : null}
            </li>
          );
        })}
      </ol>
    </BottomSheet>
  );
}
