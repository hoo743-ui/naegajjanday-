"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { z } from "zod";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { Field, FormMessage, nativeSelectClass } from "@/components/admin/Field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAdminBanners, useAdminRegions, useDeleteBanner, useSaveBanner } from "@/lib/api/admin";
import type { AdminBanner } from "@/lib/api/types";
import { dateRange, num, percent } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";

/** 노출 위치는 프론트에 실제로 슬롯이 있는 곳만 고를 수 있다 (화면 구조에 묶인 값) */
const PLACEMENTS = [
  { value: "home", label: "홈" },
  { value: "explore", label: "둘러보기" },
  { value: "course", label: "코스 결과" },
];
const placementLabel = (value: string) => PLACEMENTS.find((p) => p.value === value)?.label ?? value;

const linkSchema = z.string().trim().min(1, "이동할 주소를 입력해 주세요").refine((v) => (v.startsWith("/") && !v.startsWith("//")) || /^https:\/\//.test(v), "‘/경로’ 또는 https:// 주소만 쓸 수 있어요");

const schema = z
  .object({
    title: z.string().trim().min(1, "제목을 입력해 주세요").max(40, "40자까지 쓸 수 있어요"),
    subtitle: z.string().trim().max(60, "60자까지 쓸 수 있어요"),
    image_url: z.union([z.literal(""), z.url("주소 형식을 확인해 주세요")]),
    link_url: linkSchema,
    placement: z.string().min(1),
    region: z.string(),
    starts_at: z.string().min(1, "시작일을 골라 주세요"),
    ends_at: z.string().min(1, "종료일을 골라 주세요"),
    is_active: z.boolean(),
  })
  .refine((v) => v.ends_at >= v.starts_at, { path: ["ends_at"], message: "종료일이 시작일보다 빨라요" });
type Values = z.infer<typeof schema>;

const EMPTY: Values = { title: "", subtitle: "", image_url: "", link_url: "", placement: "home", region: "", starts_at: "", ends_at: "", is_active: true };

export default function AdminBannersPage() {
  const banners = useAdminBanners();
  const save = useSaveBanner();
  const remove = useDeleteBanner();
  const [editing, setEditing] = useState<AdminBanner | "new" | null>(null);
  const [removing, setRemoving] = useState<AdminBanner | null>(null);

  const columns: Column<AdminBanner>[] = [
    {
      key: "title",
      header: "배너",
      cell: (b) => (
        <span>
          <b className="block font-extrabold">{b.title}</b>
          <span className="line-clamp-1 text-xs text-muted-foreground">{b.subtitle ?? b.link_url}</span>
        </span>
      ),
    },
    { key: "placement", header: "위치", hideBelow: "sm", cell: (b) => `${placementLabel(b.placement)}${b.region ? ` · ${b.region}` : ""}` },
    { key: "period", header: "기간", hideBelow: "md", cell: (b) => <span className="tabular whitespace-nowrap">{dateRange(b.starts_at, b.ends_at)}</span> },
    { key: "imp", header: "노출", align: "right", hideBelow: "lg", cell: (b) => <span className="tabular">{num(b.impressions)}</span> },
    { key: "ctr", header: "클릭률", align: "right", cell: (b) => <span className="tabular">{b.impressions ? percent(b.clicks / b.impressions, 1) : "-"}</span> },
    {
      key: "active",
      header: "노출 중",
      align: "center",
      cell: (b) => <Switch checked={b.is_active} disabled={save.isPending} aria-label={`${b.title} 노출 ${b.is_active ? "끄기" : "켜기"}`} onCheckedChange={(v) => save.mutate({ id: b.id, input: { is_active: v } })} />,
    },
    {
      key: "actions",
      header: <span className="sr-only">작업</span>,
      align: "right",
      cell: (b) => (
        <span className="flex justify-end gap-1">
          <Button type="button" variant="ghost" size="icon-sm" aria-label={`${b.title} 수정`} onClick={() => setEditing(b)}>
            <Pencil aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-danger"
            aria-label={`${b.title} 삭제`}
            onClick={() => {
              remove.reset();
              setRemoving(b);
            }}
          >
            <Trash2 aria-hidden />
          </Button>
        </span>
      ),
    },
  ];

  return (
    <>
      <AdminPageHeader
        title="배너 관리"
        description="홈과 둘러보기에 노출되는 배너. 기간 안이고 ‘노출 중’이어야 사용자에게 보여요."
        actions={
          <Button type="button" variant="brand" size="md" onClick={() => setEditing("new")}>
            <Plus aria-hidden /> 배너 만들기
          </Button>
        }
      />
      <Panel>
        {save.error && editing === null ? (
          <div className="mb-3">
            <FormMessage tone="error">{mascotCopyForError(save.error).description}</FormMessage>
          </div>
        ) : null}
        <DataTable
          caption="배너 목록"
          columns={columns}
          rows={banners.data?.items}
          rowKey={(b) => b.id}
          isLoading={banners.isPending}
          error={banners.error}
          onRetry={() => void banners.refetch()}
          minWidth={620}
          empty={{ title: "아직 배너가 없어요", description: "가을 축제 모아보기 같은 기획전을 걸어 보세요.", mood: "hi" }}
        />
      </Panel>

      <Dialog open={editing !== null} onOpenChange={(v) => !v && setEditing(null)}>
        <DialogContent className="max-h-[92dvh] overflow-y-auto rounded-card sm:max-w-xl">{editing ? <BannerForm key={editing === "new" ? "new" : editing.id} banner={editing === "new" ? null : editing} onDone={() => setEditing(null)} /> : null}</DialogContent>
      </Dialog>

      <Dialog open={removing !== null} onOpenChange={(v) => !v && setRemoving(null)}>
        <DialogContent className="rounded-card">
          <DialogHeader>
            <DialogTitle>이 배너를 삭제할까요?</DialogTitle>
            <DialogDescription>{removing?.title} · 노출·클릭 기록도 함께 사라져요.</DialogDescription>
          </DialogHeader>
          {remove.error ? <FormMessage tone="error">{mascotCopyForError(remove.error).description}</FormMessage> : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setRemoving(null)}>
              취소
            </Button>
            <Button type="button" variant="destructive" disabled={remove.isPending} onClick={() => removing && remove.mutate(removing.id, { onSuccess: () => setRemoving(null) })}>
              {remove.isPending ? "삭제하는 중…" : "삭제"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function BannerForm({ banner, onDone }: { banner: AdminBanner | null; onDone: () => void }) {
  const save = useSaveBanner();
  const regions = useAdminRegions();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: banner
      ? { title: banner.title, subtitle: banner.subtitle ?? "", image_url: banner.image_url ?? "", link_url: banner.link_url, placement: banner.placement, region: banner.region ?? "", starts_at: banner.starts_at.slice(0, 10), ends_at: banner.ends_at.slice(0, 10), is_active: banner.is_active }
      : EMPTY,
  });
  const { errors } = form.formState;
  const preview = form.watch();

  return (
    <form
      noValidate
      className="grid gap-4"
      onSubmit={form.handleSubmit((v) =>
        save.mutate(
          { id: banner?.id, input: { title: v.title, subtitle: v.subtitle || null, image_url: v.image_url || null, link_url: v.link_url, placement: v.placement, region: v.region || null, starts_at: v.starts_at, ends_at: v.ends_at, is_active: v.is_active } },
          { onSuccess: onDone },
        ),
      )}
    >
      <DialogHeader>
        <DialogTitle>{banner ? "배너 수정" : "배너 만들기"}</DialogTitle>
        <DialogDescription>이미지가 없으면 브랜드 그라디언트 위에 글자만 보여요.</DialogDescription>
      </DialogHeader>

      <div aria-hidden className="bg-grad-soft relative overflow-hidden rounded-2xl bg-cover bg-center p-5" style={preview.image_url && !errors.image_url ? { backgroundImage: `linear-gradient(90deg,rgba(255,255,255,.92),rgba(255,255,255,.35)),url("${encodeURI(preview.image_url)}")` } : undefined}>
        <p className="text-xs font-extrabold text-blue-deep">미리보기 · {placementLabel(preview.placement)}</p>
        <p className="mt-1 text-lg font-extrabold tracking-tight">{preview.title || "배너 제목"}</p>
        <p className="text-sm text-ink-2">{preview.subtitle || "부제목"}</p>
      </div>

      <Field id="b-title" label="제목" required error={errors.title?.message}>
        <Input id="b-title" aria-invalid={Boolean(errors.title)} aria-describedby="b-title-desc" {...form.register("title")} />
      </Field>
      <Field id="b-subtitle" label="부제목" error={errors.subtitle?.message}>
        <Input id="b-subtitle" aria-describedby="b-subtitle-desc" {...form.register("subtitle")} />
      </Field>
      <Field id="b-link" label="누르면 이동할 곳" required error={errors.link_url?.message} hint="예: /explore?type=festival">
        <Input id="b-link" aria-invalid={Boolean(errors.link_url)} aria-describedby="b-link-desc" {...form.register("link_url")} />
      </Field>
      <Field id="b-image" label="이미지 주소" error={errors.image_url?.message} hint="업로드된 이미지의 https 주소. (파일 업로드는 presign API 연결 후 제공)">
        <Input id="b-image" type="url" placeholder="https://" aria-invalid={Boolean(errors.image_url)} aria-describedby="b-image-desc" {...form.register("image_url")} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="b-placement" label="노출 위치">
          <select id="b-placement" className={nativeSelectClass} {...form.register("placement")}>
            {!PLACEMENTS.some((p) => p.value === form.getValues("placement")) ? <option value={form.getValues("placement")}>{form.getValues("placement")}</option> : null}
            {PLACEMENTS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </Field>
        <Field id="b-region" label="지역 한정" hint={regions.isError ? "지역 목록을 불러오지 못했어요" : undefined}>
          <select id="b-region" className={nativeSelectClass} disabled={regions.isPending} aria-describedby="b-region-desc" {...form.register("region")}>
            <option value="">전체 지역</option>
            {regions.data?.items.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.name}
              </option>
            ))}
          </select>
        </Field>
        <Field id="b-start" label="시작일" required error={errors.starts_at?.message}>
          <Input id="b-start" type="date" aria-invalid={Boolean(errors.starts_at)} aria-describedby="b-start-desc" {...form.register("starts_at")} />
        </Field>
        <Field id="b-end" label="종료일" required error={errors.ends_at?.message}>
          <Input id="b-end" type="date" aria-invalid={Boolean(errors.ends_at)} aria-describedby="b-end-desc" {...form.register("ends_at")} />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm font-bold text-ink-2">
        <input type="checkbox" className="size-4 accent-[#2F6BEA]" {...form.register("is_active")} /> 저장하면 바로 노출
      </label>

      {save.error ? <FormMessage tone="error">{save.error.detail ?? mascotCopyForError(save.error).description}</FormMessage> : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>
          취소
        </Button>
        <Button type="submit" variant="brand" size="md" disabled={save.isPending}>
          {save.isPending ? "저장하는 중…" : banner ? "수정 저장" : "만들기"}
        </Button>
      </DialogFooter>
    </form>
  );
}
