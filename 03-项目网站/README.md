# 高邮二王考据过程知识库网站

`03-项目网站` 是项目的展示、检索和 V2 工作库只读验收入口。它不是单独的数据仓库：旧页面读取 `02-数据库` 导出的 JSON 快照，V2 页面通过 Python bridge 读取独立的 `v2/data/real_runs/annotation_v2.db`。

## 当前定位

- 首页：说明研究对象、当前能力、代表性案例和数据库入口。
- 数据库页：统一浏览字词、案例和数据库结构。
- V2 工作库：`v2-database.html` 是案例浏览、人工待办和质量报告的统一入口，三类信息以标签分开呈现；旧 `v2-acceptance.html` 只保留兼容跳转。默认仍只读读取独立的 `v2/data/real_runs/annotation_v2.db`；只有显式设置 `V2_REVIEW_WRITE_ENABLED=1` 才开放本地人工决定写入。
- 人工标注库：展示 `02-数据库/data/annotations.db` 的人工标注与 AI 整理结果，作为主库之外的工作稿数据库入口。
- 标注工作台：给成员本地填写 `annotation_case.v1`，自动保存浏览器草稿，导出 JSON 文件后走 branch / PR。
- AI 释证：调用 `/api/ai/annotation`，固定使用 `deepseek-v4-pro`；每次请求临时检索人工标注库，必要时用主数据库补充，引用材料默认收起并逐级展开核对。
- 字词详情页：展示单个词条的释义、证据和关联案例。
- 案例详情页：展示单个考据案例的判断过程、证据和相关字词。
- 知识页：解释训诂术语，辅助阅读，不构成独立数据库。

## 运行方式

需要 Node.js 18+ 和可执行的 Python 3。旧快照页面只依赖 Node；`/api/v2/*` 还需要 Python。Windows 若 `python` 指向 Microsoft Store 别名，请把真实解释器路径设置为 `PYTHON_BIN`，也可以使用 V2 bridge 专用的 `V2_PYTHON_BIN`。

PowerShell 示例：

```powershell
$env:PYTHON_BIN = "C:\path\to\python.exe"
npm start
```

推荐在仓库根目录运行：

```bash
npm start
```

也可以在本目录运行：

```bash
npm start
```

启动后访问：

```text
http://localhost:3000
```

检查接口：

```text
/api/health
/api/bootstrap
/api/browser/bootstrap
/api/search?q=始
/api/v2/summary
```

## 数据来源

当前主数据来自 SQLite 快照：

```text
02-数据库/data/dictionary.db
  -> 03-项目网站/scripts/sqlite_bridge.py
  -> 03-项目网站/data/sqlite-snapshot.json
```

这里的主库是旧 `source.txt -> parser.py -> importer.py` 机器解析结果，不是 DeepSeek AI 输出；DeepSeek 规范化材料在独立的 `02-数据库/data/annotations.db` 和 `annotation-snapshot.json` 中。二者目前都通过 V2 适配器进入独立的 V2 工作库，不能混称为人工审核主库。

网站默认优先读取 `data/sqlite-snapshot.json`。如果 SQLite 数据变化，需要在仓库根目录运行：

```bash
npm run sync:sqlite
```

当前展示口径是“一个专题数据库，多种浏览视角”。首页的字词入口和案例入口应解释为同库的两个索引视角。

另有一个独立的人工标注灰度库：

```text
02-数据库/data/annotations.db
  -> 03-项目网站/scripts/annotation_bridge.py
  -> 03-项目网站/data/annotation-snapshot.json
  -> 03-项目网站/web/annotation.html
  -> 03-项目网站/web/ai-annotation.html
```

它不混入主数据库。`annotation.html` 只做人工库数据库浏览，`ai-annotation.html` 承接 AI 释证。更新该库后运行：

```bash
npm run sync:annotation
```

## 目录说明

