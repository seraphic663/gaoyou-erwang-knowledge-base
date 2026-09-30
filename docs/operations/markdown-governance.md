# Markdown 治理与结构复核

> 当前复核：2026-09-30

本文件规定 `D:\26大创` 内 Markdown 的分层、权威顺序和重构边界，避免把项目说明、原始文献、历史快照、临时产物和第三方依赖混成同一种文档。

## 1. 本次扫描口径

本次扫描覆盖所有非 Git Markdown；重构前扫描基线为 696 个文件。按职责分为 136 个项目维护文档、296 个原始/来源材料、252 个历史或临时材料和 12 个依赖/环境自带文档。新增本文件后，维护文档和总数各增加 1；这些数量是扫描快照，不是项目研究指标。

扫描不等于逐字改写。项目维护文档按当前目录和运行事实重构；原始文献、外部语料、历史快照和第三方依赖只做路径、链接和边界检查，保留原文与历史身份。

## 2. 当前目录分层

| 层 | 目录 | Markdown 处理规则 |
| --- | --- | --- |
| 当前入口 | `README.md`、`docs/project/`、`docs/operations/`、各业务目录 README | 可以按当前实现、路径和状态重构；必须保留日期和证据边界 |
| 研究工作 | `research/`、`data/0-当前阅读/annotation/` | 可以补充研究记录和人工工作说明；不得把 machine draft 写成 gold |
| 来源材料 | `data/`、`data/daizhigev20/`、`v2/data/external_sources/` | 默认只读；只修复明确的链接或派生元数据，不改原始正文 |
| 工程说明 | `solution/`、`v2/`、`ops/` | 以代码、配置、schema 和生成报告为准，命令必须从当前根路径可执行 |
| 历史/临时 | `archive/`、`docs/project/archive/`、`tmp/` | 保留历史口径和实验上下文，不倒改成当前说明 |
| 依赖/环境 | `ops/node_modules/`、`solution/website/node_modules/`、`v2/.venv/` | 不属于项目 Markdown，不手工重构 |

## 3. 当前权威顺序

1. 路径、构建和运行行为以源码、配置文件和实际检查结果为准。
2. 数量、队列和状态以对应日期的生成报告为准；报告日期必须和正文叙述分开写。
3. 研究结论以来源材料、人工意见和确认版本为准；自动抽取、检索命中和 AI 草稿只能作为过程材料。
4. 当前说明文档负责解释入口和边界，不覆盖历史快照，也不替代原始资料。

## 4. 根层路径地图

| 旧职责 | 当前入口 | 说明 |
| --- | --- | --- |
| 构建和 Node 依赖 | `ops/Dockerfile`、`ops/package.json`、`ops/package-lock.json` | 根 `railway.toml` 指向 `ops/Dockerfile`，网站源代码仍在 `solution/website/` |
| 检索层分析 | `research/analysis/benchmarks/` | 只保存 retrieval-layer 评价定义和结果解释 |
| 一致性和迁移检查 | `docs/operations/` | 当前结构审计和 Markdown 治理入口 |
| 外部文献及分析 | `data/daizhigev20/` | 外部 evidence acquisition 候选层，不自动成为 canonical |
| 旧兼容数据库 | `solution/legacy-db/` | 旧 SQLite、重建脚本和桥接链 |
| V2 工作库 | `v2/` | schema、代码、测试、任务包和运行数据契约 |

## 5. 修改规则

- 修改当前说明时，同时检查根 README、对应目录 README、`docs/project/` 和 `docs/operations/consistency.md`。
- 修改路径时，必须同步检查 Markdown 内链、代码默认路径、Docker/Railway 配置、`.gitattributes` 和相关生成 JSON 中的 provenance path。
- 修改原始文献、外部语料或历史快照前，先确认这不是只读权威来源；结构整理优先通过 README、索引或派生清单完成。
- 不删除无法立即证明可重建的 Markdown、生成报告、链接目标或历史材料；需要清理时先建立引用和备份证据。
- 文档可以说明“尚未完成”，但不得使用历史快照中的旧路径、旧数量或旧状态冒充当前事实。

## 6. 本次复核结果

当前根层已收束为 `docs/`、`research/`、`solution/`、`data/`、`archive/`、`ops/`、`v2/` 和 `tmp/`；`analysis/`、`audit/`、`external/` 不再作为根级目录。项目维护文档、历史材料和当前工作材料的内部 Markdown 链接已按当前路径复核，结果为 0 条断链；全量扫描另发现 4,123 条断链全部位于 `data/daizhigev20/` 的上游语料切片内部，它们指向未随本地切片保存的上游文件，不对该只读外部语料做批量改写。
