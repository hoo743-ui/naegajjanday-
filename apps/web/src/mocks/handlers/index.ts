import { adminHandlers } from "./admin";
import { chatHandlers } from "./chat";
import { courseHandlers } from "./courses";
import { exploreHandlers } from "./explore";
import { metaHandlers } from "./meta";
import { userHandlers } from "./user";

/** docs/03-api-spec.md 의 섹션 순서와 같다 */
export const handlers = [
  ...metaHandlers,
  ...courseHandlers,
  ...exploreHandlers,
  ...userHandlers,
  ...chatHandlers,
  ...adminHandlers,
];