```text
03-项目网站/
├─ server.js                       本目录服务入口
├─ package.json                    本目录运行脚本
├─ web/                            前端静态页面根目录
│  ├─ index.html                   首页
│  ├─ database.html                统一数据库浏览页
│  ├─ annotation.html              人工标注库数据库页
│  ├─ annotation-workbench.html     本地标注工作台，导出 annotation_case JSON
│  ├─ ai-annotation.html           AI 释证页
│  ├─ v2-database.html             V2 数据浏览、待办审校和质量报告
│  ├─ v2-acceptance.html           旧 V2 验收入口的兼容跳转
│  ├─ term.html                    字词详情页
│  ├─ case.html                    案例详情页
│  ├─ knowledge.html               术语说明页
│  └─ assets/
│     ├─ css/styles.css            全站样式
│     └─ js/                       前端渲染、检索和交互脚本
├─ src/                            Node 服务、数据源、结构定义
├─ scripts/sqlite_bridge.py        SQLite 快照导出脚本
├─ scripts/annotation_bridge.py    人工标注库快照导出脚本
├─ scripts/v2_acceptance_bridge.py V2 只读查询 bridge
├─ data/sqlite-snapshot.json       网站真实数据快照
├─ data/annotation-snapshot.json   人工标注库灰度快照
└─ media/step.png                  首页流程图
```

## API

- `GET /api/health`：服务健康和数据源状态。
- `GET /api/bootstrap`：首页初始化数据、统计和示例。
- `GET /api/schema`：数据库结构和记录数。
- `GET /api/browser/bootstrap`：数据库浏览页初始化数据。
- `GET /api/browser?view=...`：数据库浏览页分页、筛选和检索。
- `GET /api/search?q=关键词`：统一检索字词和案例。
- `GET /api/terms`：词条列表。
- `GET /api/cases?q=关键词`：案例列表或案例检索。
- `GET /api/term?id=编号`：字词详情。
- `GET /api/case?id=编号`：案例详情。
- `GET /api/v2/summary`：V2 工作库当前验收摘要。
- `GET /api/v2/cases`：V2 案例队列，支持分页、检索、来源和机器状态筛选；未提供分页参数时默认返回第 1 页、每页 50 条。
- `GET /api/v2/case?id=编号`：V2 案例完整详情，包括来源 passage、证据、过程、队列和既有事件。
- `GET /api/v2/review-tasks?stream=...&batch=...`：按批次读取静态 `review_task.v1` 任务；可选 `case_review`、`target_work_resolution`、`external_source_resolution`、`external_passage_resolution`。
- `GET /api/v2/review-task?id=任务 ID`：读取单条人工审校任务及其决定契约。
- `POST /api/v2/review`：受控人工决定写入接口；默认返回 403，只有 `V2_REVIEW_WRITE_ENABLED=1` 的本地服务才开放。它只调用 V2 已有事务 seam，要求稳定 `reviewer` 和唯一 `operation_id`，不会因读取任务或提交 target/source/passage resolution 自动产生 gold。
- `POST /api/ai/annotation`：AI 释证接口，固定使用 `deepseek-v4-pro`，需要配置 DeepSeek API key。

AI 释证是 one-shot 调用：每次请求只取当前问题，检索最多 5 条人工标注案例；若人工库命中不足 3 条，再补充最多 4 条主数据库案例。服务端把这些材料和系统提示一次性发送给 DeepSeek，不保留对话记忆。

## 维护规则

1. 改 SQLite 数据后，必须重新执行 `npm run sync:sqlite`。
2. 改人工标注库后，必须重新执行 `npm run sync:annotation`。
3. 改数据库字段后，同时检查 `src/store-definitions.js`、`scripts/sqlite_bridge.py` 和前端渲染脚本。
4. 改首页或详情页数据库表述时，保持“同一数据库，不同视角”的口径；人工标注库是实验性功能，不叫主库。
5. `data/sqlite-snapshot.json` 和 `data/annotation-snapshot.json` 都是导出产物，不要手工改。
6. `更新记录.md` 只记录结构、数据链路和展示口径变化，不写日常流水账。

V2 人工审校入口的读取和写入分开：任务 JSONL/manifest 是可重建的静态快照，VR 默认每批只显示前 20 条，可切换 50/100 条；提交后要重新运行 `python v2/scripts/build_review_task_batches.py --batch-size 100` 才会按最新队列状态重建任务包。写入 bridge 会把 `task_id`、任务类型、queue item、当前 pending 状态与任务包绑定，不能用任意 ID 绕过任务流。服务默认不打开写入，测试或本地审校时使用 `V2_REVIEW_WRITE_ENABLED=1 npm start`，并只在本地受控环境提交明确决定。
