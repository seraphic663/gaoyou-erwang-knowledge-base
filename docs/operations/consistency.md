# 项目一致性检查清单

> 当前结构与路径复核：2026-09-30；数量和运行状态仍以对应生成报告日期为准。

本文件用于提醒：改网站、数据库、V2 工作流、研究说明或 README 时，必须同步检查相关文件。当前目录结构以 `docs/project / docs/management / docs/operations / solution/legacy-db / solution/website / data / data/daizhigev20 / archive/literature / research/analysis / v2` 为准；组会记录归入 `docs/management/组会谈话/`。

## 一、核心口径

- 项目名称：高邮二王考据过程知识库构建及应用。
- 研究内核：以高邮二王材料为案例，构建可追溯、可评价的古籍考据任务和研究环境。
- 当前阶段：少量结构化复核案例；长期路线是 benchmark-ready corpus 和领域化 agent harness 评价。
- 展示定位：研究整理和操作原型，不写成泛化古籍平台。
- 旧展示定位：一个专题数据库，多种浏览视角；旧 `dictionary.db` 是机器解析兼容库，不称人工主库。
- 旧展示链：`solution/legacy-db/main/source.txt -> parser.py -> importer.py -> solution/legacy-db/data/dictionary.db -> sqlite_bridge.py -> sqlite-snapshot.json`。
- 旧标注链：`DOCX -> data/D-标注/json/run.py -> solution/legacy-db/data/annotations.db -> annotation_bridge.py -> annotation-snapshot.json`。
- V2 链：`原典/旧数据 -> passage/candidate/adapter/validator -> v2/data/real_runs/annotation_v2.db -> human_review -> gold`；机器草稿、结构化复核、benchmark-ready 和 V2 gold 必须分开。
- benchmark 口径：当前 research/analysis/benchmarks/ 主要是 retrieval-layer 诊断 benchmark；不得写成端到端考据 benchmark 或 agent 实验。
- 代表案例：首页当前以《经义述闻·左传下》“造舟于河”为主线案例。
- 项目说明入口：项目级说明、工程路线和协作指南集中放在 `docs/project/`。

## 二、改动联动规则

| 如果修改 | 必须同步检查 |
| --- | --- |
| `solution/website/index.html`、`app.js` | 根 `README.md`、网站 `README.md`、网站更新记录、申报资料中项目名称和展示口径 |
| `database.html`、`browser.js`、`term.html`、`case.html`、`detail.js` | 数据库 README、网站 README、`src/store-definitions.js`、数据统计是否一致 |
| `annotation.html`、`annotation.js` | 标注库 README、网站 README、`annotation-snapshot.json` |
| `corpus.html`、`corpus-browser.js`、`/api/corpus/*` | 网站 README、corpus bridge、检索 benchmark README、线上 API 检查 |
| `ai-annotation.html`、`ai-annotation.js`、`src/ai-annotation.js` | 网站 README、DeepSeek API key 说明、AI 引用展开交互 |
| `v2-database.html`、V2 前端脚本或 `/api/v2/*` | `v2/README.md`、网站 README、`docs/project/03-工程、文件包与V2规范.md`、`docs/project/05-当前状态与执行评估.md`、Python bridge、相关 benchmark README |
| `v2/schemas/`、`v2/src/`、`v2/scripts/` | `docs/project/03-工程、文件包与V2规范.md`、V2 README、测试、验证报告和任务包生成链 |
| `annotation_v2.db`、work queues、review tasks 或 review transaction | V2 验证报告、任务 manifest、状态计数、gold gate、网站 V2 summary；禁止手工改数据库 |
| `solution/legacy-db/main/`（source.txt、parser.py、importer.py、database.py） | `solution/legacy-db/README.md`、`solution/website/scripts/sqlite_bridge.py`、网站快照 |
| `solution/legacy-db/annotation/` 或标注库 schema 变更 | `solution/legacy-db/README.md`、`solution/website/scripts/annotation_bridge.py`、annotation-snapshot.json |
| `solution/website/data/sqlite-snapshot.json` | 首页统计、数据库页统计、申报材料中的数据量表述 |
| `solution/website/src/http-server.js` API 变更 | `solution/website/README.md`、部署迁移说明、健康检查和演示检查清单 |
| `ops/Dockerfile`、`railway.toml`、`ops/package.json` | 根 `README.md`、网站部署报告、迁移说明、线上 `/api/health` |
| `data/0-当前阅读/` | 首页案例、知识页术语、文献 README |
| `data/A-原著原典/` 或 `B-一级资料/` | `data/README.md`、`docs/project/02-架构、证据与数据边界.md`、V2 来源登记和 passage 建设路线 |
| `archive/literature/` 的目录结构或归档规则 | `archive/literature/README.md`、根 `README.md`、`.gitignore` |
| `docs/project/` | 根 `README.md`、`docs/operations/consistency.md`、相关目录 README |
| 当前 Markdown 导航、目录或路径 | 根 `README.md`、相关目录 README、`docs/operations/markdown-governance.md`、内部链接扫描 |
| 根 `README.md`、各目录 `README.md` | `docs/project/`、网站更新记录、benchmark 说明和冗余性分析报告 |
| 人工审计协作或 Git 规则 | `docs/project/01-项目与人工审计指南.md`、根 `README.md` 中的成员入口 |

