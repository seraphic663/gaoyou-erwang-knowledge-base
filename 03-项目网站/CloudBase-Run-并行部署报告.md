# CloudBase Run 并行部署说明

更新时间：2026-08-30

> 当前边界：本文保留 2026-05 的 CloudBase 备用部署方案，并同步到现行 Dockerfile。Railway 已验证 `/api/health` 和 `/api/v2/summary`；CloudBase 当前没有可复核的 V2 持久卷与 V2 API 验收记录，因此不能把“支持用同一 Dockerfile 构建”写成“CloudBase V2 已部署可用”。

## 1. 当前目标

本轮目标是让项目在保留 Railway 的同时，维护一条腾讯云中文站 `CloudBase Run` 备用部署路径。两条线上路径都使用根目录 `Dockerfile` 构建容器，避免不同平台维护两套构建逻辑。

约束如下：

- GitHub 仓库保持公开
- Railway 继续作为主展示地址
- CloudBase Run 作为备用展示地址，先使用默认域名
- 优先省事和稳定
- 接受冷启动
- 不改网站页面内容、接口逻辑和数据库结构

## 2. 已完成的仓库配置

当前保留两个根目录部署文件：

- `Dockerfile`
- `.dockerignore`

Railway 配置已经明确为 Dockerfile 构建：

- `railway.toml` 中 `builder = "DOCKERFILE"`
- 根目录 `package.json` 的 `npm start` 仍是统一启动入口

这意味着当前仓库同时支持两条部署入口：

- Railway：读取 `railway.toml`，用根目录 `Dockerfile` 构建容器，执行 `npm start`
- CloudBase Run：读取根目录 `Dockerfile`，构建容器后执行 `npm start`

## 3. Dockerfile 配置说明

CloudBase Run 的源码部署要求代码中包含 `Dockerfile`。本项目根目录已补入：

```dockerfile
FROM node:18-alpine

WORKDIR /app

RUN apk add --no-cache python3

COPY package.json ./
COPY 03-项目网站 ./03-项目网站
COPY v2 ./v2

ENV NODE_ENV=production
ENV PORT=3000
ENV DATA_SOURCE=sqlite
ENV DATA_DIR=/app/03-项目网站/data
ENV PYTHON_BIN=python3

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["npm", "start"]
```

关键点：

- 使用 `node:18-alpine` 并安装 Python 3，满足 Node 服务和 V2 bridge 的运行要求
- 复制根目录 `package.json`、`03-项目网站` 和 V2 运行代码；`.dockerignore` 排除 `v2/data/`，不会把本地数据库、JSONL 和任务包打入镜像
- 根目录没有 `server.js`，服务入口由根 `package.json` 调用 `03-项目网站/server.js`
- 显式设置 `DATA_SOURCE=sqlite`，强制读取 `sqlite-snapshot.json`
- 显式设置 `PYTHON_BIN=python3`，供 V2 查询 bridge 调用
- 暴露 `3000` 端口，对应本项目默认端口
- 用 `/api/health` 做容器健康检查

## 4. 为什么不复制 `02-数据库` 和 `v2/data`

CloudBase Run 线上不需要直接读取 `02-数据库/data/dictionary.db`。

当前线上运行链路是：

```text
02-数据库/data/dictionary.db
  -> npm run sync:sqlite
  -> 03-项目网站/data/sqlite-snapshot.json
  -> Node 服务读取快照
```

因此旧展示链只需要包含：

- `03-项目网站/data/sqlite-snapshot.json`
- 页面文件
- Node 服务文件

这能减少镜像体积，也避免把数据库加工区和文献区带进运行环境。

V2 与旧快照不同：V2 页面运行时需要 `annotation_v2.db` 和审校任务 manifest，但这些文件体量大、包含运行状态，不应固化进镜像。部署平台应把受控持久卷挂载到 `/app/v2/data`，或者显式设置 `V2_DB_FILE` 和 `V2_REVIEW_MANIFEST_FILE` 指向持久化位置。没有完成这一步时，CloudBase 只能验收旧快照页面，不能验收 `/api/v2/*`。

## 5. CloudBase Run 控制台具体配置

在腾讯云中国站进入 `CloudBase` 控制台，选择 `CloudBase Run / 云托管` 创建服务。

建议配置如下：

| 配置项 | 建议值 |
| --- | --- |
| 部署方式 | 公开 Git 仓库地址部署 |
| Git 仓库地址 | 你的公开 GitHub 仓库 HTTPS 地址 |
| 分支 | `main` |
| 构建方式 | 源码部署，使用 Dockerfile |
| Dockerfile 目录 | 根目录，留空或填 `.` |
| Dockerfile 文件名 | `Dockerfile` |
| 服务类型 / 访问类型 | `WEB` / 公网访问 |
| 服务端口 | `3000` |
| CPU | `0.25` 或 `0.5` 核 |
| 内存 | 按平台规格选择，优先 `0.5GB` 或 `1GB` |
| 最小实例数 | `0` |
| 最大实例数 | `1` |
| 健康检查路径 | `/api/health` |
| 环境变量 | 基础展示：`DATA_SOURCE=sqlite`、`PYTHON_BIN=python3`；启用 V2 时另配置持久卷及必要路径 |

