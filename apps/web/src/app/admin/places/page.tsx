"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Check, CheckCheck, ImagePlus, Search, X } from "lucide-react";
import { z } from "zod";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { flattenCategories } from "@/components/admin/categories";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { Field, FormMessage, nativeSelectClass } from "@/components/admin/Field";
import { StatusBadge, statusLabel } from "@/components/admin/StatusBadge";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MAX_PHOTO_BYTES, useAdminPlaces, useApprovePlace, useBulkApprovePlaces, usePlaceRevisions, useRejectPlace, useUpdatePlace, useUploadPlacePhoto } from "@/lib/api/admin";
import { useCategories, useDebounced, usePlaceDetail } from "@/lib/api/hooks";
import type { AdminPlace, PlaceStatus } from "@/lib/api/types";
import { dateShort, won } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";

const STATUS_TABS: { value: PlaceStatus | "all"; label: string }[] = [
  { value: "pending", label: "승인 대기" },
  { value: "approved", label: "승인됨" },
  { value: "rejected", label: "반려" },
  { value: "hidden", label: "숨김" },
  { value: "closed", label: "폐업" },
  { value: "all", label: "전체" },
];

export default function AdminPlacesPage() {
  const [status, setStatus] = useState<PlaceStatus | "all">("pending");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [openId, setOpenId] = useState<string | null>(null);
  const query = useDebounced(q.trim(), 300);

  const places = useAdminPlaces({ status: status === "all" ? undefined : status, q: query || undefined, limit: 50 });
  const bulk = useBulkApprovePlaces();
  const rows = places.data?.items;
  const open = rows?.find((p) => p.id === openId) ?? null;

  useEffect(() => setSelected(new Set()), [status, query]);

  const columns: Column<AdminPlace>[] = [
    {
      key: "name",
      header: "장소",
      cell: (p) => (
        <span>
          <b className="block font-extrabold">{p.name}</b>
          <span className="text-caption text-muted-foreground">{p.category_name}</span>
          {p.duplicate_of ? <span className="ml-1.5 rounded-md bg-pink-soft px-1.5 py-0.5 text-caption font-semibold text-pink-deep">중복 의심</span> : null}
        </span>
      ),
    },
    { key: "region", header: "지역", cell: (p) => p.region?.name ?? "-", hideBelow: "sm" },
    { key: "price", header: "1인 가격", align: "right", cell: (p) => <span className="tabular">{p.is_free ? "무료" : won(p.price_per_person)}</span> },
    { key: "source", header: "출처", cell: (p) => <span className="text-caption">{p.source}</span>, hideBelow: "md" },
    { key: "created", header: "수집일", cell: (p) => <span className="tabular">{dateShort(p.created_at)}</span>, hideBelow: "lg" },
    { key: "status", header: "상태", cell: (p) => <StatusBadge status={p.status} /> },
  ];

  return (
    <>
      <AdminPageHeader title="장소 승인 · 수정" description="수집된 장소는 승인해야 추천 후보가 돼요. 행을 누르면 원본과 정규화 결과를 비교하고 고칠 수 있어요." />

      <Panel>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div role="tablist" aria-label="상태 필터" className="no-scrollbar flex gap-1 overflow-x-auto rounded-full bg-soft p-1">
            {STATUS_TABS.map((t) => (
              <button key={t.value} type="button" role="tab" aria-selected={status === t.value} onClick={() => setStatus(t.value)} className={cn("rounded-full px-3.5 py-1.5 text-body-sm font-semibold whitespace-nowrap", status === t.value ? "bg-white text-ink shadow-soft" : "text-ink-2 hover:text-ink")}>
                {t.label}
              </button>
            ))}
          </div>
          <label className="relative ml-auto w-full sm:w-64">
            <span className="sr-only">장소 이름 검색</span>
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="장소 이름 검색" className="pl-9" />
          </label>
        </div>

        {selected.size > 0 ? (
          <div className="mb-3 flex flex-wrap items-center gap-3 rounded-2xl bg-blue-soft px-4 py-2.5" role="region" aria-label="선택한 장소 일괄 작업">
            <p className="tabular text-body-sm font-extrabold text-blue-deep">{selected.size}곳 선택됨</p>
            <Button type="button" size="sm" disabled={bulk.isPending} onClick={() => bulk.mutate([...selected], { onSuccess: () => setSelected(new Set()) })}>
              <CheckCheck aria-hidden /> {bulk.isPending ? "승인하는 중…" : "일괄 승인"}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              선택 해제
            </Button>
          </div>
        ) : null}
        <div aria-live="polite">
          {bulk.data ? <div className="mb-3"><FormMessage tone={bulk.data.failed.length ? "error" : "success"}>{bulk.data.approved}곳을 승인했어요.{bulk.data.failed.length ? ` ${bulk.data.failed.length}곳은 실패했어요.` : ""}</FormMessage></div> : null}
          {bulk.error ? <div className="mb-3"><FormMessage tone="error">{mascotCopyForError(bulk.error).description}</FormMessage></div> : null}
        </div>

        <DataTable
          caption="장소 목록"
          columns={columns}
          rows={rows}
          rowKey={(p) => p.id}
          isLoading={places.isPending}
          error={places.error}
          onRetry={() => void places.refetch()}
          onRowClick={(p) => setOpenId(p.id)}
          rowLabel={(p) => `${p.name} 상세 열기`}
          selection={{ selected, onChange: setSelected, isSelectable: (p) => p.status === "pending" }}
          minWidth={680}
          empty={
            status === "pending" && !query
              ? { title: "승인 대기 중인 장소가 없어요", description: "큐를 다 비웠어요. 새 지역을 수집하면 여기에 쌓여요.", mood: "cheers" }
              : { title: "조건에 맞는 장소가 없어요", description: "검색어나 상태 필터를 바꿔 보세요.", mood: "think" }
          }
        />
        {places.data?.next_cursor ? <p className="mt-3 text-center text-caption text-muted-foreground">처음 50곳만 보여 줘요. 검색으로 좁혀 보세요.</p> : null}
      </Panel>

      <Sheet open={open !== null} onOpenChange={(v) => !v && setOpenId(null)}>
        <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-[640px]">{open ? <PlaceDetail place={open} onClose={() => setOpenId(null)} /> : null}</SheetContent>
      </Sheet>
    </>
  );
}

