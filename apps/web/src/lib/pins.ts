"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * 고정한 장소 (편집 가능한 초안, docs/42): "이 장소 고정"을 누른 곳은 다시 짜도 남는다.
 * 코스가 다시 짜이면 id 가 바뀌므로 코스가 아니라 장소 id 로, 이 탭(세션) 동안 기억한다.
 */
const KEY = "jj-pins";
const listeners = new Set<() => void>();
let cache: string[] | null = null;

function read(): string[] {
  if (cache) return cache;
  try {
    const raw = sessionStorage.getItem(KEY);
    cache = raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    cache = [];
  }
  return cache;
}
const EMPTY: string[] = [];

function write(next: string[]) {
  cache = next;
  try {
    sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // 저장소를 못 쓰면 이 화면에서만 기억한다
  }
  listeners.forEach((fn) => fn());
}

export function usePins() {
  const pins = useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    read,
    () => EMPTY,
  );
  const toggle = useCallback((placeId: string) => {
    const now = read();
    // 서버는 최대 6곳까지 받는다
    write(now.includes(placeId) ? now.filter((id) => id !== placeId) : [...now, placeId].slice(-6));
  }, []);
  return { pins, toggle };
}
