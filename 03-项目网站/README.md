# 高邮二王考据过程知识库网站

`03-项目网站` 是项目的展示与检索入口。它不是单独的数据仓库，而是读取 `02-数据库` 生成的 SQLite 快照，把同一专题数据库拆成首页概览、数据库浏览、字词详情、案例详情和术语说明几种阅读视角。

## 当前定位

- 首页：说明研究对象、当前能力、代表性案例和数据库入口。
- 数据库页：统一浏览字词、案例和数据库结构。
- 人工标注库：展示 `02-数据库/data/annotations.db` 的人工标注与 AI 整理结果，作为主库之外的工作稿数据库入口。
- AI 释证：调用 `/api/ai/annotation`，固定使用 `deepseek-v4-pro`；每次请求临时检索人工标注库，必要时用主数据库补充，引用材料默认收起并逐级展开核对。
- 字词详情页：展示单个词条的释义、证据和关联案例。
- 案例详情页：展示单个考据案例的判断过程、证据和相关字词。
- 知识页：解释训诂术语，辅助阅读，不构成独立数据库。

## 运行方式

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
```

## 数据来源

当前主数据来自 SQLite 快照：

```text
02-数据库/data/dictionary.db
  -> 03-项目网站/scripts/sqlite_bridge.py
  -> 03-项目网站/data/sqlite-snapshot.json
```

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
│  ├─ ai-annotation.html           AI 释证页
│  ├─ term.html                    字词详情页
│  ├─ case.html                    案例详情页
│  ├─ knowledge.html               术语说明页
│  └─ assets/
│     ├─ css/styles.css            全站样式
│     └─ js/                       前端渲染、检索和交互脚本
├─ src/                            Node 服务、数据源、结构定义
├─ scripts/sqlite_bridge.py        SQLite 快照导出脚本
├─ scripts/annotation_bridge.py    人工标注库快照导出脚本
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
- `POST /api/ai/annotation`：AI 释证接口，固定使用 `deepseek-v4-pro`，需要配置 DeepSeek API key。

AI 释证是 one-shot 调用：每次请求只取当前问题，检索最多 5 条人工标注案例；若人工库命中不足 3 条，再补充最多 4 条主数据库案例。服务端把这些材料和系统提示一次性发送给 DeepSeek，不保留对话记忆。

## 维护规则

1. 改 SQLite 数据后，必须重新执行 `npm run sync:sqlite`。
2. 改人工标注库后，必须重新执行 `npm run sync:annotation`。
3. 改数据库字段后，同时检查 `src/store-definitions.js`、`scripts/sqlite_bridge.py` 和前端渲染脚本。
4. 改首页或详情页数据库表述时，保持“同一数据库，不同视角”的口径；人工标注库是实验性功能，不叫主库。
5. `data/sqlite-snapshot.json` 和 `data/annotation-snapshot.json` 都是导出产物，不要手工改。
6. `更新记录.md` 只记录结构、数据链路和展示口径变化，不写日常流水账。
