import { http, HttpResponse } from "msw";
import type { GenerateCourseRequest, ReorderRequest, SwapRequest } from "@/lib/api/types";
import { generate, getDetail, markSaved, removeStop, reorder, swap } from "../fixtures/course-engine";
import { guard, latency, problem, sse, tokenFrames, u } from "./utils";

export const courseHandlers = [
  http.post(u("/courses/generate"), async ({ request }) => {
    const body = (await request.json()) as GenerateCourseRequest;
    await latency(2600); // 로더의 단계 문구가 보이도록 일부러 길게
    if (!body.purpose || !body.party_size || !body.budget_total) {
      return problem(422, "VALIDATION_ERROR", "입력을 확인해 주세요", "purpose, party_size, budget_total 은 필수예요.");
    }
    return guard(() => generate(body));
  }),

  http.get(u("/courses/:id/narrative"), ({ params }) => {
    try {
      const course = getDetail(String(params.id));
      const left = course.totals.budget_left;
      const names = course.stops.map((s) => s.place.name);
      const text =
        `짠! ${course.summary.replace(/요$/, "요.")} ` +
        `${names[0] ?? "첫 장소"}에서 시작해서 ${names.slice(1).join(", ")} 순서로 이어져요. ` +
        (left > 0
          ? `${left.toLocaleString("ko-KR")}원이 남으니까 디저트 하나 더 어때요?`
          : "예산을 남김없이 알차게 쓰는 코스예요.");
      return sse([...tokenFrames(text), { event: "done", data: {} }]);
    } catch {
      return problem(404, "COURSE_NOT_FOUND", "코스를 찾을 수 없어요");
    }
  }),

  http.get(u("/courses/:id"), async ({ params }) => {
    await latency(300);
    return guard(() => getDetail(String(params.id)));
  }),

  http.post(u("/courses/:id/swap"), async ({ params, request }) => {
    const body = (await request.json()) as SwapRequest;
    await latency(700);
    return guard(() => swap(String(params.id), body.position, body.strategy ?? "random_top"));
  }),

  http.post(u("/courses/:id/reorder"), async ({ params, request }) => {
    const body = (await request.json()) as ReorderRequest;
    await latency(400);
    return guard(() => reorder(String(params.id), body.order));
  }),

  http.delete(u("/courses/:id/stops/:position"), async ({ params }) => {
    await latency(400);
    return guard(() => removeStop(String(params.id), Number(params.position)));
  }),

  http.post(u("/courses/:id/save"), async ({ params }) => {
    await latency(350);
    return guard(() => {
      markSaved(String(params.id), true);
      return { id: String(params.id) };
    });
  }),

  http.post(u("/courses/:id/feedback"), async () => {
    await latency(300);
    return new HttpResponse(null, { status: 204 });
  }),
];
