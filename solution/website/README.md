# 高邮二王考据过程知识库网站

> 网站入口和目录路径复核于 2026-09-30。

`solution/website` 是项目的展示、通用语料检索和 V2 工作库入口。它不是单独的数据仓库：旧页面读取 `solution/legacy-db` 导出的 JSON 快照，通用 corpus 和 V2 页面通过只读 bridge 读取当前工作数据库；检索接口与 V2 审校接口分开。

在项目总体路线中，网站是研究操作和成果展示层，不是独立的研究贡献。固定成果页面只能从中期确认版本派生；V2 页面和五步卡提供检索、AI 备料和审计记录，但不把页面标签或五步记录显示成 gold。

## 先定位

| 你要做什么 | 入口 |
| --- | --- |
| 看线上或本地网站 | 本文的运行方式和部署说明 |
| 检索通用 corpus 正文 | corpus.html |
| 浏览 V2 案例和质量报告 | v2-database.html |
| 进入五步 AI 辅助审计 | annotation-workbench.html |
| 查旧数据库快照 | database.html、annotation.html |
| 查 API 和数据源 | 本文的 API、数据来源和目录说明 |
| 查项目级研究口径 | ../../docs/project/README.md |

## 当前定位

- 首页：说明研究对象、当前能力、代表性案例和数据库入口。
- 首页“数据库”入口提供主数据库、人工标注库、通用语料库和 V2 工作库四个选项；各入口的查询与写入边界仍独立。
- 数据库页：统一浏览主库字词、案例和数据库结构。
- 通用语料库：`corpus.html` 和 `/api/corpus/retrieve` 只读检索 canonical passage，显示出处、定位和关联案例；它不显示或修改 V2 质量判定，也不承担人工审校。
- V2 工作库：`v2-database.html` 是完整案例库和质量报告入口；`annotation-workbench.html` 无参数时提供轻量案例选择器，有 `case` 参数时进入单案例五步审校。旧 `v2-acceptance.html` 只保留兼容跳转。Railway 的工作库自动读取 volume 下的 `v2/data/real_runs/annotation_v2.db`；本地案例默认读取被忽略的 `v2/data/local_test/annotation_v2.local.db`。通用 corpus 可用 `CORPUS_DB_FILE` 指定；正式人工决定写入使用 `V2_REVIEW_WRITE_ENABLED=1`，五步审计卡记录使用独立开关。
- 人工标注库：展示 `solution/legacy-db/data/annotations.db` 的人工标注与 AI 整理结果，作为主库之外的工作稿数据库入口。
- 五步释证：无 `case` 参数时先在页面内选择案例；选中 V2 案例后生成 AI 五步草稿，人工逐步修改和记录意见；保存到独立 `five_step_audit_records` 表，不改变案例状态。它是 AI 辅助审计流程，不等于后续的 domain-specific agent harness。Railway 默认保持只读，本地测试库默认允许保存；仍可用 `V2_FIVE_STEP_AUDIT_WRITE_ENABLED=0` 显式关闭。
- AI 释证：旧的一次性接口仍保留供兼容调用；`ai-annotation.html` 现在跳转到五步释证，网站主流程统一从 V2 案例开始。
- 字词详情页：展示单个词条的释义、证据和关联案例。
- 案例详情页：展示单个考据案例的判断过程、证据和相关字词。
- 知识页：解释训诂术语，辅助阅读，不构成独立数据库。

## 运行方式

需要 Node.js 18+ 和可执行的 Python 3。旧快照页面只依赖 Node；`/api/corpus/*` 和 `/api/v2/*` 还需要 Python。Windows 若 `python`/`python3` 指向 Microsoft Store 别名，bridge 会跳过 9009 失败并尝试常见安装路径；仍可用 `PYTHON_BIN` 或 `V2_PYTHON_BIN` 明确指定解释器。

PowerShell 示例：

```powershell
$env:PYTHON_BIN = "C:\path\to\python.exe"
node solution/website/server.js
```

推荐在仓库根目录运行：