## 三、提交前检查

每次提交前至少做这些检查：

1. 搜索旧路径：`01-项目申报`、`01-立项申报`、`D-二级资料`、`F-标注`。
2. 搜索旧数据源：`demo-db.json`、`parsed_data.py`、`dictionary.empty.db`、`step2.png`。
3. 搜索旧口径：`两套数据库`、`字词数据库`、`案例数据库`。
4. 搜索旧部署片段：`COPY server.js ./`、`NIXPACKS`。
5. 确认运行时文件不入仓：`.env`、`__pycache__/`、`*.db-wal`、`*.db-shm`。
6. 确认 `archive/literature/` 只提交 `README.md`，不要提交 PDF、DOCX、扫描图、签名和编译产物。
7. 如果改了前端脚本，运行 `node --check`。
8. 如果改了主库脚本，运行 `python solution/legacy-db/main/importer.py --dry-run`。
9. 如果改了 SQLite 主库，运行 `npm --prefix solution/website run sync:sqlite`。
10. 如果改了 SQLite 标注库，运行 `npm --prefix solution/website run sync:annotation`。
11. 提交前运行 `git diff --check`。
12. 如果改了 V2，运行 `python -B -m unittest discover -s v2/tests -p "test_*.py" -v` 和 `python v2/scripts/run_v2_validation.py`，并核对数据库、队列、任务包和报告时间是否一致。
13. 如果改了 Docker 构建输入，确认 `.dockerignore` 与 `.railwayignore` 均未把 `v2/data/` 或文献大文件送入构建上下文。

## 四、当前保留边界

- `solution/legacy-db/main/parser.py`、`main/importer.py`、`main/database.py` 必须保留，因为它们解释数据库如何重建。
- `solution/legacy-db/lib/` 是共享工具层，被主库、标注库和桥接脚本共用。
- `solution/legacy-db/data/` 放两个 SQLite 产物：`dictionary.db` 和 `annotations.db`。
- `parsed_data.py` 不再保留，因为它是生成型中间文件。
- Python 脚本重新计入 GitHub 语言统计；当前体量不会造成项目语言比例畸形。
- `solution/website/data/sqlite-snapshot.json` 是网站展示快照，不要手工改，优先从 SQLite 导出。
- `solution/website/data/annotation-snapshot.json` 是人工标注灰度库快照，不要手工改，优先从标注库导出。
- `v2/data/real_runs/annotation_v2.db` 是 V2 统一工作数据库；机器和人工状态共存但必须分开，不进入 Docker 镜像，不手工编辑。
- V2 审校任务 JSONL/manifest 是可重建快照；人工事务写入后必须重建队列、任务包和验证报告。
- V2 默认只读；`V2_REVIEW_WRITE_ENABLED=1` 只用于本地受控审校，不作为线上常开配置。
- 首页不保留累计访问计数；线上容器不应依赖运行时 JSON 做持久化展示。
- `archive/literature/` 是本地归档区，Git 只跟踪 `archive/literature/README.md`。
- `docs/project/` 是项目级说明区，协作、工程路线和问题分析在这里维护；不要把私人申请、投稿规划放进共享文档。
