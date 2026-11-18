# AEIP ingestion service (GitHub webhooks -> PostgreSQL via Prisma). Build from the repository root:
#   docker build -f ingestion/Dockerfile -t aeip-ingestion .
FROM node:22-slim
WORKDIR /app
RUN apt-get update -y && apt-get install -y --no-install-recommends openssl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY prisma ./prisma
RUN npx prisma generate
COPY ingestion ./ingestion
ENV NODE_ENV=production PORT=4000
USER node
EXPOSE 4000
# Apply pending migrations, then start the listener.
CMD ["sh", "-c", "npx prisma migrate deploy && npx tsx ingestion/webhook-listener.ts"]
