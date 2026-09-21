"use client";

import { useRef } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

interface AlternativeTabsProps {
  /** 같은 요청에서 나온 코스들 (라벨은 API 가 준다: 추천 코스 / 가성비 코스 / 덜 걷는 코스 …) */
  items: { id: string; label: string }[];
  currentId: string;
  onSelect: (id: string) => void;
}

/** WAI-ARIA tabs 패턴: ←/→ 로 이동, Home/End 지원 */
export function AlternativeTabs({ items, currentId, onSelect }: AlternativeTabsProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  if (items.length <= 1) return null;

  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    const last = items.length - 1;
    const next =
      event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (next === null) return;
    event.preventDefault();
    const target = items[next];
    refs.current[next]?.focus();
    if (target) onSelect(target.id);
  };

  return (
    <div role="tablist" aria-label="다른 코스 보기" className="no-scrollbar flex gap-1 overflow-x-auto rounded-full bg-[#EAF0FA] p-1">
      {items.map((item, i) => {
        const selected = item.id === currentId;
        return (
          <button
            key={item.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls="course-panel"
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(item.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn("relative flex-1 rounded-full px-4 py-2.5 text-sm font-extrabold whitespace-nowrap transition-colors", selected ? "text-ink" : "text-ink-2 hover:text-ink")}
          >
            {selected ? <motion.span layoutId="alt-tab" className="absolute inset-0 rounded-full bg-white shadow-soft" transition={{ type: "spring", stiffness: 400, damping: 32 }} /> : null}
            <span className="relative">{item.label.replace(/\s*코스$/, "")}</span>
          </button>
        );
      })}
    </div>
  );
}
