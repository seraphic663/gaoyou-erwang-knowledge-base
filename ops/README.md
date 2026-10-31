# 构建与部署契约

> 当前入口复核于 2026-10-31。

`ops/` 保存容器构建上下文所需的 Dockerfile 与 Node 运行依赖；网站源码仍位于 `solution/website/`。

- 根 `railway.toml` 指向 `ops/Dockerfile`；从仓库根目录构建。
- `package.json` 与 lockfile 提供 Node 运行时依赖。
- 本地网站：`npm --prefix solution/website start`。
- 四书机器库任务：`npm --prefix solution/website run machine:build`、`machine:pack`。
- 人工标注快照任务：`npm --prefix solution/website run sync:annotation`。

旧 `sync:sqlite` 任务已移除。运行时机器库由版本化 bundle 提供；更新 parser 或原典内容后显式构建和核对 manifest，不因普通页面修改重解析四书。

`node_modules/` 是本地生成依赖，不是权威来源，也不应提交。
