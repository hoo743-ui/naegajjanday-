import { http, HttpResponse } from "msw";
import type { CourseRole } from "@/lib/api/types";
import { placesFor } from "../fixtures/course-engine";
import { buildAttractions, buildEvents } from "../fixtures/explore";
import { regions } from "../fixtures/meta";
import { latency, paginate, problem, u } from "./utils";

const ROLES: CourseRole[] = ["MEAL", "CAFE", "ATTRACTION", "CULTURE", "BAR"];

function searchPlaces(url: URL) {
  const q = url.searchParams.get("q")?.trim().toLowerCase() ?? "";
  const region = url.searchParams.get("region");
  const role = url.searchParams.get("role");
  const maxPrice = Number(url.searchParams.get("max_price")) || Infinity;
  const pool = (region ? regions.filter((r) => r.slug === region) : regions).flatMap((r) =>
    (role ? [role] : ROLES).flatMap((ro) => placesFor(r.slug, ro)),
  );
  return pool.filter(
    (p) =>
      p.price_per_person <= maxPrice &&
      (!q || p.name.toLowerCase().includes(q) || p.tags.some((t) => t.includes(q)) || (p.category_name ?? "").toLowerCase().includes(q)),
  );
}

export const exploreHandlers = [
  http.get(u("/attractions"), async ({ request }) => {
    await latency(350);
    const url = new URL(request.url);
    const region = url.searchParams.get("region");
    const types = url.searchParams.get("type")?.split(",").filter(Boolean) ?? [];
    const date = url.searchParams.get("date");
    const q = url.searchParams.get("q")?.trim().toLowerCase();
    const items = buildAttractions().filter(
      (a) =>
        (!region || a.region?.slug === region) &&
        (types.length === 0 || types.includes(a.type)) &&
        // 날짜를 주면: 상시 장소는 통과, 기간이 있는 것은 그날 진행 중인 것만
        (!date || !a.period || (a.period.starts_on <= date && date <= a.period.ends_on)) &&
        (!q || a.name.toLowerCase().includes(q) || a.tags.some((t) => t.includes(q)) || a.summary.toLowerCase().includes(q)),
    );
    return HttpResponse.json(paginate(items, url, 24));
  }),

  http.get(u("/events"), async ({ request }) => {
    await latency(250);
    const url = new URL(request.url);
    const region = url.searchParams.get("region");
    const from = url.searchParams.get("from");
    const to = url.searchParams.get("to");
    const items = buildEvents()
      .filter((e) => (!region || e.region?.slug === region) && (!to || e.starts_on <= to) && (!from || e.ends_on >= from))
      .sort((a, b) => a.ends_on.localeCompare(b.ends_on));
    return HttpResponse.json(paginate(items, url, 20));
  }),

  http.get(u("/places/search"), async ({ request }) => {
    await latency(250);
    const url = new URL(request.url);
    return HttpResponse.json(paginate(searchPlaces(url), url, 20));
  }),

  http.get(u("/places/autocomplete"), ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q")?.trim();
    if (!q) return HttpResponse.json({ items: [] });
    const items = searchPlaces(url)
      .slice(0, 8)
      .map((p) => ({ id: p.id, name: p.name, category_name: p.category_name ?? p.category }));
    return HttpResponse.json({ items });
  }),

  http.post(u("/places/suggest"), async ({ request }) => {
    await latency(400);
    const body = (await request.json().catch(() => null)) as { name?: string } | null;
    if (!body?.name) return problem(422, "VALIDATION_ERROR", "입력을 확인해 주세요", "장소 이름은 꼭 적어 주세요.");
    return HttpResponse.json({ id: `p_suggest_${Date.now().toString(36)}`, status: "pending" }, { status: 201 });
  }),
];
