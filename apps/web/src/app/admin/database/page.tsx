"use client";

import { useState } from "react";
import { Archive, Database, HardDrive, Trash2 } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { FormMessage } from "@/components/admin/Field";
import { StatCard } from "@/components/admin/StatCard";
import { ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useDatabaseOverview, useDeleteBackup, usePurgeCourses, usePurgeVisits, useStartBackup } from "@/lib/api/admin";
import type { ApiError } from "@/lib/api/client";
import { num } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";

const VISIT_KEEP = [90, 180, 365] as const;

function bytes(value: number | null | undefined): string {
  if (value == null) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = value;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i >= 3 ? 2 : 0)} ${units[i]}`;
}

function when(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

interface Confirm {
  title: string;
  description: string;
  cta: string;
  run: () => Promise<unknown>;
}

/**
 * 설정 · DB (docs/50): DB 가 무엇을 얼마나 들고 있는지, 그리고 운영자가 할 수 있는 정리 몇 가지.
 * 저장한 코스 · 계정 · 장소는 여기서 지우지 않는다 — 보관 기간이 지난 '저장 안 한 코스', 오래된 방문 기록, 백업 파일만.
 */
export default function AdminDatabasePage() {
  const q = useDatabaseOverview();
  const purgeCourses = usePurgeCourses();
  const purgeVisits = usePurgeVisits();
  const backup = useStartBackup();
  const removeBackup = useDeleteBackup();
  const [keepDays, setKeepDays] = useState<(typeof VISIT_KEEP)[number]>(180);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (q.isError) {
    return (
      <>
        <AdminPageHeader title="설정 · DB" />
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </>
    );
  }
  const d = q.data;

  const run = async () => {
    if (!confirm) return;
    setBusy(true);
    setError(null);
    try {
      await confirm.run();
      setConfirm(null);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };

  const askVisits = async () => {
    setNotice(null);
    const preview = await purgeVisits.mutateAsync({ olderThanDays: keepDays, dryRun: true }).catch((e: ApiError) => {
      setError(e);
      return null;
    });
    if (!preview) return;
    if (preview.matched === 0) {
      setNotice(`${keepDays}일보다 오래된 방문 기록이 없어요.`);
      return;
    }
    setConfirm({
      title: `방문 기록 ${num(preview.matched)}건을 지울까요?`,
      description: `${keepDays}일보다 오래된 방문 기록이에요. 지우면 그 기간의 날짜별 방문자 통계도 사라지고, 되돌릴 수 없어요.`,
      cta: "지우기",
      run: async () => {
        const r = await purgeVisits.mutateAsync({ olderThanDays: keepDays, dryRun: false });
        setNotice(`방문 기록 ${num(r.deleted)}건을 지웠어요.`);
      },
    });
  };

  return (
    <>
      <AdminPageHeader title="설정 · DB" description="DB 크기와 테이블, 오래된 기록 정리, 백업" />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="DB 크기" icon={Database} loading={q.isPending} value={d ? bytes(d.size_bytes) : "-"} hint={d ? (d.engine === "sqlite" ? "SQLite 파일" : "PostgreSQL") : undefined} />
        <StatCard label="디스크 여유" icon={HardDrive} loading={q.isPending} tone={d && d.size_bytes && d.disk_free_bytes && d.disk_free_bytes < d.size_bytes * 1.3 ? "warn" : "default"} value={d ? bytes(d.disk_free_bytes) : "-"} hint="백업하려면 DB 크기의 1.3배 필요" />
        <StatCard label="정리할 코스" icon={Trash2} loading={q.isPending} value={d ? num(d.expired_unsaved_courses) : "-"} hint={d ? `저장 안 하고 ${d.unsaved_course_ttl_hours}시간 지난 것` : undefined} />
        <StatCard label="백업" icon={Archive} loading={q.isPending} value={d ? `${d.backups.length}개` : "-"} hint={d?.backup_running ? "지금 백업하는 중…" : d?.backups[0] ? `마지막 ${when(d.backups[0].created_at)}` : "아직 없어요"} />
      </div>

      {notice ? <p role="status" className="mt-4 rounded-2xl bg-soft px-4 py-3 text-body-sm text-ink-2">{notice}</p> : null}
      {error && !confirm ? <FormMessage tone="error">{mascotCopyForError(error).description}</FormMessage> : null}

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Panel title="테이블" description="행 수">
          {!d ? (
            <Skeleton className="h-[320px] rounded-2xl" />
          ) : (
            <table className="tabular w-full text-body-sm">
              <caption className="sr-only">테이블별 행 수</caption>
              <tbody>
                {d.tables.map((t) => (
                  <tr key={t.name} className="border-b border-line/60">
                    <th scope="row" className="py-2 text-left font-medium text-ink-2">
                      {t.label} <span className="text-caption text-muted-foreground">{t.name}</span>
                    </th>
                    <td className="py-2 text-right font-semibold text-ink">{num(t.rows)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <div className="grid content-start gap-5">
          <Panel title="저장 안 한 코스 정리" description="만들고 저장하지 않은 코스는 보관 기간이 지나면 지워요. 저장한 코스 · 코스 생성 통계(추천 기록)는 그대로예요.">
            <Button
              type="button"
              variant="outline"
              disabled={!d || d.expired_unsaved_courses === 0}
              onClick={() =>
                d &&
                setConfirm({
                  title: `코스 ${num(d.expired_unsaved_courses)}개를 정리할까요?`,
                  description: `저장하지 않고 ${d.unsaved_course_ttl_hours}시간이 지난 코스예요. 그 코스의 공유 링크도 더는 열리지 않아요.`,
                  cta: "정리하기",
                  run: async () => {
                    const r = await purgeCourses.mutateAsync({ dryRun: false });
                    setNotice(`코스 ${num(r.deleted)}개를 정리했어요.`);
                  },
                })
              }
            >
              {d && d.expired_unsaved_courses === 0 ? "정리할 코스가 없어요" : "정리하기"}
            </Button>
          </Panel>

          <Panel title="방문 기록 정리" description={d ? `전체 ${num(d.visits_total)}건 · 가장 오래된 기록 ${when(d.oldest_visit)}` : "방문 기록"}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-body-sm text-ink-2">이보다 오래된 기록:</span>
              {VISIT_KEEP.map((n) => (
                <Button key={n} type="button" size="sm" variant={keepDays === n ? "brand" : "outline"} aria-pressed={keepDays === n} onClick={() => setKeepDays(n)}>
                  {n}일
                </Button>
              ))}
              <Button type="button" variant="outline" disabled={purgeVisits.isPending} onClick={() => void askVisits()}>
                {purgeVisits.isPending ? "세는 중…" : "몇 건인지 보고 지우기"}
              </Button>
            </div>
          </Panel>

          <Panel title="백업" description="DB 파일을 같은 디스크의 backups 폴더에 복사해요. 최근 2개만 남아요.">
            {d?.engine === "postgresql" ? (
              <p className="text-body-sm text-ink-2">PostgreSQL 은 호스팅의 스냅샷 백업을 써 주세요.</p>
            ) : (
              <div className="grid gap-3">
                <Button
                  type="button"
                  variant="brand"
                  disabled={!d || d.backup_running || backup.isPending}
                  onClick={() => {
                    setNotice(null);
                    setError(null);
                    backup.mutate(undefined, { onSuccess: () => setNotice("백업을 시작했어요. 끝나면 목록에 나타나요."), onError: setError });
                  }}
                >
                  {d?.backup_running ? "백업하는 중…" : "지금 백업하기"}
                </Button>
                {d?.backups.length ? (
                  <ul className="grid gap-2">
                    {d.backups.map((b) => (
                      <li key={b.name} className="flex items-center justify-between gap-3 rounded-2xl border border-line px-3 py-2 text-body-sm">
                        <span className="min-w-0 truncate">
                          {when(b.created_at)} · <span className="tabular text-ink-2">{bytes(b.size_bytes)}</span>
                        </span>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          aria-label={`${b.name} 삭제`}
                          onClick={() =>
                            setConfirm({
                              title: "이 백업을 지울까요?",
                              description: `${when(b.created_at)}에 만든 백업(${bytes(b.size_bytes)})이에요. 지우면 되돌릴 수 없어요.`,
                              cta: "지우기",
                              run: () => removeBackup.mutateAsync(b.name),
                            })
                          }
                        >
                          <Trash2 className="size-4" aria-hidden />
                        </Button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            )}
          </Panel>
        </div>
      </div>

      <Dialog open={confirm !== null} onOpenChange={(v) => !v && !busy && setConfirm(null)}>
        <DialogContent className="rounded-card">
          <DialogHeader>
            <DialogTitle>{confirm?.title}</DialogTitle>
            <DialogDescription>{confirm?.description}</DialogDescription>
          </DialogHeader>
          {error ? <FormMessage tone="error">{mascotCopyForError(error).description}</FormMessage> : null}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={() => setConfirm(null)}>
              취소
            </Button>
            <Button type="button" variant="destructive" disabled={busy} onClick={() => void run()}>
              {busy ? "하는 중…" : confirm?.cta}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
