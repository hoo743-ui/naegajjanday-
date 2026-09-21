import { setupServer } from "msw/node";
import { handlers } from "./handlers";

/** 서버 컴포넌트(generateMetadata 등)의 fetch 도 목으로 받기 위한 node 서버. instrumentation.ts 에서만 켠다. */
export const server = setupServer(...handlers);
