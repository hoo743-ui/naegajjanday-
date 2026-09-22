"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { track } from "@/lib/analytics";
import { useBanners } from "@/lib/api/hooks";

/**
 * 운영자가 관리자 화면(/admin/banners)에서 올린 소식. 없으면 아무것도 그리지 않는다.
 * 광고판이 아니라 한 줄 소식이다: 그림 없이 제목과 한 줄 설명만, 화면의 주인공(예산)을 가리지 않는다.
 */
export function BannerStrip({ placement }: { placement: string }) {
  const banners = useBanners(placement);
  const items = banners.data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <aside aria-label="소식" className="wrap py-4">
      <ul className="grid gap-2 sm:grid-cols-2">
        {items.slice(0, 2).map((b) => {
          const external = /^https?:\/\//.test(b.link_url);
          const body = (
            <>
              <span className="min-w-0">
                <b className="block truncate text-body font-extrabold text-ink">{b.title}</b>
                {b.subtitle ? <span className="block truncate text-caption text-muted-foreground">{b.subtitle}</span> : null}
              </span>
              <ArrowRight aria-hidden className="size-4 shrink-0 text-blue-deep" />
            </>
          );
          const className = "flex items-center justify-between gap-3 rounded-2xl border border-line bg-white px-4 py-3 hover:border-blue-deep";
          const onClick = () => track("banner_clicked", { banner_id: b.id, placement });
          return (
            <li key={b.id}>
              {external ? (
                <a href={b.link_url} target="_blank" rel="noreferrer" className={className} onClick={onClick}>
                  {body}
                </a>
              ) : (
                <Link href={b.link_url || "/plan"} className={className} onClick={onClick}>
                  {body}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
