# 高邮二王考据过程知识库

本仓库是“高邮二王考据过程知识库构建及应用”的项目工作区，包含项目说明、申报资料、旧数据库兼容链路、V2 统一工作库、网站展示、文献材料和组会记录。

线上地址：https://gaoyou-demo.up.railway.app/

## 当前状态

- 旧展示链仍提供 49 部著作、3,385 个词条、815 个机器解析案例和 7,120 条证据，供网站首页、旧数据库浏览和兼容检索使用。
- V2 机器链路已跑通：当前工作库有 35 个来源文档、15,496 个 passages、6,749 个候选、7,581 个案例和 13,990 条证据。
- V2 的 7,581 个案例目前全部是 `machine_status=draft`、`human_status=pending`、`lifecycle=machine_draft`；`review_events=0`、gold=0，不能称为已完成人工审校的知识库。
- 当前优先任务是目标典籍消歧、外部 canonical 底本与 passage 登记、引文核验和人工审校，不是继续扩展旧 parser 产出的模板化案例。

V2 工作流和状态的优先解释见 [00-项目说明/03-工程、文件包与V2规范.md](00-项目说明/03-工程、文件包与V2规范.md)。

## 部署状态

- Railway：当前线上主展示地址，读取根目录 `railway.toml`，使用根目录 `Dockerfile` 构建并执行 `npm start`。运行镜像包含 Node 服务、网站代码、V2 Python 代码；大体量 `v2/data/` 不进入构建上下文，而是由 Railway volume 挂载到 `/app/v2/data`。
- CloudBase Run：保留为备用部署方案，同样可使用根目录 `Dockerfile`。当前仓库没有证据证明 CloudBase 已配置 V2 持久卷，因此在完成卷挂载和 `/api/v2/summary` 验证前，只能确认旧快照展示能力，不能声称 V2 在线可用。详见 [03-项目网站/CloudBase-Run-并行部署报告.md](03-%E9%A1%B9%E7%9B%AE%E7%BD%91%E7%AB%99/CloudBase-Run-%E5%B9%B6%E8%A1%8C%E9%83%A8%E7%BD%B2%E6%8A%A5%E5%91%8A.md)。
- `Dockerfile` 安装 Python 3，复制根目录 `package.json`、`03-项目网站/` 和 `v2/`；根目录没有 `server.js`，实际服务入口是 `03-项目网站/server.js`。
- `.dockerignore` 与 `.railwayignore` 都排除 `v2/data/`，防止数据库、JSONL、任务包和研究运行产物被打入镜像。

## 三条数据链路

旧主库兼容链：

```text
02-数据库/main/source.txt
  -> 02-数据库/main/parser.py
  -> 02-数据库/main/importer.py
  -> 02-数据库/data/dictionary.db
  -> 03-项目网站/scripts/sqlite_bridge.py
  -> 03-项目网站/data/sqlite-snapshot.json
  -> 旧展示页面/API
```

旧标注灰度库链：

```text
04-项目文献/D-标注/ 的 DOCX
  -> 04-项目文献/D-标注/json/run.py
  -> 02-数据库/data/annotations.db
  -> 03-项目网站/scripts/annotation_bridge.py
  -> 03-项目网站/data/annotation-snapshot.json
  -> annotation.html（旧 AI 入口仅保留兼容跳转）
```

V2 统一工作链：

```text
四部原典 Markdown / 旧 AI JSON / 旧 dictionary.db
  -> passage、候选与来源审计
  -> annotation_case.v1 适配和校验
  -> v2/data/real_runs/annotation_v2.db
  -> 人工审校任务与受控事务
  -> gold / 后续正式主库与网站快照
```

旧 `dictionary.db` 和 `annotations.db` 都是兼容、迁移与对照材料。V2 机器结果可以进入统一工作库，但未经可追溯人工审校不能进入 gold。

## 项目架构

```text
D:\26大创
├─ 00-项目说明/        项目说明、规范、状态对照和协作指南
├─ 01-项目资料/        项目管理、答辩材料和组会记录
├─ 02-数据库/          旧主库与旧标注库的兼容加工链
├─ 03-项目网站/        展示网站、API 服务、前端和旧库快照
├─ 04-项目文献/        当前研究文献、原典和标注材料
├─ 05-归档文献/        大体量归档材料；Git 只跟踪 README
└─ v2/                 V2 schema、Python 实现、测试、工作数据库和审校任务
```

根目录只保留跨模块配置和总说明。成员协作和人工审计先看 `00-项目说明/01-项目与人工审计指南.md`。当前从 `03-项目网站/annotation-workbench.html` 进入五步释证审校卡。参与 V2 正式审校前以 `00-项目说明/03-工程、文件包与V2规范.md` 和 `v2/README.md` 为准。

