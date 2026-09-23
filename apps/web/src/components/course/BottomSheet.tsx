"use client";

import type { ReactNode } from "react";
import { X } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  /** 맨 아래 고정 행동(한두 개) */
  footer?: ReactNode;
}

/**
 * 결과 화면의 바텀시트 하나 (docs/42): 길찾기 · 바꾸기 · 다시 짜기가 같은 모양을 쓴다.
 * 아래에서 올라오고, 넓은 화면에서도 가운데 520px — 엄지가 닿는 곳에 질문 하나와 행동 하나.
 */
export function BottomSheet({ open, onClose, title, description, children, footer }: BottomSheetProps) {
  return (
    <Sheet open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <SheetContent side="bottom" showCloseButton={false} className="mx-auto max-h-[85dvh] w-full max-w-[520px] gap-0 rounded-t-2xl border-line bg-paper p-0 sm:bottom-6 sm:rounded-2xl">
        <div className="flex items-start justify-between gap-3 px-5 pt-5">
          <div className="min-w-0">
            <SheetTitle className="text-h3 font-bold text-ink">{title}</SheetTitle>
            {description ? <SheetDescription className="mt-0.5 text-body-sm text-muted-foreground">{description}</SheetDescription> : <SheetDescription className="sr-only">{title}</SheetDescription>}
          </div>
          <button type="button" onClick={onClose} aria-label="닫기" className="-mt-2 -mr-2 grid size-11 shrink-0 place-items-center rounded-full text-ink-2 hover:bg-ink/[0.06]">
            <X aria-hidden className="size-5" />
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto px-5 pt-4 pb-4">{children}</div>
        {footer ? <div className="border-t border-dashed border-ink/20 px-5 pt-3 pb-[max(16px,env(safe-area-inset-bottom))]">{footer}</div> : null}
      </SheetContent>
    </Sheet>
  );
}