```bash
node solution/website/server.js
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
solution/legacy-db/data/dictionary.db
  -> solution/website/scripts/sqlite_bridge.py
  -> solution/website/data/sqlite-snapshot.json
```

这里的主库是旧 `source.txt -> parser.py -> importer.py` 机器解析结果，不是 DeepSeek AI 输出；DeepSeek 规范化材料在独立的 `solution/legacy-db/data/annotations.db` 和 `annotation-snapshot.json` 中。二者目前都通过 V2 适配器进入独立的 V2 工作库，不能混称为人工审核主库。

网站默认优先读取 `data/sqlite-snapshot.json`。如果 SQLite 数据变化，需要在仓库根目录运行：

```bash
npm --prefix solution/website run sync:sqlite
```

当前展示口径是“一个专题数据库，多种浏览视角”。首页的字词入口和案例入口应解释为同库的两个索引视角。

另有一个独立的人工标注灰度库：

```text
solution/legacy-db/data/annotations.db
  -> solution/website/scripts/annotation_bridge.py
  -> solution/website/data/annotation-snapshot.json
  -> solution/website/web/annotation.html
  -> solution/website/web/ai-annotation.html
```

它不混入主数据库。`annotation.html` 只做人工库数据库浏览；旧的 `ai-annotation.html` 只保留兼容跳转。更新该库后运行：

```bash
npm --prefix solution/website run sync:annotation
```

## 目录说明

```text
solution/website/
├─ server.js                       本目录服务入口
├─ package.json                    本目录运行脚本
├─ web/                            前端静态页面根目录
│  ├─ index.html                   首页
│  ├─ database.html                统一数据库浏览页
│  ├─ annotation.html              人工标注库数据库页
│  ├─ annotation-workbench.html     五步释证审校卡，从 V2 案例启动
│  ├─ ai-annotation.html           旧 AI 入口的兼容跳转页
│  ├─ corpus.html                  通用 corpus 正文检索入口
│  ├─ v2-database.html             V2 案例浏览和质量报告；案例进入五步 AI 审校
│  ├─ v2-acceptance.html           旧 V2 验收入口的兼容跳转
│  ├─ term.html                    字词详情页
│  ├─ case.html                    案例详情页
│  ├─ knowledge.html               术语说明页
│  └─ assets/
│     ├─ css/styles.css            全站样式
│     ├─ css/corpus.css             通用 corpus 检索样式
│     ├─ js/corpus-browser.js       通用 corpus 正文检索
│     └─ js/                       前端渲染、检索和交互脚本
├─ src/                            Node 服务、数据源、结构定义
├─ scripts/sqlite_bridge.py        SQLite 快照导出脚本
├─ scripts/annotation_bridge.py    人工标注库快照导出脚本
├─ scripts/corpus_retrieval_bridge.py 通用 corpus 只读检索 bridge
├─ scripts/v2_acceptance_bridge.py V2 只读查询 bridge
├─ data/sqlite-snapshot.json       网站真实数据快照
├─ data/annotation-snapshot.json   人工标注库灰度快照
└─ media/step.png                  首页流程图
```

