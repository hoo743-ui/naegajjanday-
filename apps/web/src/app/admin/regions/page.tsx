"use client";

import { useState, type KeyboardEvent } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { DatabaseZap, Play, Plus, Power, X } from "lucide-react";
import { z } from "zod";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { Field, FormMessage } from "@/components/admin/Field";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useActivateRegion, useAdminRegions, useCollectRegion, useCreateRegion } from "@/lib/api/admin";
import type { AdminRegion } from "@/lib/api/types";
import { dateShort, num } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";

const schema = z.object({
  slug: z
    .string()
    .trim()
    .min(3, "3자 이상이어야 해요")
    .max(48)
    .regex(/^[a-z0-9]+(-[a-z0-9]+)*$/, "영문 소문자·숫자·하이픈만 쓸 수 있어요 (예: seoul-mangwon)"),
  name: z.string().trim().min(1, "이름을 입력해 주세요").max(30),
  parent: z.string().trim().max(48),
  lat: z.number({ error: "위도를 숫자로 입력해 주세요" }).min(33, "대한민국 범위(33~39)를 벗어났어요").max(39, "대한민국 범위(33~39)를 벗어났어요"),
  lng: z.number({ error: "경도를 숫자로 입력해 주세요" }).min(124, "대한민국 범위(124~132)를 벗어났어요").max(132, "대한민국 범위(124~132)를 벗어났어요"),
  radius_m: z.number({ error: "반경을 숫자로 입력해 주세요" }).int().min(300, "300m 이상").max(10000, "10km 이하"),
  keywords: z.array(z.string()).min(1, "수집 키워드를 하나 이상 넣어 주세요").max(12, "키워드는 12개까지예요"),
});
type Values = z.infer<typeof schema>;

