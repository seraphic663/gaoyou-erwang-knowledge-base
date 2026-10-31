# 人工标注对结构切分评测的适用性盘点

本盘点只统计字段、状态、出处与边界元数据，没有摘录校勘答案。SQLite 均以 `mode=ro` 打开并设置 `PRAGMA query_only=ON`；未修改原文、数据库或旧评测文件。

## 当前来源与全量统计

`data/D-标注/03-案例Markdown/` 有 87 份案例 Markdown，旁边的 `manual_annotation_cases.annotation_case.v1.candidates.jsonl` 也有 87 条。两处都表明这是人工撰写来源：JSONL 的 `_migration.source_layer` 为 `manual_annotation_markdown`，转换方式为确定性 Markdown 解析。每条都有 `submitted_by`，但 `reviewed_by` 为空；迁移记录中的 `human_review.status` 87 条全为 `pending`，`machine_result.status` 87 条全为 `draft`。这里的 pending/draft 是迁移后的审核状态，不能用来否认原始案例由人撰写。

JSONL 的主要字段包括 `source_work`、`source_location`、`source_passage_id`、`target_work`、`target_location`、`target_passage_id`、`target_scope`、`evidences`、`term_relations`、`problem_discovery`、`evidence_collection`、`reasoning`、`conclusion`、`machine_result`、`human_review`、`submitted_by`、`reviewed_by` 和 `_migration`。`_migration.source_sections` 与 `source_section_spans` 各在 87 条中出现，86 条非空；其键是 `claim`、`conclusion`、`counter_argument`、`evidence_text`、`method_terms`、`process_text`、`source_argument`、`target_text` 等案例表单字段，表示案例 Markdown 内的字段跨度，不是原典的章、条、注释或序跋边界。

自动来源匹配在 79 条中生成了 `source_location`：59 条为条题精确匹配，9 条为条题含短语，8 条为父条上下文匹配，3 条为短语命中规范段落；另有 7 条未匹配、1 条歧义。8 条没有 `source_location`。87 条均无 `target_location` 和 `target_passage_id`。这些是迁移器给出的定位结果，没有人工复核状态。

当前遗留库 [annotations.db](D:/26大创/data/D-标注/05-数据库/annotations.db) 有 87 条案例、60 个来源文档。`annotation_cases` 字段覆盖来源文档、案例题名、来源/目标作品、目标文本、问题、主张、方法、结论、确定度、状态和原始 JSON；87 条全为 `status=草稿`、`certainty=待核`。另有 1,125 条证据、257 个过程步骤、154 个术语关系。证据行的角色说明均表明其引文由标注 Markdown 自动抽取，底本与版本尚未核验。来源文档全标为 `markdown_manual_annotation`，但 `full_json_file`、`ai_json_file` 及来源/段落/批注哈希字段在 60 条中均缺失。案例字段缺失为 `problem` 44 条、`claim` 8 条；证据字段缺失为 `work` 34 条、`term` 1,125 条。

遗留库的术语关系值为：`未定` 54、`训释` 35、`校勘` 27、`字际关系` 23、`虚词用法` 14、`句义解释` 1。这些类别表达的是词义、字际或校勘内容，并非文本结构关系。过程步骤 257 条分别为发疑 43、取证 43、立论 41、释理 43、结论 87。

v2 当前主库 [annotation_v2.db](D:/26大创/v2/data/real_runs/annotation_v2.db) 有 7,581 条案例：全部是 `lifecycle=machine_draft`、`machine_status=draft`、`human_status=pending`、`review_status=pending`；`review_events` 与 `five_step_audit_records` 均为 0。来源分布为遗留 AI JSON 重处理 17、旧词典库重处理 815、原文 AI 4、原文机器候选壳 6,745；主库没有 `manual_annotation_markdown` 来源。6,749 条自动抽取候选的 `candidate_status=approved` 只表示机器候选阶段通过，不能当作人工审核或 gold。

v2 的 `manual_annotation_ingress/manual_annotation_cases.annotation_case.v1.candidates.jsonl` 有 47 条；按 `case_id` 集合核对，这 47 条都包含在前述 87 条候选中，不应作为新增独立案例相加。它们仍全是 `human_review.status=pending`、`machine_result.status=draft`，且 `reviewed_by` 为空。87 条候选 JSONL 与遗留库各自的 ID 不相同，因此本盘点不声称逐条主键映射已经核实。

`data/D-标注/` 下有 3 份 DOCX、3 份 full JSON 和 3 份 AI JSON。full JSON 共记录 353 个段落、28 条 Word comment、26 个 annotation block；28 条 comment 均带段落锚点，26 个 block 均有起止段落。作者字段有两个不同取值，但数据没有明确的人类/AI分类字段，不能仅凭作者名确认身份。AI JSON 共 17 条，全部为 `status=草稿`，虽 `certainty=确定`，仍不是人工确认。`data/D-标注/json/人工标注/` 目前只有 README，没有独立标注数据文件。

## 对结构 gold 的判断

现有 87 条是有价值的人工撰写案例来源，但其字段和分类集中在校勘、训释、证据和词际关系。它们没有被标成章/条边界、底本与注文的结构关系，或序/跋边界；自动匹配到的 `section_title`、`entry_title` 和案例表单字段跨度不能替代这些标签。因此不适合作为本轮结构切分的直接 gold，也不能因系统审核状态为 pending 就把人工撰写来源抹掉。

3 份 DOCX 的 Word comment—段落锚点和 annotation block 段落范围，是一个更窄的候选信号：可以作为这些文件内部的批注定位/标注块候选，不足以代表原典章条、注释与正文关系或序跋边界。若未来用于结构任务，需要逐条对照原始 DOCX 和原典语境确认标注含义与范围。本轮把 87 条人工案例保留为后续考据/校勘参考候选，不把它们转成切分 gold。

## 主要来源路径

- 人工撰写案例：`data/D-标注/03-案例Markdown/*.md`
- 案例候选及迁移元数据：`data/D-标注/04-案例JSONL/manual_annotation_cases.annotation_case.v1.candidates.jsonl`
- 遗留人工 Markdown 案例库：`data/D-标注/05-数据库/annotations.db`
- v2 当前主库：`v2/data/real_runs/annotation_v2.db`
- v2 人工案例候选子集：`v2/data/real_runs/manual_annotation_ingress/manual_annotation_cases.annotation_case.v1.candidates.jsonl`
- DOCX/AI JSON/full JSON：`data/D-标注/` 与 `data/D-标注/json/{ai_json,full_json,人工标注}/`
