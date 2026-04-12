# 26大创数据库说明

`02-数据库` 用于原始文本整理、结构化解析、SQLite 入库与后续扩展。当前主库是 `data/dictionary.db`，数据库结构以 `database.py` 为准。

## 第一部分：简要介绍

### 目录说明

- `source.txt`：原始语料文本（source text）。
- `parser.py`：文本解析脚本（parser）。
- `parsed_data.py`：解析后的中间数据（parsed output）。
- `bulk_importer.py`：批量导入脚本（bulk importer）。
- `database.py`：数据库结构与操作接口（database schema and access layer）。
- `data/dictionary.db`：SQLite 数据库文件（SQLite database file）。

### 数据库总体结构

当前数据库由五张主表和三张全文检索表组成。

### 主表（Core Tables）

- `works`：著作表（Works）
- `passages`：文本片段表（Passages）
- `terms`：词条表（Terms）
- `cases`：考据案例表（Cases）
- `evidences`：证据表（Evidences）

### 检索表（Full-Text Search Tables）

- `terms_fts`：词条全文检索表（Terms Full-Text Search）
- `passages_fts`：片段全文检索表（Passages Full-Text Search）
- `evidences_fts`：证据全文检索表（Evidences Full-Text Search）

### 各表字段说明

### 1. `works` 著作表（Works）

用途：保存被引用或被讨论的文献、著作与典籍信息。

| 字段名 | 英文说明 | 含义 |
| --- | --- | --- |
| `id` | primary key | 主键 |
| `title` | work title | 书名 |
| `author` | author | 作者或责任者 |
| `work_type` | work type | 著作类型 |
| `dynasty` | dynasty | 朝代 |
| `time_note` | time note | 时间说明 |
| `notes` | notes | 补充备注 |

`work_type` 当前可选值：

- `二王著作`：Erwang writings
- `原始经典`：source classics

### 2. `passages` 文本片段表（Passages）

用途：保存可定位的原文或论述片段，是著作和案例之间的文本层。

| 字段名 | 英文说明 | 含义 |
| --- | --- | --- |
| `id` | primary key | 主键 |
| `work_id` | work id | 所属著作编号，对应 `works.id` |
| `juan` | juan / fascicle | 卷次 |
| `chapter` | chapter / section | 篇章或类目 |
| `location_note` | location note | 更细的定位说明 |
| `raw_text` | raw text | 原始文本 |
| `normalized_text` | normalized text | 规范化文本 |
| `passage_type` | passage type | 片段类型 |

`passage_type` 当前可选值：

- `二王论述`：Erwang commentary
- `原始经典`：source classic passage

### 3. `terms` 词条表（Terms）

用途：保存数据库中的核心检索对象，即字、词、术语等词条。

| 字段名 | 英文说明 | 含义 |
| --- | --- | --- |
| `id` | primary key | 主键 |
| `term` | term entry | 词条本体 |
| `term_type` | term type | 词条类型 |
| `category` | category | 分类 |
| `aliases` | aliases | 别名，当前以 JSON 文本保存 |
| `notes` | notes | 备注 |
| `core_meaning` | core meaning | 核心释义 |
| `case_ids` | related case ids | 关联案例编号，当前以 JSON 文本保存 |

`term_type` 当前可选值：

- `术语`：technical term
- `词`：word
- `字`：character

### 4. `cases` 考据案例表（Cases）

用途：保存完整的考据单元，一条记录对应一则案例。

| 字段名 | 英文说明 | 含义 |
| --- | --- | --- |
| `id` | primary key | 主键 |
| `title` | case title | 案例标题 |
| `section_title` | section title | 所属章节或条目标题 |
| `volume_title` | volume title | 卷册标题 |
| `term_ids` | related term ids | 关联词条编号，当前以 JSON 文本保存 |
| `erwang_passage_id` | Erwang passage id | 对应二王论述片段 |
| `target_passage_id` | target passage id | 对应被解释的原文片段 |
| `problem` | research problem | 所讨论的问题 |
| `method` | method | 所用方法 |
| `process_text` | analysis process | 考据过程 |
| `conclusion` | conclusion | 结论 |
| `certainty` | certainty level | 结论确定性 |
| `status` | review status | 数据状态 |

`certainty` 当前可选值：

- `确定`：confirmed
- `可疑`：uncertain
- `待核`：pending verification

`status` 当前可选值：

- `草稿`：draft
- `已校对`：proofread
- `已审核`：reviewed