说明：

- 公开仓库可以直接填写地址部署，不需要授权账号。
- 如果后续需要 push 后自动部署，再考虑绑定 GitHub 授权仓库。
- 最小实例数设为 `0` 可以降低成本，但首次访问会有冷启动。
- 答辩或演示前，如果担心首开慢，可以临时把最小实例数改为 `1`。

## 6. 部署前必须确认

每次推送 CloudBase 前，先在本地确认快照是最新的：

```powershell
npm run sync:sqlite
```

然后确认本地服务正常：

```powershell
npm start
```

访问：

```text
http://127.0.0.1:3000/api/health
```

返回中应能看到：

- `ok: true`
- `source: sqlite`
- `sourceLabel: SQLite 实库快照`

如果本次部署宣称支持 V2，还必须先确认平台已挂载 V2 数据，并验证：

```text
http://127.0.0.1:3000/api/v2/summary
```

返回数量必须与计划部署的 V2 数据版本一致；不能用 `/api/health` 成功替代 V2 数据验收。

## 7. 部署后验证清单

CloudBase 部署完成后，先用平台默认域名验证：

```text
https://你的-cloudbase-默认域名/api/health
https://你的-cloudbase-默认域名/api/bootstrap
https://你的-cloudbase-默认域名/
https://你的-cloudbase-默认域名/database.html
https://你的-cloudbase-默认域名/api/search?q=造
https://你的-cloudbase-默认域名/api/v2/summary
```

其中 `/api/health` 是最重要的第一项。

成功标准：

- `/api/health` 返回 `ok: true`
- `source` 为 `sqlite`
- 首页能打开
- 数据库页能打开
- 搜索接口有结果
- 只有配置了 V2 持久卷时，`/api/v2/summary` 才应返回预期数据库统计；否则应把该部署标记为“旧快照展示可用、V2 未启用”

## 8. 公开仓库部署的注意点

CloudBase Run 支持公开 Git 仓库地址部署，这适合当前项目。

但公开仓库部署和授权私有仓库部署有差异：

- 公开仓库适合快速部署和展示
- 授权仓库更适合自动部署和团队协作
- 如果后续想做到 GitHub push 后自动发版，建议再改成授权仓库部署

当前阶段不需要先处理自动部署。

## 9. 费用配置建议

为了贴合“省事、稳定、接受冷启动”的目标，第一版建议：

- 最小实例数：`0`
- 最大实例数：`1`
- 规格：先从最低可用规格开始

如果访问速度不稳定，再调整：

- CPU 从 `0.25` 升到 `0.5`
- 内存从 `0.5GB` 升到 `1GB`
- 演示当天把最小实例数从 `0` 临时改到 `1`

不要一开始就开高规格或多实例。这个站点目前是轻量 Node 服务，不需要复杂资源。

## 10. 当前验证情况

已确认：

- `03-项目网站/data/sqlite-snapshot.json` 存在
- 根目录 `package.json` 的启动命令仍为 `node 03-项目网站/server.js`
- 项目代码已支持读取 `PORT`
- 项目已有 `/api/health`
- 当前 Dockerfile 已安装 Python 3 并复制 `v2/` 运行代码
- `.dockerignore` 已排除 `v2/data/`，避免约 826 MB 的非 PDF V2 数据进入普通 Docker 构建上下文
- Railway 的 `/api/health` 和 `/api/v2/summary` 当前可用

尚未确认：

- CloudBase 当前服务是否仍在线、使用哪个版本和默认域名；
- CloudBase 是否配置 `/app/v2/data` 持久卷或等价的 `V2_DB_FILE` 路径；
- CloudBase 的 `/api/v2/summary` 是否返回与当前工作库一致的统计。

因此本文件是“可执行部署说明 + 已知验证边界”，不是 CloudBase 当前在线状态证明。

CloudBase Run 使用 Dockerfile 构建时，若出现部署失败，优先检查：

- Dockerfile 是否在仓库根目录
- CloudBase 构建目录是否为根目录
- 服务端口是否填 `3000`
- Dockerfile 不应复制根目录 `server.js`
- `03-项目网站/data/sqlite-snapshot.json` 是否已提交到 GitHub
- 健康检查路径是否为 `/api/health`
- 若启用 V2，Python 3 是否可执行、V2 volume 是否挂载、`V2_DB_FILE`/manifest 是否指向实际文件

## 11. 参考官方资料

- CloudBase Run 部署方式  
  https://docs.cloudbase.net/run/deploy/deploy/introduce

- CloudBase Run 通过 Git 仓库部署  
  https://docs.cloudbase.net/run/deploy/deploy/deploying-git

- CloudBase Run 从源代码部署  
  https://docs.cloudbase.net/run/deploy/deploy/deploying-source-code

- CloudBase Run 服务开发说明  
  https://docs.cloudbase.net/run/develop/developing-guide

- CloudBase Run 版本配置说明  
  https://docs.cloudbase.net/run/deploy/version-setting

- CloudBase Run 概述  
  https://docs.cloudbase.net/run/introduction
