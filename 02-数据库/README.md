# 数据库与数据引擎

`02-数据库/` 现已作为仓库中的统一数据库目录，合并了原“研究方案”文档和原“数据加工区”脚本，不再承担主网站展示职责。

## 当前职责

- 保存《广雅疏证》原始语料：[source.txt](source.txt)
- 保存数据库设计说明：[数据库.md](数据库.md)
- 负责文本解析与结构化抽取：[parser2.py](parser2.py)
- 保存解析产物：[parsed_full.py](parsed_full.py)
- 负责批量导入 SQLite：[bulk_importer.py](bulk_importer.py)
- 定义最小必要版数据库与检索接口：[db2.py](db2.py)
- 保存当前主用 SQLite 实库：[dictionary.db](data2/dictionary.db)

## 与主网站的关系

主网站在 [../03-项目网站](../03-%E9%A1%B9%E7%9B%AE%E7%BD%91%E7%AB%99)。

网站默认读取的是由 SQLite 实库导出的统一快照：

- 输入：`02-数据库/data2/dictionary.db`
- 输出：`03-项目网站/data/sqlite-snapshot.json`

同步命令在仓库根目录执行：

```bash
npm run sync:sqlite
```

## 目录说明

- `数据库.md`：当前数据库设计与字段规范说明
- `data2/`：当前主用 SQLite 实库

## 说明

如果你只关心部署和网站展示，不需要直接运行本目录下的脚本。
如果你要更新语料、重跑解析、重建 SQLite，再回到本目录工作。
