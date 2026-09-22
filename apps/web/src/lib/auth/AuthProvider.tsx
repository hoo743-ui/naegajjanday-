"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { identify, resetAnalytics } from "@/lib/analytics";
import { qk, useMe } from "@/lib/api/hooks";
import type { Me } from "@/lib/api/types";
import { IS_MOCKING } from "@/lib/api/client";
import { getAccessToken, hasSessionHint, logout as logoutRequest, refreshAccessToken, subscribeToken } from "./token";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  me: Me | null;
  /** admin 또는 operator */
  isStaff: boolean;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  status: "loading",
  me: null,
  isStaff: false,
  logout: async () => undefined,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [token, setToken] = useState<string | null>(() => getAccessToken());
  const [restoring, setRestoring] = useState(true);

  useEffect(() => subscribeToken(setToken), []);

  // 새로고침 직후: 메모리에 access token 이 없으므로 refresh 쿠키로 한 번 복원을 시도한다.
  // 로그인한 흔적이 없는 방문자는 건너뛴다 (돌아올 답은 401 뿐이다)
  useEffect(() => {
    let alive = true;
    if (!IS_MOCKING && !hasSessionHint()) {
      setRestoring(false);
      return;
    }
    void refreshAccessToken().finally(() => {
      if (alive) setRestoring(false);
    });
    return () => {
      alive = false;
    };
  }, []);

  const meQuery = useMe(!restoring && token !== null);
  const me = token ? (meQuery.data ?? null) : null;

  useEffect(() => {
    if (me) identify(me.id, { role: me.role, provider: me.provider });
  }, [me]);

  // 절대 reject 하지 않는다: 서버 호출이 실패해도 이 브라우저의 로그인 상태(토큰·내 정보 캐시)는 반드시 지운다.
  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } catch {
      // logoutRequest 는 던지지 않지만, 던지더라도 아래 정리는 해야 한다
    } finally {
      // ["me"] 접두사 → 내 정보 · 취향 · 저장한 코스까지 함께 지운다 (다음 사용자에게 보이면 안 된다)
      client.removeQueries({ queryKey: qk.me });
      try {
        resetAnalytics();
      } catch {
        // 분석 도구 오류가 로그아웃을 막으면 안 된다
      }
    }
  }, [client]);

  const value = useMemo<AuthContextValue>(() => {
    const status: AuthStatus =
      restoring || (token !== null && meQuery.isPending) ? "loading" : me ? "authenticated" : "anonymous";
    return { status, me, isStaff: me?.role === "admin" || me?.role === "operator", logout };
  }, [restoring, token, meQuery.isPending, me, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
