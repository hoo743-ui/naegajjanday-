// 점검 도구가 API 로 직접 만든 코스를 "만든 사람"으로 연다 (docs/28 편집 키).
// 계정 없이 만든 코스는 이제 그 코스를 만든 브라우저만 고칠 수 있다 — 도구는 Node 에서 만들고 크롬에서 열므로,
// 생성 응답의 edit_key 를 크롬의 저장소(njd_course_keys)에 넣어 주어야 바꾸기 · 저장 · 조건 바꾸기가 보인다.
//   import { asCreator, remember } from "./creator.mjs";
//   const body = await remember(await (await fetch(`${API}/courses/generate`, …)).json());
//   const context = await asCreator(await browser.newContext(…));
const keys = {};
const contexts = new Set();

function put(entries) {
  try {
    const current = JSON.parse(localStorage.getItem("njd_course_keys") ?? "{}");
    localStorage.setItem("njd_course_keys", JSON.stringify({ ...current, ...entries }));
  } catch {
    // 저장소를 못 쓰는 페이지(about:blank 등)
  }
}

/** 이 컨텍스트는 도구가 만든 코스들의 주인이다: 지금까지의 키와 앞으로 생길 키를 모두 받는다 */
export async function asCreator(context) {
  contexts.add(context);
  if (Object.keys(keys).length) await context.addInitScript(put, { ...keys });
  return context;
}

/** 생성 응답을 그대로 돌려주면서 키를 기억하고, 등록된 컨텍스트에 나눠 준다 */
export async function remember(body) {
  if (!body || !body.edit_key) return body;
  const added = {};
  for (const course of body.courses ?? []) {
    keys[course.id] = body.edit_key;
    added[course.id] = body.edit_key;
  }
  for (const context of contexts) await context.addInitScript(put, added).catch(() => undefined);
  return body;
}
