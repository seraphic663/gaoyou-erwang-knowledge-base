FROM node:18-alpine

WORKDIR /app

RUN apk add --no-cache python3

COPY package.json ./
COPY 03-项目网站 ./03-项目网站
COPY v2 ./v2

ENV NODE_ENV=production
ENV PORT=3000
ENV DATA_SOURCE=sqlite
ENV PYTHON_BIN=python3

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["npm", "start"]
