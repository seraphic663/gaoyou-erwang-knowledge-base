# 高邮二王考据过程知识库

> 项目工作区总入口；当前说明口径复核于 2026-09-30。

在线展示：<https://gaoyou-demo.up.railway.app/>

## 先看哪里

| 你要做什么 | 先看哪里 |
| --- | --- |
| 理解项目定位、阶段目标和当前任务 | [docs/project/README.md](docs/project/README.md) → [00-项目规划与进展.md](docs/project/00-项目规划与进展.md) |
| 参加人工复核 | [01-项目与人工审计指南.md](docs/project/01-项目与人工审计指南.md) |
| 理解来源、证据、数据库和状态边界 | [02-架构、证据与数据边界.md](docs/project/02-架构、证据与数据边界.md) |
| 开发或维护 V2 | [03-工程、文件包与V2规范.md](docs/project/03-工程、文件包与V2规范.md) → [v2/README.md](v2/README.md) |
| 查看当前数量、队列和风险 | [05-当前状态与执行评估.md](docs/project/05-当前状态与执行评估.md) |
| 查数据库文件、快照和备份关系 | [06-数据库关系与清理状态.md](docs/project/06-数据库关系与清理状态.md) |
| 查原典、一级资料或标注材料 | [data/README.md](data/README.md) → [data/literature.md](data/literature.md) |
| 查旧兼容库的脚本和导出链 | [solution/legacy-db/README.md](solution/legacy-db/README.md) |
| 运行、浏览或部署网站 | [solution/website/README.md](solution/website/README.md) |
| 查看检索层 benchmark | [research/analysis/benchmarks/README.md](research/analysis/benchmarks/README.md) |
| 查历史材料和申报附件 | [archive/literature/README.md](archive/literature/README.md) |
| 维护目录、Markdown 和权威边界 | [docs/operations/markdown-governance.md](docs/operations/markdown-governance.md) |

## 工作区架构

本工作区按研究生命周期组织：`docs/` 保存当前上下文，`research/` 保存研究问题和中期案例，`solution/` 保存工程，`data/` 保存来源材料，`archive/` 保存历史证据，`tmp/` 保存可重建临时产物；构建和部署契约集中在 `ops/`，Git/Docker/Railway 必须读取的少数根级契约文件保留在根部。

目录迁移只改变职责和路径，不改变数据库角色、来源状态、人工复核门禁或历史材料的证据身份。

docs/research-plan.md 是研究方向和中期审查的工作备忘录，不是成员日常操作入口。原始立项、答辩和 archive/ 材料是历史证据，不根据当前研究定位倒改。

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
- 2026-09-30 结构复核后，根层不再保留 `analysis/`、`audit/`、`external/`；构建依赖和容器入口集中在 `ops/`，研究分析统一在 `research/analysis/`，外部语料统一在 `data/daizhigev20/`。

## 仓库目录地图

| 目录 | 核心内容 | 当前定位 |
| --- | --- | --- |
| docs/ | 项目定位、管理资料、研究规划和交接 | 当前上下文入口 |
| research/ | 外部来源研究和中期案例文件包 | 研究工作层 |
| solution/ | 旧兼容管线和网站代码 | 工程与运行层 |
| data/ | 原典、一级资料、标注输入和数据说明 | 来源材料层 |
| archive/ | 扫描件、DOCX、PDF、申报附件和历史文件 | 历史证据层 |
| research/analysis/ | benchmark 定义和评价分析 | 可复核分析层 |
| docs/operations/ | 一致性和迁移检查 | 审计层 |
| ops/ | 容器构建和 Node 运行时依赖 | 构建与部署层 |
| v2/ | schema、代码、测试、V2 工作库接口和运行数据 | 当前核心工作包 |
| data/daizhigev20/ | 独立外部文献及其分析 | 外部 evidence acquisition 候选层 |
| tmp/ | 审阅渲染、实验输出、备份和可重建缓存 | 临时层，不是权威来源 |

## Markdown 分层与权威顺序

- 当前维护文档：根 `README.md`、`docs/project/`、`docs/operations/`、各业务目录 README、`ops/README.md`；这些文件负责导航、边界和可执行入口。
- 当前研究工作层：`research/`、`data/0-当前阅读/annotation/` 和明确声明为编辑源的文件包；修改前必须保留来源、版本和人工判断边界。
- 只读来源层：`data/` 的原始文献、`data/daizhigev20/` 的外部语料、旧数据库和 `v2/data/` 生产/运行材料；只修复指针或生成元数据，不改原文和生产结果。
- 历史/临时层：`archive/`、`docs/project/archive/`、`tmp/`；用于追溯和比较，不倒改成当前口径。
- 依赖层：`ops/node_modules/`、`solution/website/node_modules/`、`v2/.venv/`；第三方 Markdown 不属于项目文档。

路径与构建行为以代码和配置为准，数量与运行状态以对应生成报告为准，研究结论以来源材料和人工确认记录为准；发生冲突时，不用历史 Markdown 覆盖当前实现或权威来源。

## 不要混用的边界

- dictionary.db、annotations.db 和 annotation_v2.db 是三种性质不同的数据库，不能统称为人工主库。
- 原典、旧数据库、旧 AI 输出和 V2 生产数据库默认只读；中期正文以 research/midterm-pilot/ 文件包为编辑源。
- machine draft、五步审计记录、页面标签、检索 benchmark 和 structure-reviewed case 不能直接写成 V2 gold。
- secondary citation match、公开候选、legacy-derived passage 和 full JSON 命中不能写成外部原典已核验。
- 申报材料“不少于 60 条”和答辩材料“不少于 300 条”仍未建立换算关系；三例 pilot 不冒充完成任一数量指标。

## 运行和维护

本地网站运行、API、部署和数据源切换见 solution/website/README.md；V2 测试、验证、任务包和状态契约见 v2/README.md。改动项目级口径、数据库、网站或 V2 时，同步检查 [docs/operations/consistency.md](docs/operations/consistency.md)，修改 Markdown 时同步遵守 [Markdown 治理说明](docs/operations/markdown-governance.md)。

README 只负责定位和导航；案例正文、工程字段、部署细节、API 清单和历史推导放在相应子目录说明中。
