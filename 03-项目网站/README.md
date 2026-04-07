# 高邮二王考据过程知识库构建及应用

这是一个围绕“高邮二王考据过程知识库构建及应用”搭建的研究整理原型。它的目标不是泛化为一般古籍平台，而是围绕“王氏四种”中的典型疑难，把单条考据案例、相关引证材料与判断过程组织成可检索、可复核、可比较的专题知识库。网站当前按申报书 `v4.2` 的口径收束为“研究问题优先、当前能力随后、代表性案例展开、试查入口跟进”的首页结构，并把“过程性知识”落到可直接观看的个案链条上。

## 0 基础启动教程

如果你是第一次接触这个项目，直接照着做即可：

### 第 1 步：确认安装了 Node.js

打开终端，输入：

```bash
node -v
npm -v
```

如果能看到版本号，说明环境已就绪；如果提示“不是内部或外部命令”，先安装 Node.js 18+。

### 第 2 步：打开项目根目录

请在 VS Code 中打开整个文件夹 `D:\26大创`，不要只双击打开 `index.html`。

### 第 3 步：启动网站

推荐两种方式，任选一种：

**方式 A：在根目录启动**

```bash
npm start
```

**方式 B：使用 VS Code 任务**

在 VS Code 里运行任务 `serve demo`，它会自动启动本地服务。

### 第 4 步：打开网站

启动成功后，在浏览器访问：

```text
http://localhost:3000
```

### 第 5 步：确认数据库正常

如果页面显示“数据库状态：已连接”，说明本地研究原型正常运行。

你也可以直接打开接口检查：

```text
http://localhost:3000/api/health
http://localhost:3000/api/bootstrap
```

## Railway 部署说明

如果要把这个研究原型 push 到 Railway 后直接可用，推荐直接部署整个仓库根目录；项目已准备好默认启动入口。

### 推荐方式：部署仓库根目录

- Railway 会读取根目录的 `package.json` 和 `railway.toml`
- 启动命令直接使用 `npm start`
- 服务会自动读取 Railway 注入的 `PORT` 环境变量

### 也可以部署子目录

- 以 `03-项目网站` 为工作目录
- 启动命令仍然是 `npm start`
- 默认数据文件位于当前目录的 `data/demo-db.json`

### 你最省事的做法

- 直接 push 到 GitHub
- Railway 连接这个仓库
- 不手动改启动命令
- 等待自动构建完成后直接访问公网地址

### 部署后检查

打开以下地址确认服务正常：

```text
/api/health
/api/bootstrap
```

如果 `health.ok=true`，说明 Railway 上的服务已经正常跑起来。

### 数据持久化建议

如果你需要数据库重启后继续保留，请在 Railway 中挂载一个 Volume，并设置：

- `RAILWAY_VOLUME_MOUNT_PATH`，或
- `DATA_DIR`

程序会优先把 `demo-db.json` 写入这些目录；如果没配，服务也会自动初始化，只是重启后数据可能重置。

## 现在做到什么程度

- 前端展示页：首页聚焦研究问题、当前能力、代表性案例与试查入口
- 二级详情页：支持字词整理详情页与考据案例详情页，适合答辩时逐条展开说明
- 二级结构页：集中展示数据库 5 表及字段说明
- 后端本地 API：提供数据库统计、案例检索、结构信息
- 统一数据源层：支持 `Demo JSON` 与 `SQLite 实库（02-数据库）`
- 可扩展架构：后续可以继续扩到更正式的 SQLite / MySQL / PostgreSQL 服务

## 工程架构

```text
26大创/
├─ 02-数据库/
│  ├─ 数据库.md
│  ├─ parser2.py / parsed_full.py / bulk_importer.py / db2.py
│  ├─ source.txt
│  └─ data2/
│     └─ dictionary.db
├─ 03-项目网站/
│  ├─ index.html / database.html / term.html / case.html
│  ├─ app.js / detail.js / styles.css
│  ├─ server.js
│  ├─ package.json
│  ├─ README.md
│  ├─ data/
│  │  ├─ demo-db.json
│  │  └─ sqlite-snapshot.json
│  └─ media/
```

### 数据库结构

当前网站后端已经改为“统一数据源接口”，默认优先接入由 SQLite 实库导出的统一快照：

- `02-数据库/data2/dictionary.db`：真实 SQLite 数据源
- `03-项目网站/data/sqlite-snapshot.json`：由 Python 脚本导出的统一快照
- `03-项目网站/data/demo-db.json`：回退用 Demo 数据源

无论底层来源是什么，网站 API 都按“5 表数据库”输出统一结构：

- `works`：著作来源表
- `passages`：文本片段表
- `terms`：词条与术语表
- `cases`：考释案例表
- `evidences`：证据表

这种结构已经能形成“著作 - 片段 - 词条 - 案例 - 证据”的最小闭环，原因在于它能较稳妥地承载单条考据所需的出处、引文、证据与结论关系：

- 数据有明确分层，便于扩展和维护
- 可以单独替换存储层，而不影响前端页面
- 能支持后续新增搜索、筛选、图谱、导出等能力

## 数据源切换

- 默认行为：若检测到 `03-项目网站/data/sqlite-snapshot.json`，网站优先使用 SQLite 快照
- 强制使用 demo：设置环境变量 `DATA_SOURCE=demo`
- 强制使用 SQLite：设置环境变量 `DATA_SOURCE=sqlite`

当 SQLite 数据更新后，执行一次：

```bash
python 03-项目网站/scripts/sqlite_bridge.py export
```

即可重新生成网站使用的统一快照。

## 接口

- `GET /api/bootstrap`：返回数据库统计、结构和示例数据
- `GET /api/schema`：返回表结构和记录数
- `GET /api/search?q=关键词`：同时返回匹配字词与相关案例
- `GET /api/cases?q=关键词`：按关键词检索案例
- `GET /api/term?id=编号`：返回单个字词的详情数据
- `GET /api/case?id=编号`：返回单个案例的详情数据
- `GET /api/terms`：返回词条表
- `GET /api/health`：服务健康检查（可用于联调）

## 运行方式

1. 安装 Node.js 18+。
2. 在仓库根目录 `D:\26大创` 打开终端。
3. 运行：

```bash
npm start
```

4. 打开浏览器访问：

```text
http://localhost:3000
```

## 常见问题

### 1. 页面显示“数据库连接失败”

通常是因为你直接双击打开了 HTML 文件，或者本地服务没有启动。请改为先运行 `npm start`，再访问 `http://localhost:3000`。

### 2. 提示端口 3000 被占用

说明本地已经有一个研究原型实例在运行。你可以直接打开 `http://localhost:3000`，或者先关闭旧进程再重启。

### 3. 网站打不开

请确认你访问的是 `http://localhost:3000`，不是 `file:///.../index.html`。

## 为什么我建议做到这个级别

对你的题目来说，最合适的是“轻量正式版”工程化：

- 比纯静态页面更像真实项目
- 比复杂的企业级系统更容易展示和维护
- 能支撑“数据库—接口—前端”完整闭环
- 后续如果要写立项书、答辩 PPT、项目中期检查，都更容易讲清楚

## 后续可继续升级的方向

- 把文件型数据库换成 SQLite
- 增加案例增删改接口
- 增加全文检索与标签过滤
- 增加古籍图文对照和知识图谱视图
- 增加管理员审核和标注工作流

## 说明

当前项目仍是研究原型阶段，但后端已经完成一次工程化重构：

- 静态页面与数据源适配分离
- Node 服务只负责 HTTP 与页面分发
- SQLite 读取通过 Python 标准库桥接完成
- 页面不再直接依赖某一种数据库格式
