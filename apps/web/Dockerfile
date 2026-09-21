# syntax=docker/dockerfile:1.7
# 내가짠데이 web — Next.js standalone 이미지 (non-root)
#   docker build -t njd-web --build-arg NEXT_PUBLIC_API_URL=https://api.naegajjanday.com/v1 apps/web
#   docker run -p 3000:3000 njd-web
#
# NEXT_PUBLIC_* 는 빌드 시점에 번들에 박힌다. 환경별로 이미지를 따로 빌드한다.
# NEXT_PUBLIC_API_MOCKING 은 여기서 받지 않는다 → 운영 이미지에는 목이 들어갈 수 없다.

FROM node:22-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

# ── 1. 의존성 ──────────────────────────────────────────────
FROM base AS deps
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

# ── 2. 빌드 ────────────────────────────────────────────────
FROM base AS builder
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/v1
ARG NEXT_PUBLIC_SITE_URL=http://localhost:3000
ARG NEXT_PUBLIC_KAKAO_MAP_KEY=
ARG NEXT_PUBLIC_GA4_ID=
ARG NEXT_PUBLIC_POSTHOG_KEY=
ARG NEXT_PUBLIC_POSTHOG_HOST=
ARG NEXT_PUBLIC_MIXPANEL_TOKEN=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_KAKAO_MAP_KEY=$NEXT_PUBLIC_KAKAO_MAP_KEY \
    NEXT_PUBLIC_GA4_ID=$NEXT_PUBLIC_GA4_ID \
    NEXT_PUBLIC_POSTHOG_KEY=$NEXT_PUBLIC_POSTHOG_KEY \
    NEXT_PUBLIC_POSTHOG_HOST=$NEXT_PUBLIC_POSTHOG_HOST \
    NEXT_PUBLIC_MIXPANEL_TOKEN=$NEXT_PUBLIC_MIXPANEL_TOKEN
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# MSW 서비스 워커는 개발 전용. 운영 이미지에서는 뺀다.
RUN rm -f public/mockServiceWorker.js && npm run build

# ── 3. 실행 ────────────────────────────────────────────────
FROM base AS runner
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -S -g 1001 nodejs && adduser -S -u 1001 -G nodejs nextjs
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/login" >/dev/null || exit 1
CMD ["node", "server.js"]
