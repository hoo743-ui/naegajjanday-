"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Heart, X } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { usePreferences, useTags, useUpdatePreferences } from "@/lib/api/hooks";
import type { Preferences, Tag, Transport } from "@/lib/api/types";
import { transportLabel } from "@/lib/format";
import { mascotCopyForError } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";

const TRANSPORTS: Transport[] = ["walk", "transit", "car"];

/** API 의 태그 그룹은 코드(mood·food…)로만 온다 → 화면에는 우리말 이름을 보여 준다 */
const GROUP_LABEL: Record<string, string> = { mood: "분위기", food: "음식", activity: "놀거리", feature: "편의 · 조건" };
const groupLabel = (tag: Tag) => tag.group_name ?? GROUP_LABEL[tag.group] ?? "그 밖에";

export function PreferencesEditor() {
  const tags = useTags();
  const prefs = usePreferences();
  const update = useUpdatePreferences();
  const [draft, setDraft] = useState<Preferences | null>(null);

  useEffect(() => {
    if (prefs.data) setDraft(prefs.data);
  }, [prefs.data]);

  const groups = useMemo(() => {
    const map = new Map<string, Tag[]>();
    for (const tag of tags.data?.items ?? []) {
      const key = groupLabel(tag);
      map.set(key, [...(map.get(key) ?? []), tag]);
    }
    return [...map.entries()];
  }, [tags.data]);

  if (tags.isPending || prefs.isPending) return <Skeleton className="h-[260px] rounded-card" aria-label="취향 불러오는 중" />;
  if (prefs.isError) return <ErrorState error={prefs.error} onRetry={() => void prefs.refetch()} className="rounded-card bg-white shadow-soft" />;
  if (tags.isError) return <ErrorState error={tags.error} onRetry={() => void tags.refetch()} className="rounded-card bg-white shadow-soft" />;
  if (!draft) return null;

  const dirty = JSON.stringify(draft) !== JSON.stringify(prefs.data);
  const cycle = (name: string) => {
    update.reset();
    setDraft((d) => {
      if (!d) return d;
      const liked = d.liked_tags.includes(name);
      const avoided = d.disliked_tags.includes(name);
      return {
        ...d,
        liked_tags: !liked && !avoided ? [...d.liked_tags, name] : d.liked_tags.filter((t) => t !== name),
        disliked_tags: liked ? [...d.disliked_tags, name] : d.disliked_tags.filter((t) => t !== name),
      };
    });
  };

  return (
    <div className="grid gap-5 rounded-card border border-line bg-white p-6 shadow-soft">
      <p className="text-sm text-muted-foreground">
        한 번 누르면 <b className="text-blue-deep">좋아요</b>, 한 번 더 누르면 <b className="text-pink-deep">피할래요</b>. 코스를 짤 때마다 자동으로 반영돼요.
      </p>
      {groups.length === 0 ? (
        <EmptyState size="sm" title="고를 태그가 아직 없어요" />
      ) : (
        groups.map(([group, items]) => (
          <div key={group} role="group" aria-label={group}>
            <p className="mb-2 text-xs font-extrabold text-ink-2">{group}</p>
            <div className="flex flex-wrap gap-2">
              {items.map((tag) => {
                const like = draft.liked_tags.includes(tag.name);
                const avoid = draft.disliked_tags.includes(tag.name);
                return (
                  <button
                    key={tag.name}
                    type="button"
                    onClick={() => cycle(tag.name)}
                    aria-label={`${tag.name}: ${like ? "좋아요" : avoid ? "피할래요" : "선택 안 함"}`}
                    className={cn(
                      "rounded-full border-2 px-4 py-2 text-sm font-extrabold transition-all duration-150 active:scale-95",
                      like && "border-blue-deep bg-blue-deep text-white",
                      avoid && "border-pink-deep bg-pink-soft text-pink-deep line-through",
                      !like && !avoid && "border-transparent bg-[#F0F4FA] text-ink-2 hover:bg-line",
                    )}
                  >
                    {like ? <Heart aria-hidden className="mr-1 -mt-0.5 inline size-3.5 fill-current" /> : null}
                    {avoid ? <X aria-hidden className="mr-1 -mt-0.5 inline size-3.5" /> : null}
                    {tag.name}
                  </button>
                );
              })}
            </div>
          </div>
        ))
      )}

      <fieldset>
        <legend className="mb-2 text-xs font-extrabold text-ink-2">주로 이렇게 다녀요</legend>
        <div className="flex flex-wrap gap-2">
          {TRANSPORTS.map((mode) => (
            <label key={mode} className="relative">
              <input
                type="radio"
                name="pref-transport"
                className="peer sr-only"
                checked={draft.transport === mode}
                onChange={() => {
                  update.reset();
                  setDraft((d) => (d ? { ...d, transport: mode } : d));
                }}
              />
              <span className="block cursor-pointer rounded-full bg-[#F0F4FA] px-4 py-2 text-sm font-extrabold text-ink-2 peer-checked:bg-ink peer-checked:text-white peer-focus-visible:outline-[3px] peer-focus-visible:outline-offset-2 peer-focus-visible:outline-blue">
                {transportLabel(mode)}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-wrap items-center gap-3" aria-live="polite">
        <Button type="button" variant="brand" size="md" disabled={!dirty || update.isPending} onClick={() => update.mutate(draft)}>
          {update.isPending ? "저장하는 중…" : "취향 저장"}
        </Button>
        {update.isSuccess && !dirty ? (
          <span className="inline-flex items-center gap-1 text-sm font-bold text-success">
            <Check aria-hidden className="size-4" /> 저장했어요
          </span>
        ) : null}
        {update.error ? <span className="text-sm font-bold text-danger">{mascotCopyForError(update.error).description}</span> : null}
      </div>
    </div>
  );
}
