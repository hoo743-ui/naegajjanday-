"use client";

import { useState } from "react";
import { ExternalLink, LocateFixed, MapPin, Route } from "lucide-react";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import type { Stop, Transport } from "@/lib/api/types";
import { naverAppDirections, naverWebDirections, type MapPoint } from "@/lib/naver-map";
import { cn } from "@/lib/utils";
import { BottomSheet } from "./BottomSheet";

type From = { kind: "here" } | { kind: "stop"; position: number };

interface DirectionsSheetProps {
  open: boolean;
  onClose: () => void;
  courseId: string;
  stops: Stop[];
  /** 가려는 곳 */
  to: Stop;
  mode: Transport;
}

const point = (s: Stop): MapPoint => ({ lat: s.place.lat, lng: s.place.lng, name: s.place.name });
const WEB_MODE: Record<Transport, string> = { walk: "walk", car: "car", transit: "transit" };

function isPhone(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

/** 휴대폰이면 네이버지도 앱을 먼저, 없으면 웹. 데스크톱은 새 탭으로 웹 */
function openNaver(from: MapPoint | null, to: MapPoint, mode: Transport) {
  const seg = (p: MapPoint) => `${p.lng.toFixed(6)},${p.lat.toFixed(6)},${encodeURIComponent(p.name)},,`;
  // 출발지를 모르면(위치 권한 거절) 도착지만 넘긴다 — 네이버지도가 현재 위치로 출발지를 채운다
  const web = from ? naverWebDirections(from, to, mode) : `https://map.naver.com/p/directions/-/${seg(to)}/-/${WEB_MODE[mode]}`;
  if (!isPhone() || !from) {
    window.open(web, "_blank", "noopener");
    return;
  }
  const timer = window.setTimeout(() => {
    if (document.visibilityState === "visible") window.open(web, "_blank", "noopener");
  }, 1200);
  document.addEventListener("visibilitychange", () => window.clearTimeout(timer), { once: true });
  window.location.href = naverAppDirections(from, to, mode, [], window.location.hostname || "naegajjanday");
}

/**
 * 길찾기 (docs/42): 버튼 하나로 시작해서 질문 하나 — "어디서 출발할까요?" → 네이버지도 열기.
 * 첫 장소면 현재 위치, 아니면 이전 장소가 기본. 중간 장소를 건너뛰거나 순서를 바꿔 다닐 때는 "다른 코스 장소"에서 고른다.
 */
export function DirectionsSheet({ open, onClose, courseId, stops, to, mode }: DirectionsSheetProps) {
  const index = stops.findIndex((s) => s.position === to.position);
  const prev = index > 0 ? stops[index - 1] : undefined;
  const others = stops.filter((s) => s.position !== to.position && s.position !== prev?.position);
  const [from, setFrom] = useState<From>(prev ? { kind: "stop", position: prev.position } : { kind: "here" });
  const [showOthers, setShowOthers] = useState(false);
  const [locating, setLocating] = useState(false);

  const go = () => {
    track("directions_opened", { course_id: courseId, position: to.position, from: from.kind === "here" ? "here" : from.position === prev?.position ? "prev" : "other" });
    if (from.kind === "stop") {
      const start = stops.find((s) => s.position === from.position);
      openNaver(start ? point(start) : null, point(to), mode);
      onClose();
      return;
    }
    // 현재 위치: 브라우저에 한 번 묻는다. 거절하거나 못 찾으면 네이버지도가 스스로 현재 위치를 쓴다
    if (!("geolocation" in navigator)) {
      openNaver(null, point(to), mode);
      onClose();
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        openNaver({ lat: pos.coords.latitude, lng: pos.coords.longitude, name: "현재 위치" }, point(to), mode);
        onClose();
      },
      () => {
        setLocating(false);
        openNaver(null, point(to), mode);
        onClose();
      },
      { timeout: 6000, maximumAge: 60_000 },
    );
  };

  const option = (key: string, on: boolean, onPick: () => void, icon: React.ReactNode, title: string, sub?: string) => (
    <button
      key={key}
      type="button"
      role="radio"
      aria-checked={on}
      onClick={onPick}
      className={cn("flex min-h-14 w-full items-center gap-3 rounded-xl border px-4 py-2.5 text-left transition-colors", on ? "border-tomato bg-tomato-soft" : "border-ink/15 bg-white hover:border-ink/40")}
    >
      <span className={cn("grid size-9 shrink-0 place-items-center rounded-full", on ? "bg-tomato text-white" : "bg-paper-2 text-ink-2")}>{icon}</span>
      <span className="min-w-0">
        <b className="block truncate text-body font-semibold text-ink">{title}</b>
        {sub ? <span className="block truncate text-caption text-muted-foreground">{sub}</span> : null}
      </span>
    </button>
  );

  return (
    <BottomSheet
      open={open}
      onClose={onClose}
      title="어디서 출발할까요?"
      description={`도착: ${to.place.name}`}
      footer={
        <Button type="button" variant="brand" size="xl" className="w-full" onClick={go} disabled={locating}>
          {locating ? "현재 위치를 찾는 중…" : "네이버지도 열기"} <ExternalLink aria-hidden />
        </Button>
      }
    >
      <div role="radiogroup" aria-label="출발지" className="grid gap-2">
        {option("here", from.kind === "here", () => setFrom({ kind: "here" }), <LocateFixed aria-hidden className="size-4" />, "현재 위치")}
        {prev ? option("prev", from.kind === "stop" && from.position === prev.position, () => setFrom({ kind: "stop", position: prev.position }), <MapPin aria-hidden className="size-4" />, `이전 장소: ${prev.place.name}`, `${prev.position}번째 곳`) : null}
        {others.length > 0 ? (
          <>
            <button type="button" aria-expanded={showOthers} onClick={() => setShowOthers((v) => !v)} className="flex min-h-12 w-full items-center gap-3 rounded-xl border border-dashed border-ink/25 px-4 text-left text-body font-semibold text-ink-2 hover:border-ink/50">
              <Route aria-hidden className="size-4" /> 다른 코스 장소
            </button>
            {showOthers ? (
              <div className="grid gap-2 pl-3">
                {others.map((s) =>
                  option(`s${s.position}`, from.kind === "stop" && from.position === s.position, () => setFrom({ kind: "stop", position: s.position }), <b className="tabular text-caption">{s.position}</b>, s.place.name),
                )}
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </BottomSheet>
  );
}
