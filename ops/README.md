# 构建与部署契约

> 当前维护入口复核于 2026-09-30。

本目录集中保存 Node 运行时依赖清单和生产容器构建文件。它们不是研究资料，也不是网站源代码。

- `Dockerfile`：从仓库根目录作为 Docker build context 构建；路径由根 `railway.toml` 的 `build.dockerfilePath` 指向。
- `package.json`、`package-lock.json`：为容器安装 `opencc-js` 等运行时依赖；本地网站开发入口在 `solution/website/`。
- `node_modules/`：本地生成依赖，不是权威来源，已由根 `.gitignore` 忽略。

本地运行网站使用 `node solution/website/server.js` 或 `npm --prefix solution/website start`。数据库快照同步使用 `npm --prefix solution/website run sync:sqlite` 和 `npm --prefix solution/website run sync:annotation`。
