# AEIP dashboard (Next.js standalone server). Build from frontend/:
#   docker build -t aeip-web frontend
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* values are compiled into the browser bundle, so they are build arguments.
ARG NEXT_PUBLIC_INGESTION_API_URL=http://localhost:4000
ENV NEXT_PUBLIC_INGESTION_API_URL=$NEXT_PUBLIC_INGESTION_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S aeip && adduser -S aeip -G aeip
COPY --from=build --chown=aeip:aeip /app/.next/standalone ./
COPY --from=build --chown=aeip:aeip /app/.next/static ./.next/static
COPY --from=build --chown=aeip:aeip /app/public ./public
USER aeip
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/login >/dev/null || exit 1
CMD ["node", "server.js"]