### 5. `evidences` 证据表（Evidences）

用途：保存支撑案例结论的具体证据，是案例分析的依据层。

| 字段名 | 英文说明 | 含义 |
| --- | --- | --- |
| `id` | primary key | 主键 |
| `case_id` | case id | 所属案例编号，对应 `cases.id` |
| `term_id` | term id | 所属词条编号，对应 `terms.id` |
| `source_passage_id` | source passage id | 证据来源片段编号，对应 `passages.id` |
| `work_id` | work id | 证据所属著作编号，对应 `works.id` |
| `evidence_type` | evidence type | 证据类型 |
| `quote_text` | quoted text | 引文原文 |
| `core_snippet` | core snippet | 核心引句 |
| `note` | note | 证据说明 |

`evidence_type` 当前可选值：

- `书证`：documentary evidence
- `声训`：phonological evidence
- `义证`：semantic evidence
- `形证`：graphic evidence
- `语法证据`：grammatical evidence
- `异文`：variant reading

### 数据类别与关系

从数据组织上看，当前数据库包含五类核心数据（data categories）：

- 著作数据（works data）：保存文献来源。
- 片段数据（passage data）：保存可定位的原文片段。
- 词条数据（term data）：保存字、词、术语等检索对象。
- 案例数据（case data）：保存完整考据过程。
- 证据数据（evidence data）：保存支撑案例的具体论据。

它们的关系如下：

- `works` -> `passages`：一部著作可以包含多条文本片段。
- `passages` -> `cases`：案例可以关联二王论述片段和目标原文片段。
- `terms` <-> `cases`：当前通过 `term_ids` 与 `case_ids` 以 JSON 形式维护多对多关系。
- `cases` -> `evidences`：一个案例可以对应多条证据。
- `terms` -> `evidences`：一条证据可以直接归属到某个词条。

这套结构形成了基本链条：

`works -> passages -> cases -> evidences`

同时，`terms` 作为检索核心，横向连接 `cases` 和 `evidences`。

## 第二部分：AI 维护与扩展说明

这一部分面向后续接手本目录的 AI 或开发者。目标不是解释概念，而是说明下一步该改哪里、按什么顺序改、哪些地方必须同步。

### 一、先看什么

如果要继续维护本目录，默认按下面顺序阅读：

1. `02-数据库/README.md`
2. `02-数据库/database.py`
3. `02-数据库/parser.py`
4. `02-数据库/bulk_importer.py`
5. `02-数据库/parsed_data.py`
6. `03-项目网站/scripts/sqlite_bridge.py`

这样可以先理解数据库结构，再理解数据如何生成、如何入库，以及最后如何同步到网站。

### 二、数据流是什么

当前真实数据流如下：

`source.txt -> parser.py -> parsed_data.py -> bulk_importer.py -> data/dictionary.db -> 03-项目网站/scripts/sqlite_bridge.py -> 03-项目网站/data/sqlite-snapshot.json`

含义如下：

- `source.txt`：原始文本输入。
- `parser.py`：把原始文本拆成结构化数据。
- `parsed_data.py`：保存解析后的中间结果。
- `bulk_importer.py`：把中间结果批量导入 SQLite。
- `data/dictionary.db`：主数据库。
- `sqlite_bridge.py`：把 SQLite 导出成网站使用的 JSON 快照。
- `sqlite-snapshot.json`：网站优先读取的实际数据文件。

结论：如果只改了 SQLite 而没有重新导出快照，网站看到的仍然可能是旧数据。

### 三、每个文件的维护职责

- `database.py`
  负责建表、字段定义、数据写入接口、查询接口和 FTS 检索。
  只要改数据库结构，优先改这里。

- `parser.py`
  负责把 `source.txt` 解析成结构化结果。
  只要原始文本格式变了，或想增加解析出的数据项，就改这里。

- `parsed_data.py`
  是解析结果文件，不应手工大改，原则上由 `parser.py` 重新生成。

- `bulk_importer.py`
  负责把 `parsed_data.py` 中的结构化数据导入 `dictionary.db`。
  只要解析结果结构变了，或数据库新增字段需要写入，就改这里。

- `data/dictionary.db`
  是产物文件，不是维护入口。
  一般通过脚本重建或更新，不建议手工直接修改。

- `03-项目网站/scripts/sqlite_bridge.py`
  负责把 SQLite 规范化导出为网站快照。
  只要数据库表结构、字段名或输出结构改了，这里通常也要同步改。

