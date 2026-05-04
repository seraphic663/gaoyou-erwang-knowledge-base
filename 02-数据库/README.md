# 数据库目录说明

`02-数据库` 负责原始语料整理、结构化解析、SQLite 入库和后续同步到网站。当前主库是 `data/dictionary.db`，结构以 `database.py` 为准。

## 当前数据链路

```text
source.txt
  -> parser.py
  -> bulk_importer.py
  -> data/dictionary.db
  -> ../03-项目网站/scripts/sqlite_bridge.py
  -> ../03-项目网站/data/sqlite-snapshot.json
```

`bulk_importer.py` 已直接调用 `parser.py` 的解析结果，不再依赖 `parsed_data.py`。`parsed_data.py` 属于生成型中间文件，不应再提交进仓库。

## 文件职责

| 文件 | 职责 | 是否维护入口 |
| --- | --- | --- |
| `source.txt` | 原始语料输入 | 是 |
| `parser.py` | 解析原始语料，生成结构化记录 | 是 |
| `bulk_importer.py` | 批量导入 SQLite | 是 |
| `database.py` | 建表、索引、写入接口、查询接口 | 是 |
| `data/dictionary.db` | 当前 SQLite 主库 | 产物，不建议手工改 |
| `README.md` | 数据库维护说明 | 是 |

## 数据库结构

当前数据库以五张主表组织：

| 表 | 含义 |
| --- | --- |
| `works` | 著作来源表，保存被引用或讨论的典籍、著作信息 |
| `passages` | 文本片段表，保存可定位的原文或论述片段 |
| `terms` | 词条表，保存字、词、术语等检索对象 |
| `cases` | 考据案例表，保存完整考据单元 |
| `evidences` | 证据表，保存支撑案例结论的具体证据 |

全文检索表：

```text
terms_fts
passages_fts
evidences_fts
```

关系口径：

```text
works -> passages -> cases -> evidences
terms <-> cases
terms -> evidences
```

`terms` 是检索核心；`cases` 是考据单元；`evidences` 是证据层；`works` 和 `passages` 提供出处和文本定位。

## 常用命令

在仓库根目录运行：

```bash
python 02-数据库/bulk_importer.py --dry-run
python 02-数据库/bulk_importer.py
npm run sync:sqlite
```

说明：

- `--dry-run` 只解析和统计，不写入数据库。
- 正式运行 `bulk_importer.py` 会重建或更新 `data/dictionary.db`。
- `npm run sync:sqlite` 会把 SQLite 导出为网站读取的 `sqlite-snapshot.json`。

## 维护场景

### 只增加数据

1. 修改 `source.txt`。
2. 运行 `bulk_importer.py --dry-run`。
3. 确认 works、terms、cases、evidences 统计正常。
4. 运行 `bulk_importer.py`。
5. 运行 `npm run sync:sqlite`。

### 修改解析规则

1. 修改 `parser.py`。
2. 用 `--dry-run` 检查解析统计。
3. 如导入字段受影响，同步修改 `bulk_importer.py`。
4. 正式导入并同步网站快照。

### 修改数据库结构

至少检查四处：

```text
database.py
bulk_importer.py
../03-项目网站/scripts/sqlite_bridge.py
../03-项目网站/src/store-definitions.js
```

如果网站页面直接消费新字段，还要同步检查 `app.js`、`browser.js`、`detail.js`。

## 不应提交的内容

```text
parsed_data.py
data/dictionary.empty.db
data/*.db-journal
__pycache__/
*.pyc
```

这些文件要么是自动生成中间文件，要么是缓存和临时文件。它们不会提高可维护性，只会放大仓库并干扰 GitHub 语言统计。

## 当前扩展优先级

1. 补实 `passages`，让著作、原文片段、案例、证据链条更完整。
2. 规范 `terms` 与 `cases` 的多对多关系，后续可考虑独立关联表。
3. 再考虑版本层、关系层或知识图谱层。