// ── 상세 드로어 ─────────────────────────────────────────────
function PlaceDetail({ place, onClose }: { place: AdminPlace; onClose: () => void }) {
  const approve = useApprovePlace();
  const reject = useRejectPlace();
  const [reason, setReason] = useState("");
  const error = approve.error ?? reject.error;

  return (
    <>
      <SheetHeader className="border-b">
        <SheetTitle className="flex flex-wrap items-center gap-2 text-h3 font-extrabold">
          {place.name} <StatusBadge status={place.status} />
        </SheetTitle>
        <SheetDescription>
          {place.category_name} · {place.region?.name ?? "지역 없음"} · 출처 {place.source}
          {place.data_quality !== undefined ? ` · 데이터 품질 ${Math.round(place.data_quality * 100)}%` : ""}
          {place.duplicate_of ? ` · ‘${place.duplicate_of.name}’ 과(와) 중복 의심` : ""}
        </SheetDescription>
      </SheetHeader>

      <div className="grid gap-5 p-4">
        <Tabs defaultValue={place.source_raw || place.normalized ? "diff" : "edit"}>
          <TabsList>
            <TabsTrigger value="diff">원본 비교</TabsTrigger>
            <TabsTrigger value="edit">장소 수정</TabsTrigger>
            <TabsTrigger value="photos">사진</TabsTrigger>
            <TabsTrigger value="history">수정 이력</TabsTrigger>
          </TabsList>
          <TabsContent value="diff" className="pt-3">
            <RawDiff raw={place.source_raw} normalized={place.normalized} />
          </TabsContent>
          <TabsContent value="edit" className="pt-3">
            <PlaceEditForm place={place} />
          </TabsContent>
          <TabsContent value="photos" className="pt-3">
            <PlacePhotos id={place.id} name={place.name} />
          </TabsContent>
          <TabsContent value="history" className="pt-3">
            <Revisions id={place.id} />
          </TabsContent>
        </Tabs>

        {place.status === "pending" ? (
          <div className="sticky bottom-0 -mx-4 grid gap-2.5 border-t bg-white p-4">
            <Field id="reject-reason" label="반려 사유 (선택)">
              <Input id="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="예: 폐업, 가격 정보 없음" />
            </Field>
            {error ? <FormMessage tone="error">{mascotCopyForError(error).description}</FormMessage> : null}
            <div className="flex gap-2">
              <Button type="button" variant="outline" className="flex-1 text-danger" disabled={reject.isPending || approve.isPending} onClick={() => reject.mutate({ id: place.id, reason: reason || undefined }, { onSuccess: onClose })}>
                <X aria-hidden /> 반려
              </Button>
              <Button type="button" className="flex-[2] bg-success hover:bg-success/90" disabled={reject.isPending || approve.isPending} onClick={() => approve.mutate(place.id, { onSuccess: onClose })}>
                <Check aria-hidden /> {approve.isPending ? "승인하는 중…" : "승인"}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}

const show = (value: unknown): string => (value === undefined ? "—" : typeof value === "string" ? value : JSON.stringify(value));

/** 수집 원본(source_raw) 과 정규화 결과(normalized) 를 키 단위로 나란히 놓고, 달라진 키를 강조한다 */
function RawDiff({ raw, normalized }: { raw?: Record<string, unknown>; normalized?: Record<string, unknown> }) {
  const keys = useMemo(() => [...new Set([...Object.keys(raw ?? {}), ...Object.keys(normalized ?? {})])].sort(), [raw, normalized]);
  if (keys.length === 0) return <EmptyState size="sm" title="비교할 원본 데이터가 없어요" description="수집 원본 비교는 아직 준비 중이에요. 지금은 ‘장소 수정’ 탭에서 정규화된 값을 확인하고 고칠 수 있어요." />;
  const changed = keys.filter((k) => show(raw?.[k]) !== show(normalized?.[k])).length;

  return (
    <div>
      <p className="mb-2 text-body-sm text-ink-2">
        {keys.length}개 항목 중 <b className="text-gold-ink">{changed}개</b>가 정규화 과정에서 달라졌어요.
      </p>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full min-w-[520px] text-body-sm">
          <caption className="sr-only">수집 원본과 정규화 결과 비교</caption>
          <thead className="bg-soft text-left text-caption font-semibold text-ink-2">
            <tr>
              <th scope="col" className="px-3 py-2">항목</th>
              <th scope="col" className="px-3 py-2">수집 원본</th>
              <th scope="col" className="px-3 py-2">정규화 결과</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => {
              const a = show(raw?.[k]);
              const b = show(normalized?.[k]);
              const diff = a !== b;
              return (
                <tr key={k} className={cn("border-t align-top", diff && "bg-gold-soft/60")}>
                  <th scope="row" className="px-3 py-2 text-left font-mono text-caption font-semibold whitespace-nowrap">
                    {k}
                    {diff ? <span className="sr-only"> (변경됨)</span> : null}
                  </th>
                  <td className={cn("px-3 py-2 break-all", diff && "text-ink-2 line-through decoration-pink-deep/60")}>{a}</td>
                  <td className={cn("px-3 py-2 break-all", diff && "font-extrabold text-ink")}>{b}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** 수정 이력의 action · 필드명은 API enum/컬럼명이다 → 운영자에게는 번역해서 보여준다 */
const ACTION_LABEL: Record<string, string> = { create: "등록", approve: "승인", reject: "반려", edit: "수정", merge: "병합" };
const FIELD_LABEL: Record<string, string> = {
  name: "이름",
  status: "상태",
  lat: "위도",
  lng: "경도",
  address: "주소",
  phone: "전화",
  description: "소개",
  thumbnail_url: "대표 이미지",
  price_per_person: "1인 가격",
  is_free: "무료 여부",
  category: "분류",
  category_id: "분류 (내부 번호)",
  tags: "태그",
};
const showField = (field: string, value: unknown): string =>
  value === null || value === undefined ? "—" : field === "status" && typeof value === "string" ? statusLabel(value) : typeof value === "boolean" ? (value ? "예" : "아니오") : show(value);

function Revisions({ id }: { id: string }) {
  const revisions = usePlaceRevisions(id);
  if (revisions.isPending) return <Skeleton className="h-24 rounded-xl" />;
  if (revisions.isError) return <ErrorState error={revisions.error} onRetry={() => void revisions.refetch()} size="sm" />;
  if (revisions.data.items.length === 0) return <EmptyState size="sm" title="아직 수정한 적이 없어요" />;
  return (
    <ol className="grid gap-2.5">
      {revisions.data.items.map((r) => (
        <li key={r.id} className="rounded-xl border p-3 text-body-sm">
          <p className="font-extrabold">
            {r.action ? `${ACTION_LABEL[r.action] ?? r.action} · ` : ""}
            {r.actor} <span className="tabular font-medium text-muted-foreground">· {dateShort(r.created_at)}</span>
          </p>
          {r.note ? <p className="mt-0.5 text-ink-2">메모: {r.note}</p> : null}
          <ul className="mt-1 grid gap-0.5 text-ink-2">
            {Object.entries(r.changes).map(([field, c]) => (
              <li key={field} className="break-all">
                <span className="text-caption font-semibold">{FIELD_LABEL[field] ?? field}</span>: <span className="line-through">{showField(field, c.from)}</span> → <b className="text-ink">{showField(field, c.to)}</b>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

// ── 사진 ────────────────────────────────────────────────────
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

/** 그 가게의 실제 사진을 올린다. 사진이 없는 곳은 코스 화면에서 "예시 사진"으로 보인다 → 여기서 올리면 바로 실제 사진으로 바뀐다 */
function PlacePhotos({ id, name }: { id: string; name: string }) {
  const detail = usePlaceDetail(id);
  const upload = useUploadPlacePhoto();
  const [file, setFile] = useState<File | null>(null);
  const [makeCover, setMakeCover] = useState(true);
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  const problem = !file ? null : !PHOTO_TYPES.includes(file.type) ? "JPEG · PNG · WebP 사진만 올릴 수 있어요." : file.size > MAX_PHOTO_BYTES ? "사진이 너무 커요 (최대 6MB)." : null;
  const photos = detail.data?.images ?? [];

  return (
    <div className="grid gap-4">
      <section aria-labelledby="photos-now">
        <h3 id="photos-now" className="mb-2 text-body-sm font-semibold text-ink-2">
          지금 보이는 사진
        </h3>
        {detail.isPending ? (
          <Skeleton className="h-24 rounded-xl" />
        ) : photos.length === 0 ? (
          <p className="rounded-xl bg-soft p-3 text-body-sm text-ink-2">실제 사진이 아직 없어요. 코스 화면에서는 업종별 “예시 사진”으로 보여요.</p>
        ) : (
          <ul className="grid grid-cols-3 gap-2">
            {photos.map((url, i) => (
              <li key={url} className="relative aspect-[4/3] overflow-hidden rounded-xl border bg-soft">
                <Image src={url} alt={`${name} 사진 ${i + 1}`} fill sizes="200px" unoptimized className="object-cover" />
                {i === 0 ? <span className="absolute top-1.5 left-1.5 rounded-md bg-ink/80 px-1.5 py-0.5 text-caption font-semibold text-white">대표</span> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <form
        noValidate
        className="grid gap-3 rounded-xl border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (file && !problem) upload.mutate({ id, file, makeCover }, { onSuccess: () => setFile(null) });
        }}
      >
        <Field id="p-photo" label="올릴 사진" hint="직접 찍었거나 가게가 제공한, 써도 되는 사진만 올려 주세요. JPEG · PNG · WebP, 6MB 이하." error={problem ?? undefined}>
          <Input id="p-photo" key={file ? "picked" : "empty"} type="file" accept={PHOTO_TYPES.join(",")} aria-describedby="p-photo-desc" aria-invalid={Boolean(problem)} onChange={(e) => { upload.reset(); setFile(e.target.files?.[0] ?? null); }} />
        </Field>
        {preview && !problem ? (
          <div className="relative aspect-[4/3] w-40 overflow-hidden rounded-xl border bg-soft">
            <Image src={preview} alt="올릴 사진 미리보기" fill sizes="160px" unoptimized className="object-cover" />
          </div>
        ) : null}
        <label className="flex items-center gap-2 text-body-sm font-semibold text-ink-2">
          <input type="checkbox" className="size-4 accent-[#2F6BEA]" checked={makeCover} onChange={(e) => setMakeCover(e.target.checked)} /> 대표 사진으로 쓰기
        </label>
        <div aria-live="polite" className="grid gap-2">
          {upload.isSuccess && !file ? <FormMessage tone="success">사진을 올렸어요. 코스 화면에 바로 반영돼요.</FormMessage> : null}
          {upload.error ? <FormMessage tone="error">{upload.error.detail ?? mascotCopyForError(upload.error).description}</FormMessage> : null}
        </div>
        <Button type="submit" disabled={!file || Boolean(problem) || upload.isPending} className="justify-self-end">
          <ImagePlus aria-hidden /> {upload.isPending ? "올리는 중…" : "사진 올리기"}
        </Button>
      </form>
    </div>
  );
}

// ── 장소 수정 ───────────────────────────────────────────────
const editSchema = z.object({
  name: z.string().trim().min(1, "이름을 입력해 주세요"),
  category: z.string().min(1, "분류를 골라 주세요"),
  address: z.string().trim(),
  price_per_person: z.number({ error: "숫자로 입력해 주세요" }).int().min(0, "0 이상이어야 해요").max(1_000_000),
  is_free: z.boolean(),
  tags: z.string(),
  status: z.enum(["pending", "approved", "rejected", "hidden", "closed"]),
});
type EditValues = z.infer<typeof editSchema>;

function PlaceEditForm({ place }: { place: AdminPlace }) {
  const update = useUpdatePlace();
  const categories = useCategories();
  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: { name: place.name, category: place.category, address: place.address, price_per_person: place.price_per_person ?? 0, is_free: place.is_free, tags: place.tags.join(", "), status: place.status },
  });
  const { errors, isDirty, dirtyFields } = form.formState;
  const options = flattenCategories(categories.data?.items ?? []);

  return (
    <form
      noValidate
      className="grid gap-3.5"
      onSubmit={form.handleSubmit((v) =>
        update.mutate(
          {
            id: place.id,
            // PATCH 는 "보낸 것만 바꾼다" → 손댄 항목만 보낸다. (가격을 모르는 곳을 다른 항목만 고쳐 저장해도 0원이 되지 않게)
            input: {
              name: dirtyFields.name ? v.name : undefined,
              category: dirtyFields.category ? v.category : undefined,
              address: dirtyFields.address ? v.address : undefined,
              status: dirtyFields.status ? v.status : undefined,
              is_free: dirtyFields.is_free ? v.is_free : undefined,
              price_per_person: v.is_free ? (dirtyFields.is_free ? 0 : undefined) : dirtyFields.price_per_person || dirtyFields.is_free ? v.price_per_person : undefined,
              // 태그는 통째로 교체된다 → 손댔을 때만 보내고, 기존 태그의 가중치는 그대로 돌려보낸다
              tags: dirtyFields.tags ? v.tags.split(",").map((t) => t.trim()).filter(Boolean) : undefined,
              tag_weights: place.tag_weights,
            },
          },
          { onSuccess: (_saved, vars) => form.reset({ ...v, tags: vars.input.tags ? vars.input.tags.join(", ") : v.tags }) },
        ),
      )}
    >
      <Field id="p-name" label="이름" required error={errors.name?.message}>
        <Input id="p-name" aria-invalid={Boolean(errors.name)} aria-describedby="p-name-desc" {...form.register("name")} />
      </Field>
      <Field id="p-category" label="분류" required error={errors.category?.message ?? (categories.isError ? "분류 목록을 불러오지 못했어요" : undefined)}>
        <select id="p-category" className={nativeSelectClass} disabled={categories.isPending} aria-describedby="p-category-desc" {...form.register("category")}>
          {!options.some((o) => o.code === place.category) ? <option value={place.category}>{place.category_name}</option> : null}
          {options.map((o) => (
            <option key={o.code} value={o.code}>
              {o.label}
            </option>
          ))}
        </select>
      </Field>
      <Field id="p-address" label="주소">
        <Input id="p-address" {...form.register("address")} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field id="p-price" label="1인 가격 (원)" error={errors.price_per_person?.message} hint="추천의 예산 필터가 이 값을 써요">
          <Input id="p-price" type="number" step={500} inputMode="numeric" disabled={form.watch("is_free")} aria-describedby="p-price-desc" {...form.register("price_per_person", { valueAsNumber: true })} />
        </Field>
        <Field id="p-status" label="상태">
          <select id="p-status" className={nativeSelectClass} {...form.register("status")}>
            <option value="pending">승인 대기</option>
            <option value="approved">승인됨</option>
            <option value="rejected">반려</option>
            <option value="hidden">숨김</option>
            <option value="closed">폐업</option>
          </select>
        </Field>
      </div>
      <label className="flex items-center gap-2 text-body-sm font-semibold text-ink-2">
        <input type="checkbox" className="size-4 accent-[#2F6BEA]" {...form.register("is_free")} /> 무료 장소 (공원·산책로 등)
      </label>
      <Field id="p-tags" label="태그" hint="쉼표로 구분. 태그 목록에 등록된 이름만 쓸 수 있어요.">
        <Input id="p-tags" aria-describedby="p-tags-desc" {...form.register("tags")} />
      </Field>

      <div aria-live="polite" className="grid gap-2">
        {update.isSuccess && !isDirty ? <FormMessage tone="success">수정 내용을 저장했어요. 이력에 기록됩니다.</FormMessage> : null}
        {update.error ? <FormMessage tone="error">{update.error.detail ?? mascotCopyForError(update.error).description}</FormMessage> : null}
      </div>
      <Button type="submit" disabled={!isDirty || update.isPending} className="justify-self-end">
        {update.isPending ? "저장하는 중…" : "수정 저장"}
      </Button>
    </form>
  );
}