### 四、常见维护任务怎么做

#### 1. 新增数据，但不改表结构

适用场景：只增加词条、案例、证据、著作或片段，不新增字段。

操作顺序：

1. 更新 `source.txt` 或其他原始材料。
2. 运行 `parser.py` 生成新的结构化结果。
3. 检查 `parsed_data.py` 是否符合预期。
4. 运行 `bulk_importer.py` 写入 `data/dictionary.db`。
5. 在仓库根目录执行 `npm run sync:sqlite`，导出 `03-项目网站/data/sqlite-snapshot.json`。

关键点：这类任务通常不需要改 `database.py`，但必须重新同步网站快照。

#### 2. 新增字段

适用场景：现有表不够用，需要增加新的数据元素。

必须同步修改的地方：

1. `database.py`
   在对应 `CREATE TABLE` 语句中新增字段。

2. `bulk_importer.py`
   把新字段写入数据库。

3. `parser.py`
   如果新字段来自原始文本解析，则要在解析阶段生成该字段。

4. `parsed_data.py`
   通过重新运行解析脚本生成，不建议手工补。

5. `03-项目网站/scripts/sqlite_bridge.py`
   如果网站要读取该字段，导出逻辑必须同步更新。

关键点：新增字段不是只改 schema。至少要检查“解析层、导入层、导出层”三处是否一致。

#### 3. 新增表

适用场景：现有五表不足以表达新的数据类型。

必须同步修改的地方：

1. `database.py`
   新建表、约束、索引和必要接口。

2. `bulk_importer.py`
   增加对新表的写入逻辑。

3. `parser.py`
   如果新表数据来自原始文本解析，需新增对应输出。

4. `03-项目网站/scripts/sqlite_bridge.py`
   如果网站需要展示新表，需将其加入快照导出。

5. 网站侧 schema 或数据说明文件
   当前应重点检查 `03-项目网站/src/store-definitions.js` 等依赖五表定义的文件。

关键点：新增表属于结构级改动，不能只停在 `02-数据库` 目录内部。

#### 4. 修改字段名或字段含义

这是高风险操作，默认视为全链路修改。

必须检查：

1. `database.py` 中的 schema 和查询函数
2. `bulk_importer.py` 中的导入字段映射
3. `sqlite_bridge.py` 中的导出字段映射
4. 网站端是否直接消费该字段
5. README 中对应字段说明是否需要同步更新

关键点：改字段名最容易引起静默错误，即数据库已更新，但网站仍按旧字段读取。

### 五、推荐命令入口

常用命令如下：

```bash
python 02-数据库/parser.py --output 02-数据库/parsed_data.py
python 02-数据库/bulk_importer.py --dry-run
python 02-数据库/bulk_importer.py
npm run sync:sqlite
```

说明：

- `parser.py --output`：重新生成结构化中间结果。
- `bulk_importer.py --dry-run`：只看统计，不写库，适合先检查。
- `bulk_importer.py`：正式导入数据库。
- `npm run sync:sqlite`：把 SQLite 同步为网站快照。

### 六、默认维护规则

后续 AI 或开发者在维护本目录时，默认遵守以下规则：

1. 不直接手工编辑 `data/dictionary.db`，优先通过脚本生成或更新。
2. 不把 `parsed_data.py` 当作长期手写文件，优先由 `parser.py` 重新生成。
3. 只要 SQLite 数据变化，就重新执行一次 `npm run sync:sqlite`。
4. 只要数据库结构变化，就检查 `database.py`、`bulk_importer.py`、`sqlite_bridge.py` 是否已经同步。
5. 如果网站需要消费新字段或新表，就同步检查网站侧定义文件，而不是只改数据库。
6. 修改 README 时，以当前代码和真实数据流为准，不用早期方案稿替代现状。

### 七、后续扩展优先级

如果下一步要继续建设数据库，推荐优先级如下：

1. 补实 `passages`，让著作、原文片段、案例、证据的链条更完整。
2. 规范 `terms` 与 `cases` 的多对多关系，后续可考虑改为独立关联表。
3. 再考虑更复杂的版本层、关系层或知识图谱层。

简化判断标准如下：

- 如果目标是“加数据”，主要动 `parser.py`、`parsed_data.py`、`bulk_importer.py`。
- 如果目标是“改结构”，主要动 `database.py`，并同步检查导入和导出链路。
- 如果目标是“让网站看到新结果”，最后一定执行 `npm run sync:sqlite`。
