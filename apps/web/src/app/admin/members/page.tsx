"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { adminTime as when } from "@/lib/admin-time";
import { MEMBERS_PAGE, useMembers } from "@/lib/api/admin";
import { num } from "@/lib/format";
import { cn } from "@/lib/utils";

const ROLE: Record<string, string> = { admin: "관리자", operator: "운영자", user: "회원" };
const STATUS: Record<string, string> = { active: "", suspended: "정지", deleting: "탈퇴 중" };

/** 회원 목록 (docs/50): 가입한 계정 전부 — 가입 수단 · 로그인 · 코스 · 최근 IP. 최근 가입순. */
export default function AdminMembersPage() {
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const members = useMembers(q, page);
  const d = members.data;
  const pages = d ? Math.max(1, Math.ceil(d.total / MEMBERS_PAGE)) : 1;

  return (
    <>
      <AdminPageHeader title="회원 목록" description={d ? `가입 계정 ${num(d.total)}개 · 최근 가입순` : "가입 계정 · 최근 가입순"} />
      <Panel>
        <form
          role="search"
          className="mb-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(0);
            setQ(draft.trim());
          }}
        >
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="아이디 · 닉네임 · 이메일" aria-label="회원 검색" className="h-11 rounded-xl pl-9" />
          </div>
          <Button type="submit" variant="outline" className="h-11 rounded-xl">
            찾기
          </Button>
        </form>

        {members.isError ? (
          <ErrorState error={members.error} onRetry={() => void members.refetch()} />
        ) : !d ? (
          <Skeleton className="h-[320px] rounded-2xl" />
        ) : d.items.length === 0 ? (
          <EmptyState size="sm" title={q ? "찾는 회원이 없어요" : "아직 가입한 회원이 없어요"} />
        ) : (
          <div className="overflow-x-auto">
            <table className="tabular w-full min-w-[960px] text-body-sm">
              <caption className="sr-only">회원 목록</caption>
              <thead>
                <tr className="border-b border-line text-left text-caption font-semibold text-muted-foreground">
                  {["회원", "이메일", "가입 수단", "가입", "마지막 로그인", "로그인", "코스 생성 · 저장", "최근 IP", "마지막 방문"].map((h) => (
                    <th key={h} scope="col" className="px-2 py-2 whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.items.map((m) => (
                  <tr key={m.id} className={cn("border-b border-line/60 align-top", m.status !== "active" && "text-muted-foreground")}>
                    <th scope="row" className="px-2 py-2 text-left font-semibold whitespace-nowrap">
                      {m.login_id ?? m.nickname ?? "(이름 없음)"}
                      {m.login_id && m.nickname && m.nickname !== m.login_id ? <span className="ml-1 font-normal text-ink-2">{m.nickname}</span> : null}
                      <span className="mt-0.5 block text-caption font-medium text-muted-foreground">
                        {ROLE[m.role] ?? m.role}
                        {STATUS[m.status] ? ` · ${STATUS[m.status]}` : ""}
                      </span>
                    </th>
                    <td className="px-2 py-2 text-ink-2">{m.email ?? "-"}</td>
                    <td className="px-2 py-2 text-ink-2">{m.providers.join(", ") || "-"}</td>
                    <td className="px-2 py-2 whitespace-nowrap">{when(m.created_at)}</td>
                    <td className="px-2 py-2 whitespace-nowrap">{when(m.last_login_at)}</td>
                    <td className="px-2 py-2 text-right">{num(m.logins)}</td>
                    <td className="px-2 py-2 text-right">
                      {num(m.courses_generated)} · {num(m.courses_saved)}
                    </td>
                    <td className="px-2 py-2 font-mono text-caption">{m.last_ip ?? "-"}</td>
                    <td className="px-2 py-2 whitespace-nowrap">{when(m.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {d && pages > 1 ? (
          <div className="mt-4 flex items-center justify-end gap-2 text-body-sm">
            <Button type="button" size="sm" variant="outline" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              이전
            </Button>
            <span className="tabular text-ink-2">
              {page + 1} / {pages}
            </span>
            <Button type="button" size="sm" variant="outline" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
              다음
            </Button>
          </div>
        ) : null}
      </Panel>
    </>
  );
}
