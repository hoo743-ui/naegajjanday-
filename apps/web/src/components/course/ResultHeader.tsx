"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, Share2, SlidersHorizontal } from "lucide-react";
import { Jjani } from "@/components/mascot/Jjani";

interface ResultHeaderProps {
  /** "홍대입구 · 데이트" — 무엇을 보고 있는지 */
  title?: string;
  /** "추천 코스 · 2명 · 예산 80,000원" */
  subtitle?: string;
  /** 조건 바꾸기: 위저드로 돌아가는 주소. 없으면(남의 코스 · 오류 화면) 숨긴다 */
  changeHref?: string;
  onShare?: () => void;
  shared?: boolean;
}

/**
 * 결과 화면의 헤더 (docs/25 §5): 뒤로 · 지금 보는 코스 · 조건 바꾸기 · 공유. 그 이상은 없다.
 * 코스를 받은 사람에게 랜딩의 메뉴를 다시 보여 주지 않는다 — 여기서 할 일은 이 코스를 쓰는 것이다.
 * 공유는 데스크톱에서만 여기에 있다. 모바일은 엄지가 닿는 하단 바에 있다(같은 이름의 버튼이 한 화면에 둘이 되지 않게).
 */
export function ResultHeader({ title, subtitle, changeHref, onShare, shared = false }: ResultHeaderProps) {
  const router = useRouter();
  const back = () => {
    // 공유 링크로 막 들어온 사람에게는 돌아갈 곳이 없다 → 코스 짜기로
    if (window.history.length > 1) router.back();
    else router.push("/plan");
  };

  return (
    <header className="sticky top-0 z-50 border-b border-ink/[0.07] bg-paper/92 pt-[env(safe-area-inset-top,0px)] backdrop-blur-xl">
      <div className="flex h-(--header-h) items-center gap-1 px-2 sm:gap-2 sm:px-4 lg:px-5">
        <button type="button" onClick={back} aria-label="뒤로" className="grid size-11 shrink-0 place-items-center rounded-full text-ink hover:bg-ink/[0.05]">
          <ArrowLeft aria-hidden className="size-5" />
        </button>
        <Link href="/" aria-label="내가짠데이 홈" className="grid size-11 shrink-0 place-items-center rounded-full hover:bg-ink/[0.05]">
          <Jjani mood="hi" size={28} animated={false} decorative />
        </Link>

        <div className="min-w-0 flex-1 px-1">
          {title ? <p className="truncate text-body leading-tight font-bold text-ink">{title}</p> : null}
          {subtitle ? <p className="tabular truncate text-caption leading-tight font-semibold text-muted-foreground">{subtitle}</p> : null}
        </div>

        {changeHref ? (
          <Link
            href={changeHref}
            aria-label="조건 바꾸기"
            className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-full px-3 text-body-sm font-semibold text-blue-deep hover:bg-blue-soft"
          >
            <SlidersHorizontal aria-hidden className="size-4" />
            <span className="max-sm:sr-only">조건 바꾸기</span>
          </Link>
        ) : null}
        {onShare ? (
          <button
            type="button"
            onClick={onShare}
            aria-label="코스 공유하기"
            className="hidden h-11 shrink-0 items-center gap-1.5 rounded-full border border-line bg-white px-4 text-body-sm font-semibold text-ink hover:border-ink-2 lg:inline-flex"
          >
            {shared ? <Check aria-hidden className="size-4" /> : <Share2 aria-hidden className="size-4" />}
            {shared ? "링크 복사됨" : "공유"}
          </button>
        ) : null}
      </div>
    </header>
  );
}
