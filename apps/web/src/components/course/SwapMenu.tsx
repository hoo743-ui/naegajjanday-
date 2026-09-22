"use client";

import { MapPin, RefreshCw, Shuffle, ThumbsUp, TrendingDown, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { SwapStrategy } from "@/lib/api/types";

const OPTIONS: { strategy: SwapStrategy; label: string; hint: string; icon: LucideIcon }[] = [
  { strategy: "cheaper", label: "더 저렴하게", hint: "이보다 싼 곳으로", icon: TrendingDown },
  { strategy: "closer", label: "더 가까이", hint: "앞 장소에서 덜 걷게", icon: MapPin },
  // 평점·리뷰 자료가 아직 없다 → 이 전략은 짠이 점수가 가장 높은 대안을 준다. 없는 "평점"을 약속하지 않는다.
  { strategy: "higher_rated", label: "점수 높은 곳", hint: "짠이 점수가 가장 높은 곳으로", icon: ThumbsUp },
];

interface SwapMenuProps {
  placeName: string;
  pending: boolean;
  onSwap: (strategy: SwapStrategy) => void;
}

/** 한 곳만 교체. 나머지는 고정한 채 서버가 동선·총액을 다시 계산한다. (Radix 메뉴 → 방향키·Esc 지원) */
export function SwapMenu({ placeName, pending, onSwap }: SwapMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="soft" size="sm" disabled={pending} aria-label={`${placeName} 다른 곳으로 바꾸기`} className="rounded-full px-3.5">
          <RefreshCw aria-hidden className={pending ? "animate-spin" : undefined} />
          {pending ? "찾는 중…" : "바꾸기"}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60 rounded-2xl p-1.5">
        <DropdownMenuLabel className="text-caption text-muted-foreground">여기만 바꿔요. 나머지는 그대로예요</DropdownMenuLabel>
        {OPTIONS.map((o) => (
          <DropdownMenuItem key={o.strategy} onSelect={() => onSwap(o.strategy)} className="cursor-pointer gap-3 rounded-xl py-2.5">
            <o.icon aria-hidden className="size-4 text-blue-deep" />
            <span>
              <b className="block text-body-sm font-semibold text-ink">{o.label}</b>
              <span className="block text-caption text-muted-foreground">{o.hint}</span>
            </span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => onSwap("random_top")} className="cursor-pointer gap-3 rounded-xl py-2.5">
          <Shuffle aria-hidden className="size-4 text-blue-deep" />
          <b className="text-body-sm font-semibold text-ink">아무 데나 괜찮은 곳</b>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
