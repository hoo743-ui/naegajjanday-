import { http, HttpResponse } from "msw";
import type { GenerateCourseRequest } from "@/lib/api/types";
import { generate, MockProblem } from "../fixtures/course-engine";
import { purposes, regions } from "../fixtures/meta";
import { latency, problem, sse, tokenFrames, u } from "./utils";

/** "3만원" "3.5만" "30000원" "30,000원" → 원 */
function parseBudget(text: string): number | null {
  const man = text.match(/(\d+(?:\.\d+)?)\s*만\s*(\d)?\s*(?:천)?/);
  if (man) {
    const base = Math.round(Number(man[1]) * 10_000);
    return base + (man[2] && /천/.test(man[0]) ? Number(man[2]) * 1_000 : 0);
  }
  const won = text.match(/(\d{1,3}(?:,\d{3})+|\d{4,7})\s*원?/);
  if (won?.[1]) return Number(won[1].replace(/,/g, ""));
  return null;
}

function parseParty(text: string): number | null {
  if (/혼자|혼밥|1인|한 ?명/.test(text)) return 1;
  if (/둘이|두 ?명|커플|데이트/.test(text)) return 2;
  if (/셋이|세 ?명/.test(text)) return 3;
  if (/넷이|네 ?명/.test(text)) return 4;
  const n = text.match(/(\d{1,2})\s*(?:명|인)/);
  return n?.[1] ? Math.max(1, Math.min(10, Number(n[1]))) : null;
}

function parsePurpose(text: string): string | null {
  const keywords: Record<string, RegExp> = {
    date: /데이트|커플|연인|애인|여자친구|남자친구/,
    travel: /여행|관광|나들이/,
    family: /가족|부모님|아이/,
    friends: /친구|모임|회식|동기/,
    solo: /혼밥|혼자/,
  };
  for (const p of purposes) if (keywords[p.code]?.test(text) || text.includes(p.name)) return p.code;
  return null;
}

function parseRegion(text: string) {
  const compact = text.replace(/\s/g, "");
  return (
    regions.find((r) => compact.includes(r.name.replace(/\s/g, ""))) ??
    regions.find((r) => r.name.split(/[·\s]/).some((part) => part.length >= 2 && compact.includes(part.replace(/(입구|역)$/, ""))))
  );
}

export const chatHandlers = [
  http.post(u("/chat/sessions"), async () => {
    await latency(200);
    return HttpResponse.json({ id: `s_${Date.now().toString(36)}`, created_at: new Date().toISOString() }, { status: 201 });
  }),

  http.post(u("/chat/sessions/:id/messages"), async ({ request }) => {
    const body = (await request.json().catch(() => null)) as { content?: string } | null;
    const content = body?.content?.trim() ?? "";
    if (!content) return problem(422, "VALIDATION_ERROR", "메시지를 적어 주세요");
    await latency(350);

    const region = parseRegion(content);
    const budget = parseBudget(content);
    const party = parseParty(content);
    const purpose = parsePurpose(content);

    if (!region || !budget) {
      const missing = [!region ? "어느 동네에서" : null, !budget ? "예산은 얼마로" : null, !party ? "몇 명이서" : null].filter(Boolean).join(", ");
      const text = `좋아요! 코스를 짜려면 조금만 더 알려 주세요. ${missing} 놀 건지 말해 주면 바로 짜 드릴게요. 예를 들면 "${regions[0]?.name ?? "우리 동네"}에서 둘이 4만원"처럼요.`;
      return sse([...tokenFrames(text), { event: "done", data: {} }]);
    }

    const args: GenerateCourseRequest = {
      region: region.slug,
      purpose: purpose ?? (party === 1 ? "solo" : "date"),
      party_size: party ?? 2,
      budget_total: budget,
      transport: "walk",
      alternatives: 0,
    };

    const frames: { event: string; data: unknown }[] = [
      ...tokenFrames(`${region.name}에서 ${args.party_size}명, ${budget.toLocaleString("ko-KR")}원이군요. 예산 안에서 찾아볼게요. `),
      { event: "tool_call", data: { name: "generate_course", arguments: args } },
    ];

    try {
      const course = generate(args).courses[0];
      if (!course) throw new MockProblem(422, "SLOT_EMPTY", "코스를 만들지 못했어요");
      const left = course.totals.budget_left;
      frames.push(
        { event: "course", data: course },
        ...tokenFrames(
          `짠! ${course.summary} ` +
            (left > 0 ? `${left.toLocaleString("ko-KR")}원이 남아요. ` : "예산을 남김없이 알차게 썼어요. ") +
            "마음에 안 드는 곳이 있으면 말해 주세요. 그 한 곳만 바꿔 드릴게요.",
        ),
        { event: "done", data: {} },
      );
    } catch (error) {
      if (!(error instanceof MockProblem)) throw error;
      frames.push({
        event: "error",
        data: { title: error.message, status: error.status, code: error.code, detail: error.detail, meta: error.meta },
      });
    }
    // tool_call 뒤에 살짝 뜸을 들여 "짜는 중" 상태가 보이게 한다
    return sse(frames, 60);
  }),
];
