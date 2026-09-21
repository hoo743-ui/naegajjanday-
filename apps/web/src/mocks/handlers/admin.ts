import { http, HttpResponse } from "msw";
import type {
  AdminBanner,
  AdminBannerInput,
  AdminEvent,
  AdminEventInput,
  AdminPlace,
  AdminPlaceInput,
  AdminRegion,
  AdminRegionInput,
  CourseTemplate,
  IngestionJob,
  ScoreBreakdown,
} from "@/lib/api/types";
import { SCORE_FEATURES } from "@/lib/api/types";
import {
  COLLECT_DURATION_MS,
  adminRegions,
  banners,
  collectStartedAt,
  events,
  jobs,
  places,
  recommendationAnalytics,
  revisions,
  scoringProfiles,
  systemHealth,
  tagAffinities,
  templates,
  topPlaces,
  userAnalytics,
} from "../fixtures/admin";
import { categories, regions as metaRegions, tags } from "../fixtures/meta";
import { latency, paginate, problem, u } from "./utils";

const now = () => new Date().toISOString();
const uid = (prefix: string) => `${prefix}_${Date.now().toString(36)}${Math.round(Math.random() * 1e4).toString(36)}`;
const notFound = (what: string) => problem(404, "NOT_FOUND", `${what}을(를) 찾을 수 없어요`);
const noContent = () => new HttpResponse(null, { status: 204 });

function findCategory(code: string | undefined) {
  for (const top of categories) {
    if (top.code === code) return top;
    const child = top.children?.find((c) => c.code === code);
    if (child) return child;
  }
  return undefined;
}

function regionRef(slug: string | undefined | null) {
  const found = adminRegions.find((r) => r.slug === slug);
  return found ? { slug: found.slug, name: found.name } : null;
}

/** 수집 잡 진행: GET 할 때마다 경과 시간으로 상태를 계산한다 */
function tickCollections() {
  for (const [slug, startedAt] of collectStartedAt) {
    const region = adminRegions.find((r) => r.slug === slug);
    const job = jobs.find((j) => j.id === region?.last_job?.id);
    if (!region || !job) continue;
    const progress = Math.min(1, (Date.now() - startedAt) / COLLECT_DURATION_MS);
    job.progress = Number(progress.toFixed(2));
    job.status = progress >= 1 ? "succeeded" : "running";
    job.collected = Math.round(progress * 420);
    region.last_job = { id: job.id, status: job.status, progress: job.progress };
    if (progress >= 1) {
      job.finished_at = now();
      region.status = "ready";
      region.place_count += job.collected;
      region.pending_count += job.collected;
      region.last_collected_at = job.finished_at;
      collectStartedAt.delete(slug);
    }
  }
}

function startCollect(region: AdminRegion, provider = "kakao_local"): IngestionJob {
  const job: IngestionJob = {
    id: uid("job"),
    region: region.slug,
    provider,
    status: "running",
    progress: 0,
    collected: 0,
    started_at: now(),
    finished_at: null,
    error: null,
  };
  jobs.unshift(job);
  region.status = "collecting";
  region.last_job = { id: job.id, status: "running", progress: 0 };
  collectStartedAt.set(region.slug, Date.now());
  return job;
}

function applyPlaceInput(place: AdminPlace, input: AdminPlaceInput) {
  const changes: Record<string, { from: unknown; to: unknown }> = {};
  const set = <K extends keyof AdminPlace>(key: K, value: AdminPlace[K] | undefined) => {
    if (value === undefined || JSON.stringify(place[key]) === JSON.stringify(value)) return;
    changes[key] = { from: place[key], to: value };
    place[key] = value;
  };
  set("name", input.name);
  set("address", input.address);
  set("lat", input.lat);
  set("lng", input.lng);
  set("price_per_person", input.price_per_person);
  set("is_free", input.is_free);
  set("tags", input.tags);
  set("status", input.status);
  if (input.category) {
    const cat = findCategory(input.category);
    set("category", input.category);
    if (cat) {
      place.category_name = cat.name;
      place.course_role = cat.course_role;
    }
  }
  if (input.region) set("region", regionRef(input.region));
  place.updated_at = now();
  if (Object.keys(changes).length > 0) {
    const list = revisions.get(place.id) ?? [];
    list.unshift({ id: uid("rev"), actor: "mock-admin", created_at: place.updated_at, changes });
    revisions.set(place.id, list);
  }
}

