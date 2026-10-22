# 高邮二王考据过程知识库网站

网站负责材料查阅与释证审校。页面合并不合并数据库、不改原始记录 ID，也不把机器草稿或五步审校记录自动升级为已审定材料。

## 运行

需要 Node.js 18+、Python 3。首次在本目录安装依赖后，从仓库根目录执行 `node solution/website/server.js`，默认访问 `http://localhost:3000/`。可用 `PORT`、`PYTHON_BIN`、`V2_PYTHON_BIN` 指定端口与解释器。

本地默认使用 `v2/data/local_test/annotation_v2.local.db`；生产使用 Railway 持久卷下的 `real_runs/annotation_v2.db`。`V2_DB_FILE` 和 `CORPUS_DB_FILE` 可显式指定数据库。测试必须使用独立副本，不能在原始数据库上试写。

## 页面与代码职责

| 位置 | 唯一职责 |
| --- | --- |
| `web/assets/js/page-catalog.js` | 新站页面路径、标签和导航顺序；服务端与浏览器共用 |
| `src/site-routes.js` | 精确匹配新路由，并生成共享导航 |
| `web/*.html` | 各页面结构，以 `<!--site-navigation-->` 引入公共导航 |
| `web/assets/js/case-sources.js` | 将主库、人工标注、V2 的不同 API 字段适配为统一展示模型 |
| `web/assets/js/cases.js` | 案例列表、来源筛选和分页 |
| `web/assets/js/case-reader.js` | 展示规范化后的案例内容，独立呈现问题、主张、结论与证据 |
| `web/assets/js/term-detail.js` | 字词详情，不含案例页面分支 |
| `web/assets/js/site.js` | 安全返回地址、内容链接及共用分页/选项渲染 |
| `web/assets/js/five-step-audit.js` | 当前案例的 AI 起草、逐步审核和版本操作 |
| `web/assets/js/audit-draft.js` | 当前标签页按案例 ID 隔离的未提交草稿 |
| `scripts/site_identity_bridge.py` | 只读查询明确的主库到 V2 映射，不按标题猜测 |

只有新路由对外提供页面：`/`、`/audit`、`/cases`、`/case`、`/terms`、`/term`、`/corpus`、`/knowledge`、`/quality`。不支持旧 `.html`、`/web/` 地址，不提供旧站重定向。旧的一次性 AI 接口和相关前后端实现已删除。静态资源仅通过 `/assets/` 和 `/media/` 提供。

## 数据边界

- 主库读取 `data/sqlite-snapshot.json`；人工标注读取 `data/annotation-snapshot.json`。两者是源数据库导出物，不手工修改。
- V2 案例、证据、原文和审校历史保留原数据库及 ID。`main`、`annotation`、`v2` 是独立身份空间。
- 主库到 V2 的审校入口只使用 `legacy_term_case_links`。有多个对应记录时分别展示；人工标注材料没有明确映射时仅供阅读。
- 历史数据中的 `legacy_*` 表和来源标记是追溯契约，不是旧网站的兼容实现。
- 更新来源数据库后，使用 `npm --prefix solution/website run sync:sqlite` 或 `sync:annotation` 重新导出；页面更新不执行这些命令。

## API 与写入边界

主库读取使用 `/api/health`、`/api/bootstrap`、`/api/browser`、`/api/browser/bootstrap`、`/api/schema`、`/api/search`、`/api/term`、`/api/case` 等接口；人工标注使用 `/api/annotation`、`/api/annotation/bootstrap` 和 `/api/annotation/detail`；来源映射使用 `/api/site/audit-targets`。

原典检索为 `/api/corpus/retrieve`，V2 案例和质量为 `/api/v2/cases`、`/api/v2/case`、`/api/v2/summary`。列表与详情页面共享来源适配器，新增字段应先在适配器中明确映射，不能在页面中堆叠跨来源字段兜底。

五步草稿通过 `POST /api/v2/five-step-draft` 生成；历史与保存、修订、软删除、恢复使用 `/api/v2/five-step-audits`。生成模型与推理配置沿用既有配置；保存依赖案例身份、来源指纹与幂等操作 ID。历史 GET 严格只读，不隐式升级表结构。

`V2_FIVE_STEP_AUDIT_WRITE_ENABLED=1` 才允许保存五步审校。五步记录写入独立的 `five_step_audit_records` 表，不修改案例正式状态。迁移维护用的 `/api/v2/review-tasks`、`/api/v2/review-task`、`/api/v2/review` 属于独立数据治理流程，继续受 `V2_REVIEW_WRITE_ENABLED` 控制，不作为网站旧页面保留。

未提交草稿按浏览器标签页与 `case_id` 保存在 sessionStorage；恢复必须由用户选择，保存授权默认关闭。输入、决定和离页时暂存；退出修改明确丢弃草稿，成功提交后清理暂存。服务器仍检查来源指纹。

## 验证与发布

- `node --test solution/website/tests/*.test.js`
- `python -m unittest discover -s v2/tests -p test_five_step_audit_bridge.py`
- `python -m unittest discover -s solution/website/tests -p test_site_identity.py`
- `tests/review-http-integration.js` 仅允许显式指定隔离的 fixture-copy 数据库。

测试覆盖直接访问、旧路由退出、统一导航、三种案例来源字段契约、实际证据正文、主张与结论分离、草稿隔离及审校生命周期。数据库完整性与备份工具为 `scripts/verify_site_data.py`；发布前后按线上基线逐表核对，不用本地库覆盖线上库。部署使用根目录 `railway.toml` 和 `ops/Dockerfile`。

本次切换前的线上备份位于 Railway 持久卷 `/app/v2/data/site-navigation-backups/20261022`，包含 V2 数据库、两份网页 JSON 快照及逐表基线。代码回退与数据恢复应分开操作，只有确认数据损坏后才停写并恢复数据库。
