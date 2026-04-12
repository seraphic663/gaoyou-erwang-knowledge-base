# 高邮二王知识库（项目总览）

本仓库采用“申报、数据库、网站、参考”分层结构，便于申报、数据加工、网站展示与答辩并行推进。

## 根目录文件说明（是否冗余）

根目录保留这 4 个文件是有用途的，不建议再下沉到子目录：

- `package.json`：仓库级启动入口（`npm start`），给本地与 Railway 统一命令。
- `server.js`：兼容入口，转发到 `03-项目网站/server.js`，避免部署路径差异。
- `railway.toml`：Railway 部署配置默认读取根目录。
- `README.md`：仓库首页说明，便于团队成员和评审快速了解项目。

已清理冗余：`Intro.md`（空文件）已删除。

## 目录结构

- `01-项目申报`：提交版申报稿、核心提炼稿与申报相关组会参考稿
- `02-数据库`：数据库设计文档、原始语料、解析脚本与 SQLite 实库
- `03-项目网站`：当前对外网站与 Railway 部署入口
- `04-参考资料`：学校通知、指南与相关附件
- `05-项目文献`：文献目录说明（原件不上 Git）
- `06-组会谈话`：组会纪要与原始草稿
- `03-项目网站/data`：网站运行所需的数据快照与回退数据
- `03-项目网站/media`：页面资源

## 网站启动

在仓库根目录执行：

```bash
npm start
```

然后访问：

http://localhost:3000

## SQLite 实库同步

网站现在默认优先读取 `03-项目网站/data/sqlite-snapshot.json`。

如果你更新了 `02-数据库/data/dictionary.db`，在仓库根目录执行：

```bash
npm run sync:sqlite
```

这会把 SQLite 实库重新导出为网站可直接读取的统一快照。Railway 部署时不需要运行 Python，只需要仓库里已经包含这个快照文件即可。

数据加工区的当前说明见 [02-数据库/README.md](02-%E6%95%B0%E6%8D%AE%E5%BA%93/README.md)。

## Railway 部署

如果你把这个仓库 push 到 Railway，通常可以直接用，不需要额外改太多配置：

1. 在 Railway 新建项目并连接这个 Git 仓库。
2. 保持默认的 Node 部署方式即可，平台会自动读取根目录 `package.json` 和 `railway.toml`。
3. 启动命令已经固定为：

```bash
npm start
```

4. 不需要手动配置端口，`server.js` 会自动使用 Railway 提供的 `PORT` 环境变量。

5. 部署完成后，访问 Railway 分配的公开域名即可。

### 当前默认数据来源

- 优先：`03-项目网站/data/sqlite-snapshot.json`
- 回退：`03-项目网站/data/demo-db.json`

因此，只要你在 push 前执行过一次 `npm run sync:sqlite`，Railway 上就是“直接可用”的，不依赖 Railway 容器里再装 Python 或再读本地 SQLite。

### 数据持久化建议

如果你希望数据库在 Railway 重启后仍然保留，建议再给服务挂一个 Volume，并设置其中一个环境变量：

- `RAILWAY_VOLUME_MOUNT_PATH`：Railway 挂载卷的路径
- `DATA_DIR`：你手动指定的数据目录

服务会优先使用这些目录保存 `demo-db.json`，没有设置时也会自动初始化本地数据库文件。

### 一句话结论

把仓库 push 到 Railway 后，默认就能启动；如果你已经同步好 SQLite 快照，线上会直接读取实库导出的数据。

## 05 文件夹太大时怎么处理（推荐）

已采用“仓库不传原件、云盘存原件”的策略：

1. Git 忽略 `05-项目文献` 下的大文件（pdf/docx 等）。
2. 仓库仅保留 [05-项目文献/README.md](05-%E9%A1%B9%E7%9B%AE%E6%96%87%E7%8C%AE/README.md) 记录云链接。
3. 以后自动 `git add .` 时，不会把 05 里的原件加入版本库。

如果你之前已经把 05 中的大文件提交过，需要再执行一次“从索引移除但保留本地文件”（不影响你电脑里的文件）：

- `git rm -r --cached 05-项目文献`
- `git add .gitignore 05-项目文献/README.md`
- `git commit -m "chore: ignore large literature files"`

## 可靠性说明（已加固）

- 网站可自动适配当前目录结构读取数据
- 增加 `/api/health` 健康检查接口
- 增加静态文件路径安全校验，避免越界访问
- 数据文件损坏时自动备份并重建种子数据

## 本轮整理结果

- 已将数据库设计文档与数据加工脚本收口到 `02-数据库/`
- 已将旧 Flask 界面、旧样例脚本与旧数据库移出当前主链路
- 当前主链路明确为：
  `02-数据库/data/dictionary.db` -> `npm run sync:sqlite` -> `03-项目网站/data/sqlite-snapshot.json` -> `npm start`