五步审计卡的数据库写入 bridge 位于工作区共用 V2 目录：`v2/scripts/v2_five_step_audit_bridge.py`。

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
- `GET /api/corpus/retrieve?q=关键词&work_key=作品键`：只读检索 canonical passage；可传 `include_cases=1` 返回轻量关联案例链接。
- `GET /api/v2/summary`：V2 工作库当前验收摘要。
- `GET /api/v2/cases`：V2 案例队列，支持分页、检索、来源和机器状态筛选；未提供分页参数时默认返回第 1 页、每页 50 条。
- `GET /api/v2/case?id=编号`：V2 案例完整详情，包括来源 passage、证据、过程、队列和既有事件。
- `GET /api/corpus/retrieve?q=关键词&work_key=作品键` 或 `GET /api/corpus/retrieve?case_id=编号`：通用 corpus 只读检索接口；正文查询返回 canonical passage，案例查询返回五步释证所需的检索材料。
- `GET /api/v2/review-tasks?stream=...&batch=...`：按批次读取静态 `review_task.v1` 任务；可选 `case_review`、`target_work_resolution`、`external_source_resolution`、`external_passage_resolution`。
- `GET /api/v2/review-task?id=任务 ID`：读取单条人工审校任务及其决定契约。
- `POST /api/v2/review`：受控人工决定写入接口；默认返回 403，只有 `V2_REVIEW_WRITE_ENABLED=1` 的本地服务才开放。它只调用 V2 已有事务 seam，要求稳定 `reviewer` 和唯一 `operation_id`，不会因读取任务或提交 target/source/passage resolution 自动产生 gold。
- 上述 `review-tasks` / `review` 接口保留给迁移维护和受控试验使用，不在网站主路径展示；网站审校入口是选择案例后进入五步 AI 审校。
- `POST /api/v2/five-step-draft`：读取指定 V2 案例及其来源段落、evidence、来源状态，检索当前原文语料库后调用 DeepSeek 输出五步 JSON 草稿；响应保留本次检索到的 passage 快照。模型只允许 `deepseek-flash` 或 `deepseek-v4-pro`，思考强度只允许 `none/low/high/max`。
- `GET /api/v2/five-step-audits?case_id=...`：读取该案例最近 50 条五步审计记录及本地写入开关状态，包含版本、被替代和软删除状态。
- `POST /api/v2/five-step-audits`：默认返回 403；设置 `V2_FIVE_STEP_AUDIT_WRITE_ENABLED=1` 后，追加一条含模型配置、AI 草稿、逐步意见、人工文本和 V2 来源指纹的记录；`mode=restore` 可恢复一条软删除记录。此接口不改 `annotation_cases`、`human_status` 或 gold。
- `PATCH /api/v2/five-step-audits`：在写入开关打开时修改一条当前版本记录，生成新版本并保留旧记录。
- `DELETE /api/v2/five-step-audits`：在写入开关打开时软删除一条记录，保留原内容和删除人/时间/原因，页面可恢复。
- `POST /api/ai/annotation`：旧版一次性释证兼容接口，固定使用 `deepseek-v4-pro`，需要配置 DeepSeek API key；网站主页面不再进入此接口。

旧版 AI 释证是 one-shot 调用：每次请求只取当前问题，检索最多 5 条人工标注案例；若人工库命中不足 3 条，再补充最多 4 条主数据库案例。服务端把这些材料和系统提示一次性发送给 DeepSeek，不保留对话记忆。新的 AI 审校主流程使用 V2 五步接口。

## 维护规则

1. 改 SQLite 数据后，必须重新执行 `npm --prefix solution/website run sync:sqlite`。
2. 改人工标注库后，必须重新执行 `npm --prefix solution/website run sync:annotation`。
3. 改数据库字段后，同时检查 `src/store-definitions.js`、`scripts/sqlite_bridge.py` 和前端渲染脚本。
4. 首页入口归并不代表合并数据库；保留主库、人工标注库和 V2 工作库的数据边界，网站只保留 V2 五步释证这一条 AI 审校主流程。
5. `data/sqlite-snapshot.json` 和 `data/annotation-snapshot.json` 都是导出产物，不要手工改。
6. `更新记录.md` 只记录结构、数据链路和展示口径变化，不写日常流水账。

V2 正式人工决定入口与五步审计卡记录分开：现有 review-task 写入仍要求任务绑定并遵循批准门；五步卡记录保存到独立表，修改采用版本链，删除采用可恢复软删除，不改变案例正式状态。服务默认不打开正式 review 写入；五步审计卡可单独使用 `V2_FIVE_STEP_AUDIT_WRITE_ENABLED=1 node solution/website/server.js`。DeepSeek 五步卡默认 `deepseek-flash` + `high`，审校者可改用 `deepseek-v4-pro` 和 `none/low/high/max`，提交记录会保留请求模型、返回模型、effort、草稿、意见和案例指纹。
