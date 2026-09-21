"use client";

import { useEffect, useState } from "react";
import { Check, Plus, RotateCcw, Scale, Trash2 } from "lucide-react";
import { AdminPageHeader, Panel } from "@/components/admin/AdminShell";
import { FormMessage, nativeSelectClass } from "@/components/admin/Field";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { useSaveTemplate, useScoringProfile, useTemplates, useUpdateScoringProfile } from "@/lib/api/admin";
import { useCategories, usePurposes } from "@/lib/api/hooks";
import { SCORE_FEATURES, type CourseTemplate, type ScoreBreakdown, type TemplateSlot } from "@/lib/api/types";
import { FEATURE_INFO, dateShort, roleLabel, won } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";

const EPS = 0.005;
const sumOf = (values: number[]) => values.reduce((a, b) => a + b, 0);

export default function AdminScoringPage() {
  const purposes = usePurposes();
  const [purpose, setPurpose] = useState("");

  useEffect(() => {
    const first = purposes.data?.items[0];
    if (!purpose && first) setPurpose(first.code);
  }, [purposes.data, purpose]);

  return (
    <>
      <AdminPageHeader
        title="추천 설정"
        description="장소 점수의 8개 피처 가중치와 코스 템플릿을 목적별로 조정해요. 코드 배포 없이 다음 추천부터 바로 반영됩니다."
        actions={
          purposes.data && purposes.data.items.length > 0 ? (
            <label className="flex items-center gap-2 text-sm font-extrabold text-ink-2">
              목적
              <select value={purpose} onChange={(e) => setPurpose(e.target.value)} className={cn(nativeSelectClass, "w-40")}>
                {purposes.data.items.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null
        }
      />

      {purposes.isPending ? (
        <Skeleton className="h-[420px] rounded-card" />
      ) : purposes.isError ? (
        <ErrorState error={purposes.error} onRetry={() => void purposes.refetch()} />
      ) : purposes.data.items.length === 0 ? (
        <EmptyState title="등록된 목적이 없어요" description="목적이 있어야 가중치를 설정할 수 있어요." />
      ) : purpose ? (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
          <WeightsEditor key={`w-${purpose}`} purpose={purpose} />
          <TemplatesEditor key={`t-${purpose}`} purpose={purpose} />
        </div>
      ) : null}
    </>
  );
}

// ── 가중치 ──────────────────────────────────────────────────
function WeightsEditor({ purpose }: { purpose: string }) {
  const profile = useScoringProfile(purpose);
  const update = useUpdateScoringProfile();
  const [weights, setWeights] = useState<ScoreBreakdown | null>(null);

  useEffect(() => {
    if (profile.data) setWeights(profile.data.weights);
  }, [profile.data]);

  if (profile.isPending) return <Skeleton className="h-[560px] rounded-card" />;
  if (profile.isError) return <Panel title="피처 가중치"><ErrorState error={profile.error} onRetry={() => void profile.refetch()} size="sm" /></Panel>;
  if (!weights) return null;

  const total = sumOf(SCORE_FEATURES.map((k) => weights[k]));
  const valid = Math.abs(total - 1) < EPS;
  const dirty = SCORE_FEATURES.some((k) => Math.abs(weights[k] - profile.data.weights[k]) > 1e-9);

  const normalize = () => {
    if (total <= 0) return;
    const scaled = SCORE_FEATURES.map((k) => Math.round((weights[k] / total) * 100) / 100);
    // 반올림 오차는 가장 큰 항목에 몰아서 합을 정확히 1.00 으로 맞춘다
    const diff = Math.round((1 - sumOf(scaled)) * 100) / 100;
    const maxIndex = scaled.indexOf(Math.max(...scaled));
    const next = { ...weights };
    SCORE_FEATURES.forEach((k, i) => {
      next[k] = Math.round(((scaled[i] ?? 0) + (i === maxIndex ? diff : 0)) * 100) / 100;
    });
    setWeights(next);
  };

  return (
    <Panel
      title="피처 가중치"
      description={`프로필 v${profile.data.version} · ${dateShort(profile.data.updated_at)} 수정${profile.data.updated_by ? ` (${profile.data.updated_by})` : ""}${profile.data.experiment_key ? ` · 실험 ${profile.data.experiment_key}` : ""}`}
    >
      <p className="mb-4 rounded-xl bg-soft px-3.5 py-2.5 text-[13px] text-ink-2">
        장소 점수 S = Σ w × f. 모든 가중치의 <b>합이 1.00</b>이어야 저장할 수 있어요.
      </p>
      <ul className="grid gap-4">
        {SCORE_FEATURES.map((key) => {
          const info = FEATURE_INFO[key];
          const id = `w-${key}`;
          return (
            <li key={key}>
              <div className="flex items-baseline justify-between gap-3">
                <label id={`${id}-label`} htmlFor={`${id}-num`} className="text-sm font-extrabold text-ink">
                  {info.label} <code className="ml-1 text-xs font-medium text-muted-foreground">{key}</code>
                </label>
                <Input
                  id={`${id}-num`}
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={weights[key]}
                  onChange={(e) => {
                    update.reset();
                    setWeights({ ...weights, [key]: Math.max(0, Math.min(1, Number(e.target.value) || 0)) });
                  }}
                  className="tabular h-8 w-20 text-right font-extrabold"
                />
              </div>
              <Slider
                aria-labelledby={`${id}-label`}
                min={0}
                max={0.6}
                step={0.01}
                value={[Math.min(0.6, weights[key])]}
                onValueChange={([v]) => {
                  update.reset();
                  setWeights({ ...weights, [key]: Math.round((v ?? 0) * 100) / 100 });
                }}
                className="mt-2"
              />
              <p className="mt-1 text-xs text-muted-foreground">{info.hint}</p>
            </li>
          );
        })}
      </ul>

      <div className="sticky bottom-3 mt-5 flex flex-wrap items-center gap-2 rounded-2xl border bg-white/95 p-3 shadow-card backdrop-blur" aria-live="polite">
        <p className={cn("tabular mr-auto flex items-center gap-2 rounded-xl px-3 py-1.5 text-sm font-extrabold", valid ? "bg-success-soft text-success" : "bg-pink-soft text-pink-deep")}>
          <Scale aria-hidden className="size-4" />
          합계 {total.toFixed(2)}
          {valid ? "" : total > 1 ? ` (${(total - 1).toFixed(2)} 초과)` : ` (${(1 - total).toFixed(2)} 부족)`}
        </p>
        <Button type="button" variant="ghost" size="sm" disabled={!dirty} onClick={() => setWeights(profile.data.weights)}>
          <RotateCcw aria-hidden /> 되돌리기
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={valid || total <= 0} onClick={normalize}>
          합계 1로 정규화
        </Button>
        <Button type="button" variant="brand" size="md" disabled={!valid || !dirty || update.isPending} onClick={() => update.mutate({ purpose, weights })}>
          {update.isPending ? "저장하는 중…" : "가중치 저장"}
        </Button>
      </div>
      {update.isSuccess && !dirty ? <div className="mt-3"><FormMessage tone="success">저장했어요. 다음 추천부터 v{profile.data.version} 프로필이 적용돼요.</FormMessage></div> : null}
      {update.error ? <div className="mt-3"><FormMessage tone="error">{update.error.detail ?? mascotCopyForError(update.error).description}</FormMessage></div> : null}
    </Panel>
  );
}

// ── 템플릿 ──────────────────────────────────────────────────
function TemplatesEditor({ purpose }: { purpose: string }) {
  const templates = useTemplates(purpose);

  return (
    <Panel title="코스 템플릿" description="슬롯 순서대로 코스가 짜여요. 예산 배분(share)의 합은 1.00 이어야 해요. 선택 슬롯은 예산이 빠듯하면 뒤에서부터 빠져요.">
      {templates.isPending ? (
        <Skeleton className="h-[320px] rounded-2xl" />
      ) : templates.isError ? (
        <ErrorState error={templates.error} onRetry={() => void templates.refetch()} size="sm" />
      ) : templates.data.items.length === 0 ? (
        <EmptyState size="sm" title="이 목적의 템플릿이 아직 없어요" description="템플릿이 없으면 이 목적으로는 코스를 만들 수 없어요." />
      ) : (
        <div className="grid gap-4">
          {templates.data.items.map((t) => (
            <TemplateCard key={t.id} template={t} />
          ))}
        </div>
      )}
    </Panel>
  );
}

function TemplateCard({ template }: { template: CourseTemplate }) {
  const save = useSaveTemplate();
  const categories = useCategories();
  const [slots, setSlots] = useState<TemplateSlot[]>(template.slots);

  useEffect(() => setSlots(template.slots), [template.slots]);

  // 슬롯 역할 선택지: 카테고리 트리에 등장하는 course_role + 이미 쓰인 값 (하드코딩 없음)
  const roles = [...new Set([...(categories.data?.items ?? []).flatMap((c) => [c.course_role, ...(c.children ?? []).map((ch) => ch.course_role)]), ...slots.map((s) => s.role)])].filter((r): r is string => Boolean(r));

  const total = sumOf(slots.map((s) => s.budget_share));
  const valid = slots.length > 0 && Math.abs(total - 1) < EPS;
  const dirty = JSON.stringify(slots) !== JSON.stringify(template.slots);
  const patch = (index: number, change: Partial<TemplateSlot>) => {
    save.reset();
    setSlots((prev) => prev.map((s, i) => (i === index ? { ...s, ...change } : s)));
  };

  return (
    <article className="rounded-2xl border p-4" aria-label={`템플릿 ${template.name}`}>
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-extrabold">{template.name}</h3>
        <p className="tabular text-xs font-bold text-muted-foreground">
          {template.time_band} · {template.party_size_min}~{template.party_size_max}명 · 1인 {won(template.min_budget_per_person)}부터{template.is_active ? "" : " · 비활성"}
        </p>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <caption className="sr-only">{template.name} 슬롯 편집</caption>
          <thead>
            <tr className="text-left text-xs font-extrabold text-muted-foreground">
              <th scope="col" className="w-8 pb-2">#</th>
              <th scope="col" className="pb-2">역할</th>
              <th scope="col" className="pb-2">예산 배분</th>
              <th scope="col" className="pb-2">체류(분)</th>
              <th scope="col" className="pb-2 text-center">선택</th>
              <th scope="col" className="pb-2 text-center">순서 자유</th>
              <th scope="col" className="pb-2"><span className="sr-only">삭제</span></th>
            </tr>
          </thead>
          <tbody>
            {slots.map((slot, i) => (
              <tr key={i} className="border-t">
                <td className="tabular py-2 font-extrabold text-ink-2">{i + 1}</td>
                <td className="py-2 pr-2">
                  <select aria-label={`${i + 1}번 슬롯 역할`} value={slot.role} onChange={(e) => patch(i, { role: e.target.value })} className={cn(nativeSelectClass, "w-32")}>
                    {roles.map((r) => (
                      <option key={r} value={r}>
                        {roleLabel(r)} ({r})
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-2 pr-2">
                  <Input aria-label={`${i + 1}번 슬롯 예산 배분`} type="number" min={0} max={1} step={0.05} value={slot.budget_share} onChange={(e) => patch(i, { budget_share: Math.max(0, Math.min(1, Number(e.target.value) || 0)) })} className="tabular h-9 w-24 text-right" />
                </td>
                <td className="py-2 pr-2">
                  <Input aria-label={`${i + 1}번 슬롯 체류 시간(분)`} type="number" min={10} max={480} step={5} value={slot.stay_min} onChange={(e) => patch(i, { stay_min: Math.max(0, Number(e.target.value) || 0) })} className="tabular h-9 w-24 text-right" />
                </td>
                <td className="py-2 text-center">
                  <Switch aria-label={`${i + 1}번 슬롯: 예산이 빠듯하면 빼도 되는 선택 슬롯`} checked={slot.is_optional} onCheckedChange={(v) => patch(i, { is_optional: v })} />
                </td>
                <td className="py-2 text-center">
                  <Switch aria-label={`${i + 1}번 슬롯: 동선 최적화 때 방문 순서를 바꿔도 됨`} checked={slot.is_order_flexible} onCheckedChange={(v) => patch(i, { is_order_flexible: v })} />
                </td>
                <td className="py-2 text-right">
                  <Button type="button" variant="ghost" size="icon-sm" aria-label={`${i + 1}번 슬롯 삭제`} disabled={slots.length <= 1} onClick={() => (save.reset(), setSlots((prev) => prev.filter((_, j) => j !== i)))}>
                    <Trash2 aria-hidden />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2" aria-live="polite">
        <Button type="button" variant="outline" size="sm" disabled={roles.length === 0} onClick={() => (save.reset(), setSlots((prev) => [...prev, { role: roles[0] ?? "", budget_share: 0, stay_min: 50, is_optional: true, is_order_flexible: false }]))}>
          <Plus aria-hidden /> 슬롯 추가
        </Button>
        <p className={cn("tabular mr-auto rounded-lg px-2.5 py-1 text-[13px] font-extrabold", valid ? "bg-success-soft text-success" : "bg-pink-soft text-pink-deep")}>배분 합계 {total.toFixed(2)}</p>
        {save.isSuccess && !dirty ? (
          <span className="inline-flex items-center gap-1 text-[13px] font-bold text-success">
            <Check aria-hidden className="size-4" /> 저장했어요
          </span>
        ) : null}
        <Button type="button" variant="ghost" size="sm" disabled={!dirty} onClick={() => setSlots(template.slots)}>
          되돌리기
        </Button>
        <Button type="button" size="sm" disabled={!valid || !dirty || save.isPending} onClick={() => save.mutate({ id: template.id, input: { slots } })}>
          {save.isPending ? "저장하는 중…" : "템플릿 저장"}
        </Button>
      </div>
      {save.error ? <div className="mt-2"><FormMessage tone="error">{save.error.detail ?? mascotCopyForError(save.error).description}</FormMessage></div> : null}
    </article>
  );
}
