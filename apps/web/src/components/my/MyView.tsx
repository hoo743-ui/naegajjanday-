"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { LogOut, Pencil } from "lucide-react";
import { z } from "zod";
import { EmptyState } from "@/components/mascot/EmptyState";
import { Jjani } from "@/components/mascot/Jjani";
import { JjaniLoader } from "@/components/mascot/JjaniLoader";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDeleteMe, useUpdateMe } from "@/lib/api/hooks";
import type { Me, OAuthProvider } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { setAccessToken } from "@/lib/auth/token";
import { mascotCopyForError } from "@/lib/mascot-copy";
import { PreferencesEditor } from "./PreferencesEditor";
import { SavedCourses } from "./SavedCourses";

const PROVIDER_LABEL: Record<OAuthProvider, string> = { kakao: "카카오", naver: "네이버", google: "Google" };

export function MyView() {
  const { status, me, logout } = useAuth();
  const router = useRouter();
  /** 로그아웃·탈퇴로 스스로 나가는 중에는 홈으로 간다 → 로그인 화면으로 되돌리지 않는다 */
  const leaving = useRef(false);

  // 미들웨어는 로그인 여부를 볼 수 없다(refresh 쿠키가 API 호스트에만 있다) → 가드는 여기서 한다.
  useEffect(() => {
    if (status === "anonymous" && !leaving.current) router.replace("/login?next=%2Fmy");
  }, [status, router]);

  if (status === "loading") return <JjaniLoader stages={["내 코스를 꺼내는 중…"]} />;
  if (status === "anonymous" || !me) {
    return (
      <EmptyState mood="hi" size="lg" title="로그인하고 코스를 모아 보세요" description="저장한 코스를 다시 꺼내 보고, 다녀온 곳으로 취향을 맞춰 드려요." className="min-h-[60vh]">
        <Button asChild variant="brand" size="md">
          <Link href="/login?next=/my">로그인하기</Link>
        </Button>
        <Button asChild variant="soft" size="md">
          <Link href="/plan">가입 없이 코스 짜기</Link>
        </Button>
      </EmptyState>
    );
  }

  // 로그인 수단을 모르면(운영자가 만든 계정 등) 그 줄은 통째로 숨긴다 — " 로그인" 같은 빈 문구를 만들지 않는다
  const accountLine = [me.provider ? `${PROVIDER_LABEL[me.provider] ?? me.provider} 로그인` : null, me.email].filter(Boolean).join(" · ");

  return (
    <div className="wrap grid max-w-[920px] gap-6 py-8 sm:py-12">
      <section aria-label="내 프로필" className="flex flex-wrap items-center gap-4 border-b border-ink/10 pb-8">
        <Jjani mood="wink" size={84} />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[clamp(26px,3.4vw,34px)] font-bold tracking-[-0.03em]">{me.nickname} 님의 하루들</h1>
          {accountLine ? <p className="truncate text-sm font-bold text-ink-2">{accountLine}</p> : null}
        </div>
        <div className="flex gap-2">
          <NicknameDialog me={me} />
          <Button
            type="button"
            variant="soft"
            size="md"
            className="bg-white"
            onClick={() => {
              leaving.current = true;
              // logout() 은 실패해도 로컬 로그인 상태를 지우고 끝난다 → 어떤 경우에도 홈으로 나간다
              void logout()
                .catch(() => undefined)
                .finally(() => router.replace("/"));
            }}
          >
            <LogOut aria-hidden /> 로그아웃
          </Button>
        </div>
      </section>

      <section aria-labelledby="saved-title">
        <div className="mb-3 flex items-end justify-between">
          <h2 id="saved-title" className="text-xl font-extrabold tracking-tight font-serif">
            저장한 코스
          </h2>
          <Button asChild variant="link" className="px-0 font-extrabold">
            <Link href="/plan">새 코스 짜기</Link>
          </Button>
        </div>
        <SavedCourses />
      </section>

      <section aria-labelledby="pref-title">
        <h2 id="pref-title" className="mb-3 text-xl font-extrabold tracking-tight font-serif">
          내 취향
        </h2>
        <PreferencesEditor />
      </section>

      <section aria-labelledby="leave-title" className="rounded-card border border-line bg-white p-6">
        <h2 id="leave-title" className="text-base font-extrabold">
          회원 탈퇴
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">탈퇴를 신청하면 30일 동안 보관한 뒤 모든 개인정보와 저장한 코스를 완전히 지워요. 그 안에 다시 로그인하면 취소돼요.</p>
        <LeaveDialog
          onLeaving={() => {
            leaving.current = true;
          }}
        />
      </section>
    </div>
  );
}

const nicknameSchema = z.object({
  nickname: z.string().trim().min(2, "두 글자 이상으로 지어 주세요").max(16, "16자까지 쓸 수 있어요"),
});

function NicknameDialog({ me }: { me: Me }) {
  const [open, setOpen] = useState(false);
  const update = useUpdateMe();
  const form = useForm<z.infer<typeof nicknameSchema>>({ resolver: zodResolver(nicknameSchema), defaultValues: { nickname: me.nickname } });
  const error = form.formState.errors.nickname?.message ?? (update.error ? mascotCopyForError(update.error).description : undefined);

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (v) {
          form.reset({ nickname: me.nickname });
          update.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" variant="soft" size="md" className="bg-white">
          <Pencil aria-hidden /> 닉네임
        </Button>
      </DialogTrigger>
      <DialogContent className="rounded-card">
        <form onSubmit={form.handleSubmit((values) => update.mutate(values, { onSuccess: () => setOpen(false) }))} noValidate className="grid gap-4">
          <DialogHeader>
            <DialogTitle>닉네임 바꾸기</DialogTitle>
            <DialogDescription>짠이가 부를 이름이에요.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="nickname">닉네임</Label>
            <Input id="nickname" autoComplete="nickname" aria-invalid={Boolean(error)} aria-describedby={error ? "nickname-error" : undefined} {...form.register("nickname")} />
            {error ? (
              <p id="nickname-error" role="alert" className="text-sm font-bold text-danger">
                {error}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="submit" variant="brand" size="md" disabled={update.isPending}>
              {update.isPending ? "저장하는 중…" : "저장"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function LeaveDialog({ onLeaving }: { onLeaving: () => void }) {
  const router = useRouter();
  const remove = useDeleteMe();
  return (
    <Dialog onOpenChange={(v) => v && remove.reset()}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm" className="mt-4 text-danger">
          탈퇴 신청하기
        </Button>
      </DialogTrigger>
      <DialogContent className="rounded-card">
        <DialogHeader>
          <DialogTitle>정말 떠나시나요?</DialogTitle>
          <DialogDescription>30일 안에 다시 로그인하면 탈퇴가 취소돼요. 30일이 지나면 저장한 코스와 취향 정보는 되돌릴 수 없어요.</DialogDescription>
        </DialogHeader>
        {remove.error ? (
          <p role="alert" className="text-sm font-bold text-danger">
            {mascotCopyForError(remove.error).description}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            type="button"
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(undefined, {
                onSuccess: () => {
                  onLeaving();
                  setAccessToken(null);
                  router.replace("/");
                },
              })
            }
          >
            {remove.isPending ? "처리하는 중…" : "탈퇴 신청"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