## 核心边界

- `02-数据库/` 保留旧数据生产链，用于兼容展示、重建、迁移和对照；其中旧状态值不等于人工审校结论。
- `03-项目网站/data/` 保存旧展示链的 JSON 快照；V2 页面通过 Python bridge 读取独立的 `annotation_v2.db`。
- `v2/data/` 是运行数据和审校任务区，不进入 Docker 构建上下文；线上必须通过受控 volume 或显式 `V2_DB_FILE` 提供。
- 本地案例默认使用被 Git 忽略的轻量测试库 `v2/data/local_test/annotation_v2.local.db`；如果本地存在四部原典库 `v2/data/real_runs/annotation_v2.db`，检索会自动把它作为原文语料库。Railway 的案例库和原文语料库都自动使用 volume 下的 `v2/data/real_runs/annotation_v2.db`。需要显式切换案例库或原文语料库时分别设置 `V2_DB_FILE` 或 `V2_CORPUS_DB_FILE`。
- `04-项目文献/` 保留当前参与阅读、标注和释证的材料；`05-归档文献/` 保存大体量扫描件和历史文件。
- V2 正式人工决定默认只读；只有显式设置 `V2_REVIEW_WRITE_ENABLED=1` 才开放受任务绑定的 review 写入。五步审计卡使用独立的 `V2_FIVE_STEP_AUDIT_WRITE_ENABLED=1` 开关，不改变案例状态或 gold。

## 本地运行

需要 Node.js 18+ 和可执行的 Python 3。Windows 若 `python`/`python3` 指向 Microsoft Store 别名，V2 bridge 会跳过 9009 失败并尝试常见安装路径；仍可用 `PYTHON_BIN` 或 `V2_PYTHON_BIN` 明确指定解释器。

PowerShell 示例：

```powershell
$env:PYTHON_BIN = "C:\path\to\python.exe"
& $env:PYTHON_BIN v2/scripts/create_local_test_db.py
npm start
```

本地测试库只由 `v2/data/fixtures/` 生成，适合生成五步草稿和保存测试审计记录；不会读取或修改 Railway 生产库。重复运行创建脚本会重建该本地测试库。

五步草稿的原文检索是只读的：`GET /api/v2/retrieve?case_id=<V2 case_id>` 会先在当前案例所属作品中查找，再在必要时返回跨作品候选参考；`POST /api/v2/five-step-draft` 会把检索到的原文段落一并交给模型，并在响应中保留检索快照。检索库可通过 `V2_CORPUS_DB_FILE` 指向之后上传的四部著作库。

检索 benchmark 位于 `v2/benchmarks/case2query2retrieve.v1.json`：20 个案例按四部著作平衡抽样，另有简繁转换、无命中和无效 query 控制样本。`v2/scripts/run_retrieval_benchmark.py` 可对本地或 Railway URL 运行同一套 manifest，输出 Recall@k、MRR、hard negative 和范围违规；v1 只测确定性的 lexical rank，不把 AI rerank 混入基础召回指标。

启动后访问：

```text
http://localhost:3000/
http://localhost:3000/v2-database.html
http://localhost:3000/annotation-workbench.html
http://localhost:3000/annotation-workbench.html?case=<V2 case_id>
```

常用只读检查：

```text
http://localhost:3000/api/health
http://localhost:3000/api/bootstrap
http://localhost:3000/api/v2/summary
```

## 常用维护命令

```bash
python 02-数据库/main/importer.py --dry-run
python 02-数据库/main/importer.py
npm run sync:sqlite
npm run sync:annotation
python v2/scripts/run_v2_validation.py
python v2/scripts/build_work_queues.py
python v2/scripts/build_review_task_batches.py --batch-size 100
python -B -m unittest discover -s v2/tests -p "test_*.py" -v
```

维护时先确认自己操作的是旧兼容链还是 V2 工作链。数据库和生成型 JSON/JSONL 不手工编辑；人工审校写入后重新生成队列、任务包和验证报告。

## 仓库维护原则

- 保留可重建链路和清楚的来源边界，不把旧机器材料改名包装成人工 gold。
- `dictionary.db`、`annotations.db` 和 `annotation_v2.db` 是三个性质不同的数据库，不再统称“两个数据库”或混写为同一主库。
- 不提交缓存、journal、临时库和其他生成型中间文件。
- 大体量文献和 `v2/data/` 不进入容器构建上下文；部署数据通过快照或受控持久卷提供。
- 改动数据结构、API、部署方式或状态口径时，同步检查根 README、相关目录 README、`00-项目说明/02-架构、证据与数据边界.md`、`00-项目说明/03-工程、文件包与V2规范.md`、`00-项目说明/05-当前状态与执行评估.md` 和 `一致性检查.md`。
