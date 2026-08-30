# 高邮二王考据过程知识库

本仓库是“高邮二王考据过程知识库构建及应用”的项目工作区，包含项目说明、申报资料、旧数据库兼容链路、V2 统一工作库、网站展示、文献材料和组会记录。

线上地址：https://gaoyou-demo.up.railway.app/

## 当前状态

- 旧展示链仍提供 49 部著作、3,385 个词条、815 个机器解析案例和 7,120 条证据，供网站首页、旧数据库浏览和兼容检索使用。
- V2 机器链路已跑通：当前工作库有 35 个来源文档、15,496 个 passages、6,749 个候选、7,581 个案例和 13,990 条证据。
- V2 的 7,581 个案例目前全部是 `machine_status=draft`、`human_status=pending`、`lifecycle=machine_draft`；`review_events=0`、gold=0，不能称为已完成人工审校的知识库。
- 当前优先任务是目标典籍消歧、外部 canonical 底本与 passage 登记、引文核验和人工审校，不是继续扩展旧 parser 产出的模板化案例。

V2 工作流和状态的优先解释见 [00-项目说明/10-V2统一工作流与数据库状态规范.md](00-%E9%A1%B9%E7%9B%AE%E8%AF%B4%E6%98%8E/10-V2%E7%BB%9F%E4%B8%80%E5%B7%A5%E4%BD%9C%E6%B5%81%E4%B8%8E%E6%95%B0%E6%8D%AE%E5%BA%93%E7%8A%B6%E6%80%81%E8%A7%84%E8%8C%83.md)。

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
  -> annotation.html / ai-annotation.html
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

根目录只保留跨模块配置和总说明。成员协作先看 `00-项目说明/06-Git协作指南.md`；使用旧本地 JSON 标注工作台前看 `00-项目说明/07-标注工作台使用流程.md`；参与 V2 审校前以 `00-项目说明/10-V2统一工作流与数据库状态规范.md` 和 `v2/README.md` 为准。

## 核心边界

- `02-数据库/` 保留旧数据生产链，用于兼容展示、重建、迁移和对照；其中旧状态值不等于人工审校结论。
- `03-项目网站/data/` 保存旧展示链的 JSON 快照；V2 页面通过 Python bridge 读取独立的 `annotation_v2.db`。
- `v2/data/` 是运行数据和审校任务区，不进入 Docker 构建上下文；线上必须通过受控 volume 或显式 `V2_DB_FILE` 提供。
- `04-项目文献/` 保留当前参与阅读、标注和释证的材料；`05-归档文献/` 保存大体量扫描件和历史文件。
- V2 默认只读；只有显式设置 `V2_REVIEW_WRITE_ENABLED=1` 才开放本地人工决定写入，并且仍受任务绑定、幂等 operation 和 gold gate 约束。

## 本地运行

需要 Node.js 18+ 和可执行的 Python 3。Windows 若 `python` 指向 Microsoft Store 别名，应先把真实解释器路径写入 `PYTHON_BIN`；V2 bridge 也兼容 `V2_PYTHON_BIN`。

PowerShell 示例：

```powershell
$env:PYTHON_BIN = "C:\path\to\python.exe"
npm start
```

启动后访问：

```text
http://localhost:3000/
http://localhost:3000/v2-database.html
http://localhost:3000/annotation-workbench.html
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
- 改动数据结构、API、部署方式或状态口径时，同步检查根 README、相关目录 README、`00-项目说明/08-规范事实表.md`、`09-当前状态与目标V2对照表.md` 和 `一致性检查.md`。
