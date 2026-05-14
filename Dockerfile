FROM node:18-alpine

WORKDIR /app

COPY package.json ./
COPY 03-项目网站 ./03-项目网站

ENV NODE_ENV=production
ENV PORT=3000
ENV DATA_SOURCE=sqlite

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["npm", "start"]