export default function AdminRegionsPage() {
  const regions = useAdminRegions();
  const collect = useCollectRegion();
  const activate = useActivateRegion();
  const [formOpen, setFormOpen] = useState(false);
  const actionError = collect.error ?? activate.error;

  const columns: Column<AdminRegion>[] = [
    {
      key: "name",
      header: "지역",
      cell: (r) => (
        <span>
          <b className="block font-extrabold">{r.name}</b>
          <code className="text-xs text-muted-foreground">{r.slug}</code>
        </span>
      ),
    },
    { key: "status", header: "상태", cell: (r) => <StatusBadge status={r.status} /> },
    {
      key: "job",
      header: "수집 진행",
      cell: (r) =>
        r.last_job && (r.last_job.status === "running" || r.last_job.status === "queued") ? (
          <span className="block w-32">
            <span role="progressbar" aria-label={`${r.name} 수집 진행률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(r.last_job.progress * 100)} className="block h-2 overflow-hidden rounded-full bg-[#E3E9F4]">
              <span className="bg-grad block h-full rounded-full transition-[width] duration-700" style={{ width: `${Math.round(r.last_job.progress * 100)}%` }} />
            </span>
            <span className="tabular text-xs font-bold text-ink-2">{Math.round(r.last_job.progress * 100)}%</span>
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">{r.last_collected_at ? `${dateShort(r.last_collected_at)} 수집` : "수집 전"}</span>
        ),
    },
    { key: "places", header: "장소", align: "right", cell: (r) => <span className="tabular">{num(r.place_count)}</span> },
    { key: "pending", header: "승인 대기", align: "right", hideBelow: "md", cell: (r) => <span className="tabular">{num(r.pending_count)}</span> },
    { key: "radius", header: "반경", align: "right", hideBelow: "lg", cell: (r) => <span className="tabular">{num(r.radius_m)}m</span> },
    { key: "keywords", header: "키워드", hideBelow: "lg", cell: (r) => <span className="line-clamp-1 text-xs text-ink-2">{r.keywords.join(", ") || "-"}</span> },
    {
      key: "actions",
      header: <span className="sr-only">작업</span>,
      align: "right",
      cell: (r) => (
        <span className="flex justify-end gap-1.5">
          {r.status === "draft" || r.status === "failed" || r.status === "ready" || r.status === "active" ? (
            <Button type="button" size="sm" variant={r.status === "draft" || r.status === "failed" ? "default" : "outline"} disabled={collect.isPending} onClick={() => collect.mutate(r.slug)} aria-label={`${r.name} ${r.status === "draft" ? "수집 시작" : "다시 수집"}`}>
              <Play aria-hidden /> {r.status === "draft" ? "수집 시작" : r.status === "failed" ? "다시 시도" : "재수집"}
            </Button>
          ) : null}
          {r.status === "ready" ? (
            <Button type="button" size="sm" variant="default" className="bg-success hover:bg-success/90" disabled={activate.isPending} onClick={() => activate.mutate(r.slug)} aria-label={`${r.name} 활성화`}>
              <Power aria-hidden /> 활성화
            </Button>
          ) : null}
        </span>
      ),
    },
  ];

  return (
    <>
      <AdminPageHeader
        title="지역 관리"
        description="서비스 지역을 추가하고, 장소 수집을 돌리고, 준비되면 사용자에게 엽니다."
        actions={
          <Button type="button" variant="brand" size="md" onClick={() => setFormOpen((v) => !v)} aria-expanded={formOpen} aria-controls="region-form">
            <Plus aria-hidden /> 지역 추가
          </Button>
        }
      />

      <aside className="bg-grad-soft mb-5 flex gap-3.5 rounded-card p-5">
        <DatabaseZap aria-hidden className="mt-0.5 size-6 shrink-0 text-blue-deep" />
        <div>
          <p className="font-extrabold text-ink">새 지역 = 데이터만 추가. 코드 수정·배포 없음.</p>
          <p className="mt-1 text-sm text-ink-2">
            지역은 전부 DB 에서 읽어요. 여기서 <b>중심 좌표·반경·키워드</b>를 등록하고 <b>수집 시작</b>을 누르면 수집 잡이 장소를 모으고(수집 중), 끝나면 승인 큐로 들어가요(준비됨). 검토 뒤 <b>활성화</b>하면 그 순간부터 코스 짜기 화면의 지역 목록에 나타나요.
          </p>
        </div>
      </aside>

      {formOpen ? <RegionForm onDone={() => setFormOpen(false)} /> : null}

      {actionError ? (
        <div className="mb-4">
          <FormMessage tone="error">{mascotCopyForError(actionError).description}</FormMessage>
        </div>
      ) : null}

      <Panel title="등록된 지역" description="수집 중인 지역이 있으면 3초마다 자동으로 새로 고쳐요.">
        <DataTable
          caption="등록된 지역 목록"
          columns={columns}
          rows={regions.data?.items}
          rowKey={(r) => r.slug}
          isLoading={regions.isPending}
          error={regions.error}
          onRetry={() => void regions.refetch()}
          minWidth={720}
          empty={{ title: "아직 등록된 지역이 없어요", description: "첫 지역을 추가해 보세요. 좌표와 키워드만 있으면 돼요.", mood: "hi" }}
        />
      </Panel>
    </>
  );
}

function RegionForm({ onDone }: { onDone: () => void }) {
  const create = useCreateRegion();
  const collect = useCollectRegion();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { slug: "", name: "", parent: "", lat: undefined, lng: undefined, radius_m: 1200, keywords: [] },
  });
  const { errors } = form.formState;
  const numeric = { setValueAs: (v: unknown) => (v === "" || v === null || v === undefined ? undefined : Number(v)) };

  const submit = (startCollect: boolean) =>
    form.handleSubmit((v) =>
      create.mutate(
        { slug: v.slug, name: v.name, parent: v.parent || null, center: { lat: v.lat, lng: v.lng }, radius_m: v.radius_m, keywords: v.keywords },
        {
          onSuccess: (region) => {
            if (startCollect) collect.mutate(region.slug);
            form.reset();
            onDone();
          },
        },
      ),
    );

  return (
    <Panel title="지역 추가" description="저장하면 ‘초안’ 상태로 등록돼요. 사용자에게는 활성화 전까지 보이지 않아요." className="mb-5">
      <form id="region-form" onSubmit={(e) => void submit(false)(e)} noValidate className="grid gap-4 sm:grid-cols-2">
        <Field id="r-slug" label="슬러그" required error={errors.slug?.message} hint="URL·API 에 쓰이는 고유 키. 만든 뒤에는 바꿀 수 없어요.">
          <Input id="r-slug" placeholder="seoul-mangwon" autoComplete="off" aria-invalid={Boolean(errors.slug)} aria-describedby="r-slug-desc" {...form.register("slug")} />
        </Field>
        <Field id="r-name" label="이름" required error={errors.name?.message} hint="사용자에게 보이는 이름">
          <Input id="r-name" placeholder="망원" aria-invalid={Boolean(errors.name)} aria-describedby="r-name-desc" {...form.register("name")} />
        </Field>
        <Field id="r-lat" label="중심 위도" required error={errors.lat?.message}>
          <Input id="r-lat" type="number" step="0.0001" inputMode="decimal" placeholder="37.5560" aria-invalid={Boolean(errors.lat)} aria-describedby="r-lat-desc" {...form.register("lat", numeric)} />
        </Field>
        <Field id="r-lng" label="중심 경도" required error={errors.lng?.message}>
          <Input id="r-lng" type="number" step="0.0001" inputMode="decimal" placeholder="126.9100" aria-invalid={Boolean(errors.lng)} aria-describedby="r-lng-desc" {...form.register("lng", numeric)} />
        </Field>
        <Field id="r-radius" label="반경 (m)" required error={errors.radius_m?.message} hint="후보 장소를 찾는 기본 반경. 후보가 부족하면 엔진이 1.5배씩 두 번까지 넓혀요.">
          <Input id="r-radius" type="number" step="100" inputMode="numeric" aria-invalid={Boolean(errors.radius_m)} aria-describedby="r-radius-desc" {...form.register("radius_m", numeric)} />
        </Field>
        <Field id="r-parent" label="상위 지역 슬러그" error={errors.parent?.message} hint="선택. 예: seoul-mapo">
          <Input id="r-parent" placeholder="seoul-mapo" autoComplete="off" aria-describedby="r-parent-desc" {...form.register("parent")} />
        </Field>
        <Controller
          control={form.control}
          name="keywords"
          render={({ field }) => (
            <Field id="r-keywords" label="수집 키워드" required error={errors.keywords?.message} hint="Enter 또는 쉼표로 추가. 수집 잡이 ‘키워드 + 맛집/카페/가볼만한곳’ 으로 검색해요." className="sm:col-span-2">
              <KeywordInput id="r-keywords" value={field.value} onChange={field.onChange} invalid={Boolean(errors.keywords)} />
            </Field>
          )}
        />

        {create.error ? (
          <div className="sm:col-span-2">
            <FormMessage tone="error">{create.error.detail ?? mascotCopyForError(create.error).description}</FormMessage>
          </div>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2 sm:col-span-2">
          <Button type="button" variant="ghost" onClick={onDone}>
            취소
          </Button>
          <Button type="submit" variant="outline" disabled={create.isPending}>
            초안으로 저장
          </Button>
          <Button type="button" variant="brand" size="md" disabled={create.isPending} onClick={(e) => void submit(true)(e)}>
            <Play aria-hidden /> 저장하고 수집 시작
          </Button>
        </div>
      </form>
    </Panel>
  );
}

function KeywordInput({ id, value, onChange, invalid }: { id: string; value: string[]; onChange: (next: string[]) => void; invalid: boolean }) {
  const [text, setText] = useState("");
  const add = (raw: string) => {
    const next = raw.split(",").map((s) => s.trim()).filter((s) => s && !value.includes(s));
    if (next.length) onChange([...value, ...next]);
    setText("");
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return; // 한글 조합 중 Enter 는 무시
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(text);
    } else if (e.key === "Backspace" && !text && value.length) {
      onChange(value.slice(0, -1));
    }
  };
  return (
    <div className="flex min-h-10 flex-wrap items-center gap-1.5 rounded-md border border-input bg-white px-2 py-1.5 focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
      {value.map((kw) => (
        <span key={kw} className="inline-flex items-center gap-1 rounded-full bg-blue-soft py-1 pr-1 pl-3 text-[13px] font-extrabold text-blue-deep">
          {kw}
          <button type="button" onClick={() => onChange(value.filter((k) => k !== kw))} aria-label={`${kw} 키워드 삭제`} className="grid size-5 place-items-center rounded-full hover:bg-white">
            <X aria-hidden className="size-3" />
          </button>
        </span>
      ))}
      <input id={id} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKeyDown} onBlur={() => text && add(text)} aria-invalid={invalid} aria-describedby={`${id}-desc`} placeholder={value.length ? "" : "망원, 망원동, 망리단길"} className="min-w-[140px] flex-1 bg-transparent px-1 py-1 text-sm outline-none" />
    </div>
  );
}
