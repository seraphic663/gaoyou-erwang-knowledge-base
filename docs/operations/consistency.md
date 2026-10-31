# 项目一致性检查清单

> 当前实现与文档联动规则复核于 2026-10-31。

## 1. 身份与状态

- 四书机器库：`solution/website/runtime-bundle/machine-library.sqlite3.xz` → `/api/machine/*` → `/library`、`/terms`、`/cases`。这是机器候选，不回退到 `dictionary.db`，也不写入人工或 V2 状态。
- 人工标注库：`data/D-标注/01-原始DOCX/` → `02-文档Markdown/` → `03-案例Markdown/` → `04-案例JSONL/` → `05-数据库/annotations.db` → `annotation-snapshot.json`。状态须保留草稿/待核。
- V2 工作库：`v2/data/real_runs/annotation_v2.db` 与其任务包、验证报告、review gate 独立维护；machine candidate 不等于 human approved 或 gold。
- 典籍检索和 reading-lab 运行数据用于召回与实验，不自动写入机器关系、人工库或 V2 gold。
- `solution/legacy-db/data/dictionary.db` 与网站 `sqlite-snapshot.json` 是旧兼容快照；`/api/health` 的旧库计数不能当作 `/api/machine/meta` 的机器库计数。

## 2. 文档同步

| 改动 | 必须同步检查 |
| --- | --- |
| machine parser、库结构、关系分类或页面路由 | `solution/website/MACHINE-LIBRARY.md`、网站 README、根 README、项目状态与数据库关系说明 |
| 标注导入、数据库或快照 | `data/D-标注/README.md`、`solution/legacy-db/README.md`、网站 README、`docs/project/06` |
| V2 schema、任务包或正式写入门禁 | `v2/README.md`、`docs/project/03`、`docs/project/05`、相应验证报告 |
| Corpus 页面、搜索参数或外典索引 | 网站 README、Corpus 页面、检索桥和当期部署记录 |
| Docker/Railway 构建输入 | 根 `railway.toml`、`ops/Dockerfile`、`.dockerignore`、`.railwayignore` 和当前发布 manifest |
| 当前定位、状态或数据库路径 | 根 `README.md`、`docs/project/00`、`05`、`06`、相关目录 README |

## 3. 发布前的最低核对

1. 核对变更范围、分支、上游和目标；不要把 local checkpoint、原始材料或 ignored ParseBench 目录一并推送。
2. machine parser 或库 schema 改动必须有来源快照、parser 版本、定向回归和有界消融记录；测试数字不能表述成全库准确率。
3. 仅当改变机器源文、parser 或关系输出时重建并打包机器库；页面改动不触发四书重解析。
4. 人工库快照由 `npm --prefix solution/website run sync:annotation` 从标注数据库导出；不手工编辑 JSON。
5. machine bundle 的 byte counts、SHA-256 和运行 ID 以 manifest 和 `/api/machine/meta` 为准；`/api/health` 属于旧 snapshot。
6. 改动展示状态时，核对 `/api/annotation/bootstrap` 的人工库计数和 V2 review/gold 状态，避免状态升格。
7. 变更后更新相应当前说明；历史报告保留其日期和口径，不倒改成当前状态。

当前网站包提供 `machine:build`、`machine:pack` 和 `sync:annotation`。旧 `sync:sqlite` 流程已移除，不应用旧 dictionary.db 重建机器库。
