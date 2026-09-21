"use client";

import { useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { FileUp, Plus } from "lucide-react";
import { z } from "zod";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { flattenCategories } from "@/components/admin/categories";
import { Field, FormMessage, nativeSelectClass } from "@/components/admin/Field";
import { ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAdminRegions, useCreatePlace, useImportPlaces } from "@/lib/api/admin";
import { useCategories } from "@/lib/api/hooks";
import { mascotCopyForError } from "@/lib/mascot-copy";

/** 이 화면에서 직접 추가하는 대상: 코스에서 "놀거리/문화" 슬롯에 들어가는 분류 */
const DIRECT_ROLES = new Set(["ATTRACTION", "CULTURE", "ACTIVITY", "NIGHTVIEW"]);

const schema = z.object({
  name: z.string().trim().min(1, "이름을 입력해 주세요").max(60),
  category: z.string().min(1, "분류를 골라 주세요"),
  region: z.string().min(1, "지역을 골라 주세요"),
  address: z.string().trim().min(1, "주소를 입력해 주세요"),
  lat: z.number({ error: "위도를 숫자로 입력해 주세요" }).min(33).max(39),
  lng: z.number({ error: "경도를 숫자로 입력해 주세요" }).min(124).max(132),
  is_free: z.boolean(),
  price_per_person: z.number({ error: "숫자로 입력해 주세요" }).int().min(0).max(1_000_000),
  opening_hours: z.string().trim(),
  tags: z.string(),
  description: z.string().trim().max(500, "500자까지 쓸 수 있어요"),
});
type Values = z.infer<typeof schema>;

const DEFAULTS: Partial<Values> = { name: "", category: "", region: "", address: "", is_free: true, price_per_person: 0, opening_hours: "", tags: "", description: "" };

export default function AdminAttractionsPage() {
  const categories = useCategories();
  const regions = useAdminRegions();
  const create = useCreatePlace();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: DEFAULTS });
  const { errors } = form.formState;
  const isFree = form.watch("is_free");
  const numeric = { setValueAs: (v: unknown) => (v === "" || v === null || v === undefined ? undefined : Number(v)) };

  const options = flattenCategories(categories.data?.items ?? []).filter((o) => o.role && DIRECT_ROLES.has(o.role));

  return (
    <>
      <AdminPageHeader title="관광지 추가" description="공원, 전시관, 문화공간처럼 수집으로 잘 잡히지 않는 곳을 직접 등록해요. 무료 장소는 예산이 빠듯한 코스에서 특히 중요해요." />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Panel title="직접 등록" description="등록하면 바로 ‘승인됨’ 상태가 되고 다음 추천부터 후보에 올라요.">
          {categories.isPending || regions.isPending ? (
            <Skeleton className="h-[420px] rounded-2xl" />
          ) : categories.isError ? (
            <ErrorState error={categories.error} onRetry={() => void categories.refetch()} size="sm" />
          ) : regions.isError ? (
            <ErrorState error={regions.error} onRetry={() => void regions.refetch()} size="sm" />
          ) : (
            <form
              noValidate
              className="grid gap-4 sm:grid-cols-2"
              onSubmit={form.handleSubmit((v) =>
                create.mutate(
                  {
                    name: v.name,
                    category: v.category,
                    region: v.region,
                    address: v.address,
                    lat: v.lat,
                    lng: v.lng,
                    is_free: v.is_free,
                    price_per_person: v.is_free ? 0 : v.price_per_person,
                    description: v.description || undefined,
                    tags: v.tags.split(",").map((t) => t.trim()).filter(Boolean),
                    // status · 운영 시간은 API 가 받지 않는다: 직접 등록은 서버가 바로 ‘승인됨’으로 만든다
                  },
                  { onSuccess: () => form.reset({ ...DEFAULTS, region: v.region, category: v.category }) },
                ),
              )}
            >
              <Field id="a-name" label="이름" required error={errors.name?.message} className="sm:col-span-2">
                <Input id="a-name" aria-invalid={Boolean(errors.name)} aria-describedby="a-name-desc" {...form.register("name")} />
              </Field>
              <Field id="a-category" label="분류" required error={errors.category?.message} hint={options.length === 0 ? "놀거리·문화 역할의 분류가 아직 없어요" : undefined}>
                <select id="a-category" className={nativeSelectClass} aria-invalid={Boolean(errors.category)} aria-describedby="a-category-desc" {...form.register("category")}>
                  <option value="">선택</option>
                  {options.map((o) => (
                    <option key={o.code} value={o.code}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field id="a-region" label="지역" required error={errors.region?.message}>
                <select id="a-region" className={nativeSelectClass} aria-invalid={Boolean(errors.region)} aria-describedby="a-region-desc" {...form.register("region")}>
                  <option value="">선택</option>
                  {regions.data.items.map((r) => (
                    <option key={r.slug} value={r.slug}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field id="a-address" label="주소" required error={errors.address?.message} className="sm:col-span-2">
                <Input id="a-address" aria-invalid={Boolean(errors.address)} aria-describedby="a-address-desc" {...form.register("address")} />
              </Field>
              <Field id="a-lat" label="위도" required error={errors.lat?.message}>
                <Input id="a-lat" type="number" step="0.0001" inputMode="decimal" aria-invalid={Boolean(errors.lat)} aria-describedby="a-lat-desc" {...form.register("lat", numeric)} />
              </Field>
              <Field id="a-lng" label="경도" required error={errors.lng?.message}>
                <Input id="a-lng" type="number" step="0.0001" inputMode="decimal" aria-invalid={Boolean(errors.lng)} aria-describedby="a-lng-desc" {...form.register("lng", numeric)} />
              </Field>
              <label className="flex items-center gap-2 self-end pb-2 text-sm font-bold text-ink-2">
                <input type="checkbox" className="size-4 accent-[#2F6BEA]" {...form.register("is_free")} /> 무료 입장
              </label>
              <Field id="a-price" label="1인 가격 (원)" error={errors.price_per_person?.message}>
                <Input id="a-price" type="number" step={500} inputMode="numeric" disabled={isFree} aria-describedby="a-price-desc" {...form.register("price_per_person", { valueAsNumber: true })} />
              </Field>
              <Field id="a-hours" label="운영 시간" hint="아직 직접 입력할 수 없어요. 분류별 기본 운영 시간이 적용돼요.">
                <Input id="a-hours" disabled aria-describedby="a-hours-desc" {...form.register("opening_hours")} />
              </Field>
              <Field id="a-tags" label="태그" hint="쉼표로 구분. 태그 목록에 등록된 이름만 쓸 수 있어요. 예: 산책, 조용한, 실내">
                <Input id="a-tags" aria-describedby="a-tags-desc" {...form.register("tags")} />
              </Field>
              <Field id="a-desc" label="한 줄 소개" error={errors.description?.message} className="sm:col-span-2">
                <Textarea id="a-desc" rows={3} aria-describedby="a-desc-desc" {...form.register("description")} />
              </Field>

              <div className="grid gap-2 sm:col-span-2" aria-live="polite">
                {create.isSuccess ? <FormMessage tone="success">‘{create.data.name}’ 을(를) 등록했어요. 이어서 더 등록할 수 있어요.</FormMessage> : null}
                {create.error ? <FormMessage tone="error">{create.error.detail ?? mascotCopyForError(create.error).description}</FormMessage> : null}
              </div>
              <div className="flex justify-end sm:col-span-2">
                <Button type="submit" variant="brand" size="md" disabled={create.isPending}>
                  <Plus aria-hidden /> {create.isPending ? "등록하는 중…" : "등록"}
                </Button>
              </div>
            </form>
          )}
        </Panel>

        <ImportPanel regions={regions.data?.items.map((r) => ({ slug: r.slug, name: r.name })) ?? []} />
      </div>
    </>
  );
}

function ImportPanel({ regions }: { regions: { slug: string; name: string }[] }) {
  const upload = useImportPlaces();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [region, setRegion] = useState("");

  return (
    <Panel title="파일로 한꺼번에" description="CSV 또는 JSON. 업로드하면 수집 잡으로 들어가고, 결과는 장소 승인 큐에 쌓여요.">
      <div className="grid gap-4">
        <Field id="i-file" label="파일" hint="열: name, category, address, lat, lng, price_per_person, tags · 최대 10MB">
          <input
            ref={inputRef}
            id="i-file"
            type="file"
            accept=".csv,.json,text/csv,application/json"
            aria-describedby="i-file-desc"
            onChange={(e) => {
              upload.reset();
              setFile(e.target.files?.[0] ?? null);
            }}
            className="block w-full rounded-md border border-dashed border-input bg-soft p-3 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-white file:px-3 file:py-1.5 file:text-sm file:font-extrabold file:text-blue-deep"
          />
        </Field>
        <Field id="i-region" label="지역" required hint="파일의 장소가 모두 이 지역으로 들어가요. 지역마다 파일을 나눠 올려 주세요.">
          <select id="i-region" value={region} onChange={(e) => setRegion(e.target.value)} className={nativeSelectClass} aria-describedby="i-region-desc">
            <option value="">선택</option>
            {regions.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.name}
              </option>
            ))}
          </select>
        </Field>
        <div aria-live="polite" className="grid gap-2">
          {file && file.size > 10 * 1024 * 1024 ? <FormMessage tone="error">10MB 가 넘어요. 파일을 나눠서 올려 주세요.</FormMessage> : null}
          {upload.isSuccess ? (
            <FormMessage tone={upload.data.status === "failed" || upload.data.failed ? "error" : "success"}>
              {upload.data.created === undefined
                ? `${upload.data.accepted}건을 접수했어요. (잡 ${upload.data.job_id}) 처리되면 승인 큐에 나타나요.`
                : `${upload.data.accepted}건을 읽어 ${upload.data.created}곳을 새로 등록하고 ${upload.data.updated ?? 0}곳을 갱신했어요.${upload.data.failed ? ` ${upload.data.failed}건은 실패했어요.` : ""} (잡 ${upload.data.job_id})`}
            </FormMessage>
          ) : null}
          {upload.error ? <FormMessage tone="error">{upload.error.detail ?? mascotCopyForError(upload.error).description}</FormMessage> : null}
        </div>
        <Button
          type="button"
          variant="outline"
          disabled={!file || !region || file.size > 10 * 1024 * 1024 || upload.isPending}
          onClick={() =>
            file &&
            region &&
            upload.mutate(
              { file, region },
              {
                onSuccess: () => {
                  setFile(null);
                  if (inputRef.current) inputRef.current.value = "";
                },
              },
            )
          }
        >
          <FileUp aria-hidden /> {upload.isPending ? "올리는 중…" : "업로드"}
        </Button>
      </div>
    </Panel>
  );
}
