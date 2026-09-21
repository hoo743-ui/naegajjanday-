import { http, HttpResponse } from "msw";
import { banners, categories, purposes, regions, tags } from "../fixtures/meta";
import { latency, u } from "./utils";

export const metaHandlers = [
  http.get(u("/meta/regions"), async ({ request }) => {
    await latency(180);
    const url = new URL(request.url);
    const q = url.searchParams.get("q")?.trim().toLowerCase();
    const parent = url.searchParams.get("parent");
    const items = regions.filter(
      (r) =>
        (!q || r.name.toLowerCase().includes(q) || r.parent?.name.toLowerCase().includes(q) || r.slug.includes(q)) &&
        (!parent || r.parent?.slug === parent || r.slug.startsWith(`${parent}-`)),
    );
    return HttpResponse.json({ items });
  }),
  http.get(u("/meta/purposes"), async () => {
    await latency(150);
    return HttpResponse.json({ items: purposes });
  }),
  http.get(u("/meta/categories"), () => HttpResponse.json({ items: categories })),
  http.get(u("/meta/tags"), async ({ request }) => {
    await latency(150);
    const group = new URL(request.url).searchParams.get("group");
    return HttpResponse.json({ items: group ? tags.filter((t) => t.group === group) : tags });
  }),
  // 실제 API 와 같은 계약: LLM 이 설정돼 있을 때만 chat=true. 목에는 대화 핸들러가 있으므로 true.
  http.get(u("/meta/features"), () => HttpResponse.json({ chat: true })),
  http.get(u("/meta/banners"), ({ request }) => {
    const placement = new URL(request.url).searchParams.get("placement");
    return HttpResponse.json({ items: placement ? banners.filter((b) => b.placement === placement) : banners });
  }),
];
