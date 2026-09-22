"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { z } from "zod";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { flattenCategories } from "@/components/admin/categories";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { Field, FormMessage, nativeSelectClass } from "@/components/admin/Field";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { providerLabel, useAdminEvents, useAdminRegions, useDeleteEvent, useSaveEvent } from "@/lib/api/admin";
import { useCategories } from "@/lib/api/hooks";
import type { AdminEvent } from "@/lib/api/types";
import { dateRange, won } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";

/**
 * 이벤트 유형 = 카테고리 코드 (API `category`, 없는 코드는 422). 선택지는 카테고리 트리에서 놀거리·문화 역할만 추린다.
 * 예전 목 데이터의 짧은 값(festival 등)은 표시용으로만 번역한다.
 */
const EVENT_ROLES = new Set(["CULTURE", "ATTRACTION", "ACTIVITY"]);
const LEGACY_TYPE_LABEL: Record<string, string> = { festival: "축제", exhibition: "전시", performance: "공연", market: "마켓" };
const DEFAULT_TYPE = "culture.festival";

/** 지역·좌표는 등록할 때만 받는다 (API `EventPatch` 에 없다) → 등록 때만 필수 */
const makeSchema = (creating: boolean) =>
  z
    .object({
      title: z.string().trim().min(1, "행사 이름을 입력해 주세요").max(80),
      type: z.string(),
      region: creating ? z.string().min(1, "지역을 골라 주세요") : z.string(),
      venue: creating ? z.string().trim().min(1, "장소를 입력해 주세요") : z.string().trim(),
      lat: creating ? z.number({ error: "위도를 숫자로 입력해 주세요" }).min(33, "대한민국 범위(33~39)를 벗어났어요").max(39, "대한민국 범위(33~39)를 벗어났어요") : z.number().optional(),
      lng: creating ? z.number({ error: "경도를 숫자로 입력해 주세요" }).min(124, "대한민국 범위(124~132)를 벗어났어요").max(132, "대한민국 범위(124~132)를 벗어났어요") : z.number().optional(),
      starts_on: z.string().min(1, "시작일을 골라 주세요"),
      ends_on: z.string().min(1, "종료일을 골라 주세요"),
      is_free: z.boolean(),
      price: z.number({ error: "숫자로 입력해 주세요" }).int().min(0).max(1_000_000),
      link_url: z.union([z.literal(""), z.url("주소 형식을 확인해 주세요")]),
      status: z.enum(["draft", "published", "ended"]),
    })
    .refine((v) => v.ends_on >= v.starts_on, { path: ["ends_on"], message: "종료일이 시작일보다 빨라요" });
type Values = z.infer<ReturnType<typeof makeSchema>>;

const EMPTY: Values = { title: "", type: DEFAULT_TYPE, region: "", venue: "", lat: undefined, lng: undefined, starts_on: "", ends_on: "", is_free: true, price: 0, link_url: "", status: "draft" };

