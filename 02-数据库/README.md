# 数据库目录说明

`02-数据库` 是项目的数据层，包含两个独立 SQLite 数据库、各自的生成管线，以及共享工具层。

## 目录结构

```text
02-数据库/
  ├── lib/                       共享 SQLite 工具（连接、查询、快照导出）
  │   ├── __init__.py
  │   ├── connection.py
  │   └── snapshot.py
  ├── main/                      主库管线（《广雅疏证》语料 → dictionary.db）
  │   ├── source.txt             原始语料输入
  │   ├── parser.py              解析脚本
  │   ├── schema.sql             主库 DDL（参考）
  │   ├── database.py            主库 CRUD 接口
  │   └── importer.py            批量导入编排（原 bulk_importer.py）
  ├── annotation/                标注库管线（DOCX 标注 → annotations.db）
  │   ├── schema.sql             标注库 DDL（参考）
  │   └── importer.py            标注库建表与查询接口
  ├── data/                      两个 SQLite 数据库产物
  │   ├── dictionary.db          主库（已校对，面向公众）
  │   └── annotations.db         标注库（草稿/待核，内部研究用）
  └── README.md
```

## 两个数据库的关系

| | dictionary.db（主库） | annotations.db（标注库） |
|---|---|---|
| 数据来源 | 《广雅疏证》source.txt，旧 parser/importer 机器解析；不是 DeepSeek 输出 | DOCX 抽取 + DeepSeek 规范化 AI 工作稿 |
| 数据量 | 49 著作 · 3,385 词条 · 815 案例 · 7,120 证据 | 3 文档 · 44 词条 · 17 案例 · 121 证据 · 64 过程步骤 |
| 成熟度 | 旧字段显示 `草稿`/`确定`，但按 V2 只能视为机器结构化材料 | 草稿/待核 |
| 重建策略 | 全量重建（从 source.txt） | 增量追加（从 run.py） |
| 网站入口 | 首页、database.html、term.html、case.html | annotation.html（人工库浏览）+ ai-annotation.html（AI 释证） |
| 核心表 | works, passages, terms, cases, evidences | source_documents, annotation_cases, annotation_terms, annotation_evidences, annotation_process_steps |

两个库物理独立，架构统一：共享 `lib/` 工具层，产物统一放在 `data/`。

## 主库数据链路

```text
main/source.txt
  -> main/parser.py
  -> main/importer.py
  -> data/dictionary.db
  -> ../03-项目网站/scripts/sqlite_bridge.py
  -> ../03-项目网站/data/sqlite-snapshot.json
```

## 标注库数据链路

```text
../04-项目文献/D-标注/ 的 DOCX 文件
  -> ../04-项目文献/D-标注/json/run.py
  -> data/annotations.db
  -> ../03-项目网站/scripts/annotation_bridge.py
  -> ../03-项目网站/data/annotation-snapshot.json
```

## 常用命令

在仓库根目录运行：

```bash
# 主库
python 02-数据库/main/importer.py --dry-run
python 02-数据库/main/importer.py
npm run sync:sqlite

# 标注库（需先 cd 到 run.py 目录）
cd 04-项目文献/D-标注/json
python run.py --api --import-ai
cd ../../..
npm run sync:annotation
```

说明：

- `--dry-run` 只解析和统计，不写入数据库。
- 正式运行 `importer.py` 会重建或更新 `data/dictionary.db`。
- `npm run sync:sqlite` 把主库导出为网站 JSON 快照。
- `npm run sync:annotation` 把标注库导出为网站 JSON 快照。
- 如需进入 V2 工作库，使用 `python v2/scripts/run_legacy_machine_conversion.py` 转换主库机器材料；不得把主库旧字段 `确定` 解释为 V2 人工 gold。

## 维护场景

### 只增加主库数据

1. 修改 `main/source.txt`。
2. 运行 `importer.py --dry-run`。
3. 确认 works、terms、cases、evidences 统计正常。
4. 运行 `importer.py`。
5. 运行 `npm run sync:sqlite`。

### 修改主库解析规则

1. 修改 `main/parser.py`。
2. 用 `--dry-run` 检查解析统计。
3. 如导入字段受影响，同步修改 `main/importer.py` 和 `main/database.py`。
4. 正式导入并同步网站快照。

### 修改数据库结构

至少检查五处：

```text
main/database.py        — Schema DDL、CRUD 函数
main/schema.sql         — DDL 参考文件
../../03-项目网站/scripts/sqlite_bridge.py
../../03-项目网站/src/store-definitions.js
../../03-项目网站/src/data-sources/shared.js
```

如果网站页面直接消费新字段，还要同步检查 `app.js`、`browser.js`、`detail.js`。

### 增加标注数据

1. 将标注后的 DOCX 放入 `04-项目文献/D-标注/`。
2. 在 `D-标注/json/` 下运行 `python run.py --api --import-ai`。
3. 在仓库根目录运行 `npm run sync:annotation`。

## 不应提交的内容

```text
parsed_data.py
data/dictionary.empty.db
data/*.db-journal
__pycache__/
*.pyc
~$*.docx
```

这些文件要么是自动生成中间文件，要么是缓存和临时文件。

## 当前扩展优先级

1. 补实 `passages`，让著作、原文片段、案例、证据链条更完整。
2. 规范 `terms` 与 `cases` 的多对多关系，后续可考虑独立关联表。
3. 标注库中审核通过的案例，考虑迁移到主库（作为新的 source 渠道）。
4. 再考虑版本层、关系层或知识图谱层。