export const adminHandlers = [
  // ── 장소 ──────────────────────────────────────────────────
  http.get(u("/admin/places"), async ({ request }) => {
    await latency(250);
    const url = new URL(request.url);
    const status = url.searchParams.get("status");
    const q = url.searchParams.get("q")?.trim().toLowerCase();
    const region = url.searchParams.get("region");
    const filtered = places
      .filter((p) => (!status || p.status === status) && (!region || p.region?.slug === region))
      .filter((p) => !q || p.name.toLowerCase().includes(q) || p.address.toLowerCase().includes(q))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    return HttpResponse.json({ ...paginate(filtered, url, 50), total: filtered.length });
  }),

  http.post(u("/admin/places/bulk-approve"), async ({ request }) => {
    await latency(500);
    const { ids } = (await request.json()) as { ids: string[] };
    let approved = 0;
    const failed: string[] = [];
    for (const id of ids ?? []) {
      const place = places.find((p) => p.id === id);
      if (place && place.status === "pending") {
        applyPlaceInput(place, { status: "approved" });
        approved += 1;
      } else failed.push(id);
    }
    return HttpResponse.json({ approved, failed });
  }),

  http.post(u("/admin/places/import"), async ({ request }) => {
    await latency(900);
    const form = await request.formData();
    const file = form.get("file");
    if (!(file instanceof File)) return problem(422, "VALIDATION_ERROR", "파일을 확인해 주세요", "file 필드가 비어 있어요.");
    if (!/\.(csv|json)$/i.test(file.name)) return problem(422, "VALIDATION_ERROR", "CSV 또는 JSON 파일만 올릴 수 있어요");
    const slug = String(form.get("region") ?? adminRegions[0]?.slug ?? "");
    const job: IngestionJob = { id: uid("job"), region: slug, provider: "file", status: "queued", progress: 0, collected: 0, started_at: null, finished_at: null, error: null };
    jobs.unshift(job);
    return HttpResponse.json({ job_id: job.id, accepted: Math.max(1, Math.round(file.size / 120)) }, { status: 202 });
  }),

  http.post(u("/admin/places/:id/photos"), async ({ params, request }) => {
    await latency(700);
    const place = places.find((p) => p.id === params.id);
    if (!place) return problem(404, "NOT_FOUND", "장소를 찾을 수 없어요");
    const file = (await request.formData()).get("file");
    if (!(file instanceof File) || !/^image\/(jpeg|png|webp)$/.test(file.type)) return problem(422, "VALIDATION_ERROR", "입력을 확인해 주세요", "JPEG · PNG · WebP 사진만 올릴 수 있어요.");
    place.updated_at = now();
    return HttpResponse.json(place);
  }),

  http.post(u("/admin/places"), async ({ request }) => {
    await latency(450);
    const input = (await request.json()) as AdminPlaceInput;
    const cat = findCategory(input.category);
    if (!input.name || !cat) return problem(422, "VALIDATION_ERROR", "입력을 확인해 주세요", "이름과 카테고리는 필수예요.");
    const place: AdminPlace = {
      id: uid("ap"),
      name: input.name,
      status: input.status ?? "approved",
      category: cat.code,
      category_name: cat.name,
      course_role: cat.course_role,
      region: regionRef(input.region),
      address: input.address ?? "",
      lat: input.lat ?? 0,
      lng: input.lng ?? 0,
      price_per_person: input.price_per_person ?? null,
      is_free: input.is_free ?? false,
      rating: null,
      review_count: 0,
      tags: input.tags ?? [],
      source: "admin",
      created_at: now(),
      updated_at: now(),
      duplicate_of: null,
    };
    places.unshift(place);
    return HttpResponse.json(place, { status: 201 });
  }),

  http.get(u("/admin/places/:id/revisions"), async ({ params }) => {
    await latency(200);
    return HttpResponse.json({ items: revisions.get(String(params.id)) ?? [] });
  }),

  http.post(u("/admin/places/:id/approve"), async ({ params }) => {
    await latency(300);
    const place = places.find((p) => p.id === params.id);
    if (!place) return notFound("장소");
    applyPlaceInput(place, { status: "approved" });
    return HttpResponse.json(place);
  }),

  http.post(u("/admin/places/:id/reject"), async ({ params }) => {
    await latency(300);
    const place = places.find((p) => p.id === params.id);
    if (!place) return notFound("장소");
    applyPlaceInput(place, { status: "rejected" });
    return HttpResponse.json(place);
  }),

  http.post(u("/admin/places/:id/merge"), async ({ params, request }) => {
    await latency(400);
    const { into } = (await request.json()) as { into: string };
    const index = places.findIndex((p) => p.id === params.id);
    const target = places.find((p) => p.id === into);
    if (index === -1 || !target) return notFound("장소");
    places.splice(index, 1);
    return HttpResponse.json(target);
  }),

  http.patch(u("/admin/places/:id"), async ({ params, request }) => {
    await latency(350);
    const place = places.find((p) => p.id === params.id);
    if (!place) return notFound("장소");
    applyPlaceInput(place, (await request.json()) as AdminPlaceInput);
    return HttpResponse.json(place);
  }),

  // ── 이벤트 ────────────────────────────────────────────────
  http.get(u("/admin/events"), async ({ request }) => {
    await latency(220);
    return HttpResponse.json(paginate(events, new URL(request.url), 100));
  }),
  http.post(u("/admin/events"), async ({ request }) => {
    await latency(350);
    const input = (await request.json()) as AdminEventInput;
    if (!input.title) return problem(422, "VALIDATION_ERROR", "제목을 입력해 주세요");
    const event: AdminEvent = { ...input, id: uid("ev"), status: input.status ?? "draft", region_name: regionRef(input.region)?.name ?? null };
    events.unshift(event);
    return HttpResponse.json(event, { status: 201 });
  }),
  http.patch(u("/admin/events/:id"), async ({ params, request }) => {
    await latency(300);
    const event = events.find((e) => e.id === params.id);
    if (!event) return notFound("이벤트");
    Object.assign(event, (await request.json()) as Partial<AdminEventInput>);
    event.region_name = regionRef(event.region)?.name ?? null;
    return HttpResponse.json(event);
  }),
  http.delete(u("/admin/events/:id"), async ({ params }) => {
    await latency(250);
    const index = events.findIndex((e) => e.id === params.id);
    if (index === -1) return notFound("이벤트");
    events.splice(index, 1);
    return noContent();
  }),

  // ── 배너 ──────────────────────────────────────────────────
  http.get(u("/admin/banners"), async ({ request }) => {
    await latency(220);
    return HttpResponse.json(paginate(banners, new URL(request.url), 100));
  }),
  http.post(u("/admin/banners"), async ({ request }) => {
    await latency(350);
    const input = (await request.json()) as AdminBannerInput;
    if (!input.title || !input.link_url) return problem(422, "VALIDATION_ERROR", "제목과 링크는 필수예요");
    const banner: AdminBanner = { ...input, id: uid("b"), impressions: 0, clicks: 0 };
    banners.unshift(banner);
    return HttpResponse.json(banner, { status: 201 });
  }),
  http.patch(u("/admin/banners/:id"), async ({ params, request }) => {
    await latency(250);
    const banner = banners.find((b) => b.id === params.id);
    if (!banner) return notFound("배너");
    Object.assign(banner, (await request.json()) as Partial<AdminBannerInput>);
    return HttpResponse.json(banner);
  }),
  http.delete(u("/admin/banners/:id"), async ({ params }) => {
    await latency(250);
    const index = banners.findIndex((b) => b.id === params.id);
    if (index === -1) return notFound("배너");
    banners.splice(index, 1);
    return noContent();
  }),
  http.post(u("/admin/uploads/presign"), async ({ request }) => {
    const { filename } = (await request.json()) as { filename: string };
    const key = `${uid("up")}-${encodeURIComponent(filename ?? "file")}`;
    return HttpResponse.json({ upload_url: `https://mock-s3.invalid/${key}`, public_url: `https://cdn.mock.invalid/${key}` });
  }),

  // ── 지역 ──────────────────────────────────────────────────
  http.get(u("/admin/regions"), async () => {
    await latency(200);
    tickCollections();
    return HttpResponse.json({ items: adminRegions });
  }),
  http.post(u("/admin/regions"), async ({ request }) => {
    await latency(400);
    const input = (await request.json()) as AdminRegionInput;
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(input.slug ?? "")) {
      return problem(422, "VALIDATION_ERROR", "slug 를 확인해 주세요", "영문 소문자·숫자·하이픈만 쓸 수 있어요.");
    }
    if (adminRegions.some((r) => r.slug === input.slug)) {
      return problem(409, "REGION_ALREADY_EXISTS", "이미 있는 지역이에요", `'${input.slug}' 는 이미 등록돼 있어요.`);
    }
    const region: AdminRegion = {
      slug: input.slug,
      name: input.name,
      parent: input.parent ?? null,
      level: 3,
      center: input.center,
      radius_m: input.radius_m,
      keywords: input.keywords,
      status: "draft",
      place_count: 0,
      pending_count: 0,
      last_collected_at: null,
      last_job: null,
    };
    adminRegions.unshift(region);
    return HttpResponse.json(region, { status: 201 });
  }),
  http.patch(u("/admin/regions/:slug"), async ({ params, request }) => {
    await latency(300);
    const region = adminRegions.find((r) => r.slug === params.slug);
    if (!region) return notFound("지역");
    const { slug: _slug, ...patch } = (await request.json()) as Partial<AdminRegionInput>;
    Object.assign(region, patch);
    return HttpResponse.json(region);
  }),
  http.post(u("/admin/regions/:slug/collect"), async ({ params }) => {
    await latency(400);
    const region = adminRegions.find((r) => r.slug === params.slug);
    if (!region) return notFound("지역");
    if (region.status === "collecting") return problem(409, "JOB_ALREADY_RUNNING", "이미 수집 중이에요");
    return HttpResponse.json(startCollect(region), { status: 202 });
  }),
  http.post(u("/admin/regions/:slug/activate"), async ({ params }) => {
    await latency(350);
    const region = adminRegions.find((r) => r.slug === params.slug);
    if (!region) return notFound("지역");
    if (region.status !== "ready") {
      return problem(409, "REGION_NOT_READY", "아직 활성화할 수 없어요", "수집이 끝나 '준비됨' 상태가 되어야 해요.");
    }
    region.status = "active";
    // 공개 메타(/meta/regions)에도 바로 나타난다 — "새 지역 = 데이터만"
    if (!metaRegions.some((r) => r.slug === region.slug)) {
      metaRegions.push({ slug: region.slug, name: region.name, level: region.level, center: region.center, radius_m: region.radius_m, parent: null, place_count: region.place_count });
    }
    return HttpResponse.json(region);
  }),

  // ── 추천 설정 ─────────────────────────────────────────────
  http.get(u("/admin/scoring-profiles/:purpose"), async ({ params }) => {
    await latency(220);
    const profile = scoringProfiles.get(String(params.purpose));
    return profile ? HttpResponse.json(profile) : notFound("스코어링 프로필");
  }),
  http.put(u("/admin/scoring-profiles/:purpose"), async ({ params, request }) => {
    await latency(450);
    const profile = scoringProfiles.get(String(params.purpose));
    if (!profile) return notFound("스코어링 프로필");
    const body = (await request.json()) as { weights: ScoreBreakdown; params?: Record<string, unknown> };
    const sum = SCORE_FEATURES.reduce((acc, k) => acc + (Number(body.weights?.[k]) || 0), 0);
    if (Math.abs(sum - 1) > 0.005) {
      return problem(422, "VALIDATION_ERROR", "가중치 합이 1이 아니에요", `현재 합계는 ${sum.toFixed(3)} 이에요.`, { sum });
    }
    const next = { ...profile, weights: body.weights, params: body.params ?? profile.params, version: profile.version + 1, updated_at: now(), updated_by: "mock-admin" };
    scoringProfiles.set(profile.purpose, next);
    return HttpResponse.json(next);
  }),
  http.get(u("/admin/templates"), async ({ request }) => {
    await latency(220);
    const purpose = new URL(request.url).searchParams.get("purpose");
    return HttpResponse.json({ items: purpose ? templates.filter((t) => t.purpose === purpose) : templates });
  }),
  http.post(u("/admin/templates"), async ({ request }) => {
    await latency(350);
    const input = (await request.json()) as Omit<CourseTemplate, "id">;
    const template: CourseTemplate = { ...input, id: uid("tpl") };
    templates.push(template);
    return HttpResponse.json(template, { status: 201 });
  }),
  http.patch(u("/admin/templates/:id"), async ({ params, request }) => {
    await latency(400);
    const template = templates.find((t) => t.id === params.id);
    if (!template) return notFound("템플릿");
    const patch = (await request.json()) as Partial<CourseTemplate>;
    if (patch.slots) {
      const sum = patch.slots.reduce((acc, s) => acc + s.budget_share, 0);
      if (Math.abs(sum - 1) > 0.005) return problem(422, "VALIDATION_ERROR", "슬롯 예산 비중의 합이 1이 아니에요", `현재 합계는 ${sum.toFixed(3)} 이에요.`);
    }
    Object.assign(template, patch, { id: template.id });
    return HttpResponse.json(template);
  }),
  http.get(u("/admin/purposes/:code/tag-affinities"), async ({ params }) => {
    await latency(200);
    const code = String(params.code);
    const items = tagAffinities.get(code) ?? tags.filter((t) => t.group !== "avoid").map((t, i) => ({ tag: t.name, affinity: Number((((i * 37 + code.length * 11) % 20) / 10 - 1).toFixed(1)) }));
    return HttpResponse.json({ items });
  }),
  http.put(u("/admin/purposes/:code/tag-affinities"), async ({ params, request }) => {
    await latency(300);
    const { items } = (await request.json()) as { items: { tag: string; affinity: number }[] };
    tagAffinities.set(String(params.code), items);
    return HttpResponse.json({ items });
  }),

  // ── 수집 ──────────────────────────────────────────────────
  http.get(u("/admin/ingestion/jobs"), async ({ request }) => {
    await latency(200);
    tickCollections();
    return HttpResponse.json(paginate(jobs, new URL(request.url), 20));
  }),
  http.post(u("/admin/ingestion/jobs"), async ({ request }) => {
    await latency(350);
    const body = (await request.json()) as { region: string; provider: string };
    const region = adminRegions.find((r) => r.slug === body.region);
    if (!region) return notFound("지역");
    return HttpResponse.json(startCollect(region, body.provider), { status: 202 });
  }),
  http.post(u("/admin/ingestion/jobs/:id/retry"), async ({ params }) => {
    await latency(350);
    const job = jobs.find((j) => j.id === params.id);
    const region = adminRegions.find((r) => r.slug === job?.region);
    if (!job || !region) return notFound("수집 잡");
    return HttpResponse.json(startCollect(region, job.provider), { status: 202 });
  }),

  // ── 분석 · 시스템 ─────────────────────────────────────────
  http.get(u("/admin/analytics/users"), async () => {
    await latency(400);
    return HttpResponse.json(userAnalytics());
  }),
  http.get(u("/admin/analytics/recommendations"), async () => {
    await latency(400);
    return HttpResponse.json(recommendationAnalytics());
  }),
  http.get(u("/admin/analytics/places/top"), async () => {
    await latency(300);
    return HttpResponse.json({ items: topPlaces() });
  }),
  http.get(u("/admin/system/health"), async () => {
    await latency(150);
    return HttpResponse.json(systemHealth());
  }),
  http.post(u("/admin/cache/invalidate"), async () => {
    await latency(300);
    return noContent();
  }),
  http.post(u("/admin/search/reindex"), async () => {
    await latency(600);
    return noContent();
  }),
];