export default function AdminEventsPage() {
  const events = useAdminEvents();
  const [editing, setEditing] = useState<AdminEvent | "new" | null>(null);
  const [removing, setRemoving] = useState<AdminEvent | null>(null);
  const remove = useDeleteEvent();
  const categories = useCategories();
  const typeNames = new Map(flattenCategories(categories.data?.items ?? []).map((o) => [o.code, o.label.replace(/^(· )+/, "")]));
  const typeLabel = (type: string) => typeNames.get(type) ?? LEGACY_TYPE_LABEL[type] ?? (type || "유형 없음");

  const columns: Column<AdminEvent>[] = [
    {
      key: "title",
      header: "행사",
      cell: (e) => (
        <span>
          <b className="block font-extrabold">{e.title}</b>
          <span className="text-caption text-muted-foreground">
            {typeLabel(e.type)}
            {e.venue ? ` · ${e.venue}` : ""}
            {e.provider && e.provider !== "admin" ? ` · ${providerLabel(e.provider)} 수집` : ""}
          </span>
        </span>
      ),
    },
    { key: "region", header: "지역", hideBelow: "md", cell: (e) => e.region_name ?? e.region ?? "전체" },
    { key: "period", header: "기간", cell: (e) => <span className="tabular whitespace-nowrap">{dateRange(e.starts_on, e.ends_on)}</span> },
    { key: "price", header: "요금", align: "right", hideBelow: "sm", cell: (e) => <span className="tabular">{e.is_free ? "무료" : won(e.price)}</span> },
    { key: "status", header: "상태", cell: (e) => <StatusBadge status={e.status} /> },
    {
      key: "actions",
      header: <span className="sr-only">작업</span>,
      align: "right",
      cell: (e) => (
        <span className="flex justify-end gap-1">
          <Button type="button" variant="ghost" size="icon-sm" aria-label={`${e.title} 수정`} onClick={() => setEditing(e)}>
            <Pencil aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`${e.title} 삭제`}
            className="text-danger"
            onClick={() => {
              remove.reset();
              setRemoving(e);
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
        title="이벤트"
        description="축제·전시·공연. ‘게시 중’이고 오늘이 기간 안이면 코스의 놀거리/문화 슬롯 후보와 ‘근처 행사’에 올라가요."
        actions={
          <Button type="button" variant="brand" size="md" onClick={() => setEditing("new")}>
            <Plus aria-hidden /> 이벤트 등록
          </Button>
        }
      />
      <Panel>
        <DataTable
          caption="이벤트 목록"
          columns={columns}
          rows={events.data?.items}
          rowKey={(e) => e.id}
          isLoading={events.isPending}
          error={events.error}
          onRetry={() => void events.refetch()}
          minWidth={640}
          empty={{ title: "등록된 이벤트가 없어요", description: "이번 주말 동네 축제부터 등록해 볼까요?", mood: "hi" }}
        />
      </Panel>

      <Dialog open={editing !== null} onOpenChange={(v) => !v && setEditing(null)}>
        <DialogContent className="max-h-[92dvh] overflow-y-auto rounded-card sm:max-w-xl">{editing ? <EventForm key={editing === "new" ? "new" : editing.id} event={editing === "new" ? null : editing} onDone={() => setEditing(null)} /> : null}</DialogContent>
      </Dialog>

      <Dialog open={removing !== null} onOpenChange={(v) => !v && setRemoving(null)}>
        <DialogContent className="rounded-card">
          <DialogHeader>
            <DialogTitle>이 이벤트를 삭제할까요?</DialogTitle>
            <DialogDescription>{removing?.title} · 삭제하면 되돌릴 수 없어요.</DialogDescription>
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

function EventForm({ event, onDone }: { event: AdminEvent | null; onDone: () => void }) {
  const save = useSaveEvent();
  const regions = useAdminRegions();
  const categories = useCategories();
  const creating = event === null;
  const form = useForm<Values>({
    resolver: zodResolver(makeSchema(creating)),
    defaultValues: event
      ? { title: event.title, type: event.type, region: event.region ?? "", venue: event.venue, lat: event.lat, lng: event.lng, starts_on: event.starts_on, ends_on: event.ends_on, is_free: event.is_free, price: event.price ?? 0, link_url: event.link_url ?? "", status: event.status }
      : EMPTY,
  });
  const { errors } = form.formState;
  const isFree = form.watch("is_free");
  const numeric = { setValueAs: (v: unknown) => (v === "" || v === null || v === undefined ? undefined : Number(v)) };
  const typeOptions = flattenCategories(categories.data?.items ?? []).filter((o) => o.role && EVENT_ROLES.has(o.role));
  const currentType = form.getValues("type");
  const locked = creating ? undefined : "등록한 뒤에는 바꿀 수 없어요";

  return (
    <form
      noValidate
      className="grid gap-4"
      onSubmit={form.handleSubmit((v) =>
        save.mutate(
          { id: event?.id, input: { title: v.title, type: v.type, region: v.region || null, venue: v.venue, lat: v.lat, lng: v.lng, starts_on: v.starts_on, ends_on: v.ends_on, is_free: v.is_free, price: v.is_free ? null : v.price, link_url: v.link_url || null, status: v.status } },
          { onSuccess: onDone },
        ),
      )}
    >
      <DialogHeader>
        <DialogTitle>{event ? "이벤트 수정" : "이벤트 등록"}</DialogTitle>
        <DialogDescription>기간이 지나면 자동으로 ‘종료’ 처리돼요.</DialogDescription>
      </DialogHeader>
      <Field id="e-title" label="행사 이름" required error={errors.title?.message}>
        <Input id="e-title" aria-invalid={Boolean(errors.title)} aria-describedby="e-title-desc" {...form.register("title")} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="e-type" label="유형" hint={categories.isError ? "분류 목록을 불러오지 못했어요" : locked}>
          <select id="e-type" className={nativeSelectClass} disabled={!creating || categories.isPending} aria-describedby="e-type-desc" {...form.register("type")}>
            {!typeOptions.some((t) => t.code === currentType) ? <option value={currentType}>{LEGACY_TYPE_LABEL[currentType] ?? (currentType || "유형 없음")}</option> : null}
            {typeOptions.map((t) => (
              <option key={t.code} value={t.code}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>
        <Field id="e-region" label="지역" required={creating} error={errors.region?.message} hint={regions.isError ? "지역 목록을 불러오지 못했어요" : locked}>
          <select id="e-region" className={nativeSelectClass} disabled={!creating || regions.isPending} aria-invalid={Boolean(errors.region)} aria-describedby="e-region-desc" {...form.register("region")}>
            <option value="">{creating ? "선택" : "지역 없음"}</option>
            {regions.data?.items.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field id="e-venue" label="장소" required={creating} error={errors.venue?.message} hint="행사장 이름이나 주소">
        <Input id="e-venue" aria-invalid={Boolean(errors.venue)} aria-describedby="e-venue-desc" {...form.register("venue")} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="e-lat" label="위도" required={creating} error={errors.lat?.message} hint={locked ?? "코스의 ‘근처 행사’ 거리 계산에 써요"}>
          <Input id="e-lat" type="number" step="0.0001" inputMode="decimal" placeholder="37.5560" disabled={!creating} aria-invalid={Boolean(errors.lat)} aria-describedby="e-lat-desc" {...form.register("lat", numeric)} />
        </Field>
        <Field id="e-lng" label="경도" required={creating} error={errors.lng?.message} hint={locked}>
          <Input id="e-lng" type="number" step="0.0001" inputMode="decimal" placeholder="126.9100" disabled={!creating} aria-invalid={Boolean(errors.lng)} aria-describedby="e-lng-desc" {...form.register("lng", numeric)} />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="e-start" label="시작일" required error={errors.starts_on?.message}>
          <Input id="e-start" type="date" aria-invalid={Boolean(errors.starts_on)} aria-describedby="e-start-desc" {...form.register("starts_on")} />
        </Field>
        <Field id="e-end" label="종료일" required error={errors.ends_on?.message}>
          <Input id="e-end" type="date" aria-invalid={Boolean(errors.ends_on)} aria-describedby="e-end-desc" {...form.register("ends_on")} />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex items-center gap-2 self-end pb-2 text-body-sm font-semibold text-ink-2">
          <input type="checkbox" className="size-4 accent-[#2F6BEA]" {...form.register("is_free")} /> 무료 행사
        </label>
        <Field id="e-price" label="요금 (원)" error={errors.price?.message}>
          <Input id="e-price" type="number" step={500} inputMode="numeric" disabled={isFree} aria-describedby="e-price-desc" {...form.register("price", { valueAsNumber: true })} />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="e-link" label="안내·예매 링크" error={errors.link_url?.message}>
          <Input id="e-link" type="url" placeholder="https://" aria-invalid={Boolean(errors.link_url)} aria-describedby="e-link-desc" {...form.register("link_url")} />
        </Field>
        <Field id="e-status" label="상태">
          <select id="e-status" className={nativeSelectClass} {...form.register("status")}>
            <option value="draft">초안 (검수 전)</option>
            <option value="published">게시 중</option>
            <option value="ended">종료</option>
          </select>
        </Field>
      </div>
      {save.error ? <FormMessage tone="error">{save.error.detail ?? mascotCopyForError(save.error).description}</FormMessage> : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>
          취소
        </Button>
        <Button type="submit" variant="brand" size="md" disabled={save.isPending}>
          {save.isPending ? "저장하는 중…" : event ? "수정 저장" : "등록"}
        </Button>
      </DialogFooter>
    </form>
  );
}
