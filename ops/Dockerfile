FROM node:18-alpine

WORKDIR /app

RUN apk add --no-cache python3

COPY ops/package.json ./package.json
COPY ops/package-lock.json ./package-lock.json
RUN npm ci --omit=dev
COPY solution/website ./solution/website
COPY v2 ./v2

ENV NODE_ENV=production
ENV PORT=3000
ENV DATA_SOURCE=sqlite
ENV DATA_DIR=/app/solution/website/data
ENV PYTHON_BIN=python3
ENV V2_DB_MODE=production

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["node", "solution/website/server.js"]
