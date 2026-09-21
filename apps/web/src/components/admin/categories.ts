import type { Category } from "@/lib/api/types";

/** 카테고리 트리를 select 옵션용으로 편다. role 을 같이 넘기면 그 역할(과 하위)만 남긴다. */
export function flattenCategories(items: Category[], depth = 0): { code: string; label: string; role: Category["course_role"] }[] {
  return items.flatMap((c) => [
    { code: c.code, label: `${"· ".repeat(depth)}${c.name}`, role: c.course_role },
    ...flattenCategories(c.children ?? [], depth + 1),
  ]);
}
