import type { Transport } from "@/lib/api/types";

/**
 * 네이버 지도로 길찾기 넘기기 (docs/27 §13).
 *
 * 웹: https://map.naver.com/p/directions/{출발}/{도착}/{경유지들 또는 -}/{walk|car|transit}
 *     한 지점 = "경도,위도,이름,," — 2026-09-22 크롬에서 도보 · 자동차(경유지 2곳) · 대중교통이 모두 경로를 여는 것을 확인했다.
 *     경유지는 ":" 로 잇는다. (예전 index.nhn?menu=route 주소는 이제 자전거 길찾기로 열려서 쓰지 않는다)
 * 앱: nmap://route/{walk|car|public}?slat=&slng=&sname=&dlat=&dlng=&dname=[&v1lat=&v1lng=&v1name= … v5]&appname=
 *     경유지는 자동차 길찾기에만 있다(최대 5곳). 앱이 없으면 잠시 뒤 웹을 새 탭으로 연다 — 지금 코스 화면은 그대로 남는다.
 */
export interface MapPoint {
  lat: number;
  lng: number;
  name: string;
}

const WEB_MODE: Record<Transport, string> = { walk: "walk", car: "car", transit: "transit" };
const APP_MODE: Record<Transport, string> = { walk: "walk", car: "car", transit: "public" };
const APP_MAX_VIA = 5;

const seg = (p: MapPoint) => `${p.lng.toFixed(6)},${p.lat.toFixed(6)},${encodeURIComponent(p.name)},,`;

export function naverWebDirections(from: MapPoint, to: MapPoint, mode: Transport, via: MapPoint[] = []): string {
  const waypoints = via.length > 0 ? via.map(seg).join(":") : "-";
  return `https://map.naver.com/p/directions/${seg(from)}/${seg(to)}/${waypoints}/${WEB_MODE[mode]}`;
}

export function naverAppDirections(from: MapPoint, to: MapPoint, mode: Transport, via: MapPoint[] = [], appname = "naegajjanday"): string {
  const q = new URLSearchParams({
    slat: String(from.lat),
    slng: String(from.lng),
    sname: from.name,
    dlat: String(to.lat),
    dlng: String(to.lng),
    dname: to.name,
  });
  if (mode === "car") {
    via.slice(0, APP_MAX_VIA).forEach((p, i) => {
      q.set(`v${i + 1}lat`, String(p.lat));
      q.set(`v${i + 1}lng`, String(p.lng));
      q.set(`v${i + 1}name`, p.name);
    });
  }
  q.set("appname", appname);
  return `nmap://route/${APP_MODE[mode]}?${q.toString()}`;
}

/** 휴대폰(터치가 주 입력)인가 — 앱 스킴은 휴대폰에서만 시도한다 */
function isPhone(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(pointer: coarse)").matches && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

/**
 * <a href={웹 주소} target="_blank"> 의 onClick 에 건다. 휴대폰이면 앱을 먼저 열어 보고, 앱이 없어 화면이 그대로면 웹을 연다.
 * 데스크톱은 기본 동작(새 탭으로 웹) 그대로.
 */
export function openInNaverMap(event: { preventDefault: () => void }, from: MapPoint, to: MapPoint, mode: Transport, via: MapPoint[] = []): void {
  if (!isPhone()) return;
  event.preventDefault();
  const web = naverWebDirections(from, to, mode, via);
  const timer = window.setTimeout(() => {
    if (document.visibilityState === "visible") window.open(web, "_blank", "noopener");
  }, 1200);
  document.addEventListener("visibilitychange", () => window.clearTimeout(timer), { once: true });
  window.location.href = naverAppDirections(from, to, mode, via, window.location.hostname || "naegajjanday");
}
