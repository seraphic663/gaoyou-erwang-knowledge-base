FROM node:18-alpine

WORKDIR /app

RUN apk add --no-cache python3

COPY ops/package.json ./package.json
COPY ops/package-lock.json ./package-lock.json
RUN npm ci --omit=dev
COPY solution/website ./solution/website
RUN test -s /app/solution/website/data/sqlite-snapshot.json \
    && test -s /app/solution/website/data/annotation-snapshot.json \
    && test -s /app/solution/website/runtime-bundle/machine-library.sqlite3.xz \
    && test -s /app/solution/website/runtime-bundle/machine-library.manifest.json \
    && test -s /app/solution/website/runtime-bundle/harness_corpus.jsonl.xz
RUN python3 -B /app/solution/website/scripts/machine_bundle.py unpack \
    --bundle /app/solution/website/runtime-bundle/machine-library.sqlite3.xz \
    --manifest /app/solution/website/runtime-bundle/machine-library.manifest.json \
    --output /app/solution/website/runtime-bundle/machine-library.sqlite3
RUN python3 -B /app/solution/website/scripts/harness_bundle.py unpack \
    --bundle /app/solution/website/runtime-bundle/harness_corpus.jsonl.xz \
    --output /app/solution/website/runtime-release \
    && test -s /app/solution/website/runtime-release/harness_corpus.sqlite3
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
