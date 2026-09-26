"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * "이 코스로 할게요" (2026-09-26 창업자: 고르는 개념이 있어야): 확정한 코스와 그때의 장소들.
 * 장소 고정(pins)은 이 탭 동안만 남지만, 확정은 다시 열어도 남아야 한다 → localStorage, 코스 id 별로.
 * 서버에 따로 두지 않는다 — 저장(로그인)은 "코스 저장하기"가 한다.
 */
const KEY = "jj-confirmed";
const MAX = 30;
type Store = Record<string, string[]>;
const listeners = new Set<() => void>();
let cache: Store | null = null;
const EMPTY: Store = {};

function read(): Store {
  if (cache) return cache;
  try {
    const raw = localStorage.getItem(KEY);
    cache = raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    cache = {};
  }
  return cache;
}

function write(next: Store) {
  const ids = Object.keys(next);
  // 오래된 것부터 버린다 (넣은 순서 = 키 순서)
  cache = ids.length > MAX ? Object.fromEntries(ids.slice(-MAX).map((id) => [id, next[id]!])) : next;
  try {
    localStorage.setItem(KEY, JSON.stringify(cache));
  } catch {
    // 저장이 막혀 있으면 이 화면에서만 기억한다
  }
  listeners.forEach((fn) => fn());
}

/** 이 코스를 확정했는지 · 확정한 장소 id · 확정 / 한 곳 풀기 / 확정 취소 */
export function useConfirmed(courseId: string) {
  const store = useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    read,
    () => EMPTY,
  );
  const placeIds = store[courseId];
  const confirm = useCallback(
    (ids: string[]) => {
      const rest = { ...read() };
      delete rest[courseId];
      write({ ...rest, [courseId]: ids });
    },
    [courseId],
  );
  const release = useCallback(
    (placeId: string) => {
      const now = read();
      const ids = now[courseId];
      if (!ids) return;
      write({ ...now, [courseId]: ids.filter((id) => id !== placeId) });
    },
    [courseId],
  );
  const cancel = useCallback(() => {
    const rest = { ...read() };
    delete rest[courseId];
    write(rest);
  }, [courseId]);
  return { confirmed: placeIds !== undefined, placeIds: placeIds ?? [], confirm, release, cancel };
}
