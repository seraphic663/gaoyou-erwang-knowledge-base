# 高邮二王考据过程知识库

> 项目工作区总入口；当前说明口径复核于 2026-09-29。

在线展示：<https://gaoyou-demo.up.railway.app/>

## 先看哪里

| 你要做什么 | 先看哪里 |
| --- | --- |
| 理解项目定位、阶段目标和当前任务 | [00-项目说明/README.md](00-项目说明/README.md) → [00-项目规划与进展.md](00-项目说明/00-项目规划与进展.md) |
| 参加人工复核 | [01-项目与人工审计指南.md](00-项目说明/01-项目与人工审计指南.md) |
| 理解来源、证据、数据库和状态边界 | [02-架构、证据与数据边界.md](00-项目说明/02-架构、证据与数据边界.md) |
| 开发或维护 V2 | [03-工程、文件包与V2规范.md](00-项目说明/03-工程、文件包与V2规范.md) → [v2/README.md](v2/README.md) |
| 查看当前数量、队列和风险 | [05-当前状态与执行评估.md](00-项目说明/05-当前状态与执行评估.md) |
| 查数据库文件、快照和备份关系 | [06-数据库关系与清理状态.md](00-项目说明/06-数据库关系与清理状态.md) |
| 查原典、一级资料或标注材料 | [04-项目文献/README.md](04-项目文献/README.md) |
| 查旧兼容库的脚本和导出链 | [02-数据库/README.md](02-数据库/README.md) |
| 运行、浏览或部署网站 | [03-项目网站/README.md](03-项目网站/README.md) |
| 查看检索层 benchmark | [v2/benchmarks/README.md](v2/benchmarks/README.md) |
| 查历史材料和申报附件 | [05-归档文献/README.md](05-归档文献/README.md) |

mid.md 是研究方向和中期审查的工作备忘录，不是成员日常操作入口。原始立项、答辩和 archive/ 材料是历史证据，不根据当前研究定位倒改。

## 项目核心

项目以高邮二王材料为案例，把问题、出处、证据作用、推理和未决状态组织成可追溯、可评价的古籍考据任务。数据库、检索和网站是研究环境；当前阶段先生产真实人工复核案例；后续再形成 benchmark-ready corpus 并评价 domain-specific agent harness。

项目路线分为三层：

1. 基础设施：原典、passage、candidate、case、evidence、来源状态和检索。
2. 中期成果：少量考据过程结构化复核案例、确认版本、证据链和固定展示。
3. 长期研究：冻结任务 corpus 和 benchmark，比较 LLM-only、普通检索/RAG、generic search agent 与领域化 harness。

## 当前状态

- V2 验证快照（报告生成于 2026-09-25）记录 35 个来源文档、15,496 个 passages、6,749 个 candidates、7,581 个 cases 和 13,990 条 evidence。
- 7,581 个 V2 cases 仍是 machine draft、human pending、lifecycle=machine_draft；review_events=0、gold=0。
- 当前检索 benchmark 是 retrieval-layer v1，包含 20 个主案例和 4 个诊断控制样本；它不等于端到端考据 benchmark 或 V2 gold。
- 中期 pilot 尚未形成文件包；当前优先生产平原之隰、譕臣、造舟于河三条例案例。

## 仓库目录地图

| 目录 | 核心内容 | 当前定位 |
| --- | --- | --- |
| 00-项目说明/ | 项目定位、路线、人工流程、证据边界、V2 规范、状态和决策 | 当前项目级说明入口 |
| 01-项目资料/ | 立项、答辩、组会和项目管理资料 | 行政与过程资料 |
| 02-数据库/ | dictionary.db、annotations.db 及旧生成管线 | 旧兼容、迁移和对照 |
| 03-项目网站/ | 展示、检索、V2 浏览和五步审计入口 | 操作和展示层 |
| 04-项目文献/ | 原典、一级资料、二级资料、当前阅读和标注 | 研究材料层 |
| 05-归档文献/ | 扫描件、DOCX、PDF、申报附件和历史文件 | 归档与回查 |
| v2/ | schema、代码、测试、V2 工作库接口、任务包和 benchmark | 当前主工作库与研究基础设施 |
| daizhigev20/ | 独立外部文献 Markdown 和命中分析 | 外部 evidence acquisition 候选层 |

## 不要混用的边界

- dictionary.db、annotations.db 和 annotation_v2.db 是三种性质不同的数据库，不能统称为人工主库。
- 原典、旧数据库、旧 AI 输出和 V2 生产数据库默认只读；中期正文以 v2/research/midterm-pilot/ 文件包为编辑源。
- machine draft、五步审计记录、页面标签、检索 benchmark 和 structure-reviewed case 不能直接写成 V2 gold。
- secondary citation match、公开候选、legacy-derived passage 和 full JSON 命中不能写成外部原典已核验。
- 申报材料“不少于 60 条”和答辩材料“不少于 300 条”仍未建立换算关系；三例 pilot 不冒充完成任一数量指标。

## 运行和维护

本地网站运行、API、部署和数据源切换见 03-项目网站/README.md；V2 测试、验证、任务包和状态契约见 v2/README.md。改动项目级口径、数据库、网站或 V2 时，同步检查 [一致性检查.md](一致性检查.md)。

README 只负责定位和导航；案例正文、工程字段、部署细节、API 清单和历史推导放在相应子目录说明中。
