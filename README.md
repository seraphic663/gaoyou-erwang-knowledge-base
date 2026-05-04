# 高邮二王考据过程知识库

本仓库是“高邮二王考据过程知识库构建及应用”的项目工作区，包含申报资料、数据库生成链路、网站展示原型、文献材料和组会记录。

线上地址：https://gaoyou-demo1.up.railway.app/

## 当前主链路

```text
02-数据库/source.txt
  -> 02-数据库/parser.py
  -> 02-数据库/bulk_importer.py
  -> 02-数据库/data/dictionary.db
  -> 03-项目网站/scripts/sqlite_bridge.py
  -> 03-项目网站/data/sqlite-snapshot.json
  -> 03-项目网站/
```

网站前台统一表述为“一个专题数据库，多种浏览视角”。字词、案例、证据、著作和文本片段不是多套数据库，而是同一 SQLite 主库的不同入口。

## 目录结构

```text
01-项目资料/      申报、通知、附件等项目管理材料
02-数据库/        原始语料、解析脚本、入库脚本、SQLite 主库
03-项目网站/      网站页面、前端脚本、Node 服务、网站数据快照
04-项目文献/      原典、一级资料、二级资料、当前阅读和标注稿
05-组会谈话/      组会记录、讨论纪要、设计来源
```

## 本地运行

需要 Node.js 18+。

```bash
npm start
```

启动后访问：

```text
http://localhost:3000
```

常用检查：

```text
http://localhost:3000/api/health
http://localhost:3000/api/bootstrap
```

## 常用维护命令

```bash
python 02-数据库/bulk_importer.py --dry-run
python 02-数据库/bulk_importer.py
npm run sync:sqlite
```

维护顺序：

1. 改原始语料或解析规则后，先运行 `bulk_importer.py --dry-run`。
2. 确认统计正常后运行 `bulk_importer.py` 重建 SQLite。
3. 数据库变化后运行 `npm run sync:sqlite` 更新网站快照。
4. 网站展示口径变化后，只更新必要 README 和短更新记录，不写流水账。

## 仓库维护原则

- 保留可重建链路：`source.txt`、`parser.py`、`bulk_importer.py`、`database.py`、`dictionary.db`、`sqlite-snapshot.json`。
- 不再提交生成型中间文件，例如 `parsed_data.py`、空库、SQLite journal。
- 大体量文献资料建议迁出 Git 或使用 Git LFS；仓库内优先保留清单、摘录和标注成果。
- `02-数据库` 中的 Python 脚本重新计入 GitHub 语言统计；它们体量很小，保留可解释数据库可重建性。
