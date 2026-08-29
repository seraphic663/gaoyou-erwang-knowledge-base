# V2 下一步架构问题研究提纲（草稿）

> 研究日期：2026-08-12。本文只使用项目内指定的一手资料：`v2/schemas/annotation_v2.sql`、`v2/src`、`v2/scripts`、`v2/data/real_runs` 中的运行报告/清单，以及 `02-数据库/schema.sql` 与 `02-数据库/README.md`。本文是只读架构研究；不把机器校验、字符串命中或旧字段状态解释为人工学术结论。

> 研究后的自动化落地（同日）：已新增 `work_registry`/`work_aliases` 身份层；已生成 6,749 条候选的 `candidate_materialization_plan.candidate_shell.v1.jsonl`；并实际物化 `original-candidates-0001` 的 100 条 candidate shell。随后生成了 target_work、external edition/passage、human review 三类队列。以上步骤均不做学术语义消歧、不把公开转录升级为 canonical、不改变生产库人工状态。

## 一、先给结论

当前 V2 的机器侧入口已经成立，但“候选”“案例草稿”“外部底本”“人工 gold”四个层次仍必须继续隔离：6 个 `source_documents`、15,467 个 `passages`、6,749 个 `candidate_items`、936 个 `annotation_cases`、7,345 条 `annotation_evidences` 已进入同一个 V2 工作库；936 条案例全部是 `machine_status=draft`、`human_status=pending`，`gold=0`，`review_events=0`，数据库完整性、队列外键和孤儿引用检查通过。证据：`v2/data/real_runs/candidate_shell_batch_0001_report.json`、`v2/data/real_runs/work_queues_report.json`、`v2/data/real_runs/v2_validation_report.json`。

最重要的架构判断是：6,749 不是 6,749 条已形成学术结论的案例，而是四部王氏原典经过规则抽取和引用完整性审计后的候选入口。`candidate_status=approved` 只表示候选拥有有效 passage、文本非空且审计器未报结构错误；`candidate_auditor.py` 没有做语义判断，`original_candidate_adapter.py` 也明确要求目标典籍不明时留空、外部引文不补造。证据：`v2/src/erwang_v2/candidate_auditor.py:6-29`、`v2/src/erwang_v2/original_candidate_adapter.py:161-323`。

下一步应以四个可验收的门推进：候选到案例的可追溯批量物化门、著作身份规范化门、外部底本/版本/passage 核验门、人工审校与 gold 晋级门。任何一门未通过，都只能保留为机器草稿或 pending，不能写入 gold、主库或对外“已考证”展示。

## 二、当前基线与资料边界

| 层 | 当前数量/状态 | 已经做成的事实 | 主要缺口 |
|---|---:|---|---|
| 王氏原典输入 | 4 个 canonical-active source document；7,532 个 canonical passages | `source_version_registry` 记录活动 hash；《读书杂志》旧 hash 被标为 `historical_superseded` | 尚无外部典籍的 canonical edition/passages |
| 原典候选 | 6,749 个；四部合计 `audited_count=6,749`，审计状态全为 `approved` | 每条有 `candidate_id`、`passage_id`、rule hits、risk flags、来源文件/hash 和位置；第一批 100 条已物化为 candidate shell | 只有 4 条 `original_markdown_ai` 语义样例；剩余候选仍需按批次选择，不能视为学术案例 |
| V2 案例 | 936 个：17 条旧 AI + 815 条旧 dictionary.db + 4 条原典 AI 样例 + 100 条 candidate shell | 已统一成 `annotation_case.v1` 并进入同一物理工作库 | 全部仍是 machine draft/human pending；不能当 gold |
| 证据 | 7,345 条：104 canonical source-context passed、41 secondary citation、80 external pending、7,120 legacy-derived | quote/hash/外键边界已有校验；100 条 shell quote 标为 `context_only` | canonical source-context 通过不等于语义证据或学术结论通过 |
| 外部来源 | 100 个 registry：99 `pending`、1 `registered`；canonical file registered=0 | 已有 `external_source_registry`、证据关联表和公开转录候选清单 | edition、图像/底本核验、canonical passage 尚未落地 |
| 人工审校 | `review_events=0`、`gold=0` | 已有 `apply_review_event()` 事务边界、幂等 operation ID、approval gate 和 review queue 快照 | 尚未执行真实人工事件；UI 仍是只读，需后续接受控 review command |

四部原典候选分布为：`读书杂志` 4,309（1,836 parsed + 2,473 risk-bearing candidate）、`广雅疏证` 397（89 + 308）、`经传释词` 149（97 + 52）、`经义述闻` 1,894（549 + 1,345），合计 6,749。这里的 `candidate_count` 若只看报告中的高风险层会漏掉 `parsed_items`，应以 `audited_count`/全量 JSONL 作为下一步批处理输入。证据：`v2/data/real_runs/unified_ingress_report.json:250-314`。

旧 `02-数据库` 仍是独立的 SQLite 数据层：旧主库有 49 著作、3,385 词条、815 案例、7,120 证据但 `passages=0`；旧标注库是草稿/待核材料。README 已规定通过 `run_legacy_machine_conversion.py` 进入 V2，且不得把旧字段“确定”解释成 V2 人工 gold。证据：`02-数据库/README.md:28-39`、`02-数据库/README.md:79-85`、`v2/data/real_runs/legacy_machine_conversion_report.json`。

## 三、问题 1：6,749 个 candidate_item 如何批量进入 `annotation_case.v1`

### 3.1 已完成

`candidate_items` 已经是独立于 `annotation_cases` 的机器候选层：表中强制保留 `candidate_id`、`source_document_id`、`passage_id`、`work_key`、`source_work`、候选文本、规则命中、风险标志、候选状态、来源和 `provenance_json`，并通过 `output_case_id` 可回指案例。数据库层的 `ingest_candidate_items()` 是幂等 upsert；统一入口把四部原典的全量 6,749 条写入 `original_text_candidate_items.candidate_item.v1.jsonl` 和工作库。证据：`v2/schemas/annotation_v2.sql:95-119`、`v2/src/erwang_v2/database.py:277-332`、`v2/data/real_runs/unified_ingress_report.json:310-315`。

研究后的确定性计划已生成：6,749 条中 4 条已有 `output_case_id`，6,745 条为 `ready_candidate_shell`，没有缺失 passage/source document 的阻塞项；按每批 100 条为 68 批。第一批 `original-candidates-0001` 已物化 100 条，当前剩余 6,645 条。计划和物化均保留 `planned_case_id=candidate-shell:<candidate_id>`、source passage/hash、规则命中和风险标志；候选壳不生成语义结论，也不改变人工状态。证据：`v2/data/real_runs/candidate_materialization_plan_report.json`、`v2/data/real_runs/candidate_shell_batch_0001_report.json`。

第一批已经按该计划物化：`original-candidates-0001` 100/100 条进入 `annotation_cases`，所有案例的 `origin=original_markdown_candidate_shell`、`machine_status=draft`、`human_status=pending`、`lifecycle=machine_draft`，并通过 `candidate_items.output_case_id` 回链；没有 AI 调用、target_work 解析或 gold 晋级。100 条 source context quote 均有 canonical passage 绑定并可做字符串和字符偏移校验，但其 `semantic_role=context_only`，不表示学术证据或结论。证据：`v2/data/real_runs/candidate_shell_batch_0001_report.json`、`v2/data/real_runs/candidate_shell_batch_0001.annotation_case.v1.jsonl`。

当前只有每部原典 1 条代表候选调用 AI；本轮另将第一批 100 条确定性 materialization 为 candidate shell，但没有把它们当作 AI 语义案例。当前剩余 6,645 条候选仍只在 candidate layer；因此不是 6,749 条学术案例，而是 4 条原典 AI 草稿 + 100 条结构候选壳 + 其余候选队列。证据：`v2/data/real_runs/unified_ingress_report.json`、`v2/data/real_runs/candidate_shell_batch_0001_report.json`。

### 3.2 推荐的批量路线

建议采用“两阶段物化”，不要直接执行“6749 candidates = 6749 conclusions”。第一阶段对每条候选做确定性 materialization：以 `candidate_id` 作为幂等键，复制其 `source_passage_id/source_location/candidate_text/rule_hits/risk_flags`，生成一个标明 `record_kind=candidate_shell` 的 `annotation_case.v1` 机器草稿；`target_work=""`、`target_scope.status="unresolved"`、`relation_type="未定"`，证据只挂当前候选所在 canonical passage 的连续文本或保持空，结论只能是“机器结构草稿，待人工审校”，不能是研究结论。第二阶段才对通过人工/规则分层的候选调用 AI 或人工填写语义字段，并仍保持 `machine_status=draft` 直到验证完成。

如果不希望产生 6,749 个空壳案例，则保持 `candidate_items` 为队列，只为进入审校批次的候选生成案例；但必须把“候选是否已分批、为何未生成案例、下一次批次”记录在候选 provenance 或批次表中。两种路线都不能删除候选，也不能用 `candidate_status=approved` 代替 `human_status=approved`。

候选壳已经把 `record_kind`、`batch_id`、`materialization_policy`、`candidate_id`、`materialized_at` 和 AI/human boundary 写入 `machine_result_json`/`case_json._migration`；后续若需要更高查询性能，再把这些字段提升为显式列，但不能退回到只靠 `origin` 或 `case_title` 区分。

### 3.3 验收门 CAND-1

1. 全量输入只能来自 `original_text_candidate_items.candidate_item.v1.jsonl`，6,749 个 `candidate_id` 一一覆盖，重复运行不增加重复案例。
2. 每个物化案例必须能沿 `candidate_items.output_case_id -> annotation_cases.source_passage_id -> passages -> source_documents` 回溯，孤儿数为 0；候选文本和所引用 quote 必须能回到同一 passage。
3. 批量产物中 `machine_status` 只能是 `draft`/`rejected`，`human_status` 必须是 `pending`；不能因结构校验通过而出现 `gold` 或 `human approved`。
4. 统计必须同时报告“候选数、壳案例数、AI 生成数、人工选择数、拒绝数”，不能只报告一个“案例总数”。
5. 任意一条候选的 raw candidate、原始 passage/hash、规则命中、风险标志和生成模型/prompt 版本都可重放；缺失任一 provenance 时，该条只能留在候选队列。

## 四、问题 2：`source_work`、`target_work`、著作身份规范化并保留 raw provenance

### 4.1 当前做法与已完成边界

四部王氏原典的 `work_key` 来自 canonical passage/source document，可作为稳定的机器入口身份；`source_work` 仍是展示/输入标签。`database.py` 的 `_normalize_work_label()` 目前只做 NFKC、去《》和空白压缩；`target_inference.py` 只从显式 evidence 的 `source_work` 标签拆分出候选，并把状态设为 `machine_inferred/candidate_only`，不把候选当 resolved。证据：`v2/src/erwang_v2/database.py:32-35`、`v2/src/erwang_v2/target_inference.py:33-87`。

当前 936 个案例中只有 4 个 `target_work` 已填；新增 100 条 candidate shell 后，验证报告的 `pending_target_work_count=932`，而 17 条旧 AI 案例中有 12 条是 machine-inferred target scope、1 条 unresolved、4 条 resolved。现有 `target_passage_id` 的 815 条 legacy 链接是可追溯的 derived passage，不是目标典籍 canonical passage。证据：`v2/data/real_runs/v2_validation_report.json`、`v2/data/real_runs/batch_migration_report.json`。

### 4.2 推荐的身份模型

应把“著作身份”和“某次引用/某个版本”分开。建议增加一个 V2 `work_registry`（或等价的显式注册层）：`work_key` 为不可变内部 ID，`canonical_title` 为规范显示名，另有 author、dynasty、work_type、status；另建 alias/label mapping 保存每次观测到的 raw label、规范化结果、映射方法、confidence、reviewer 和时间。`external_source_registry` 应引用 `work_key`，而不是把 `normalized_work` 同时当作著作身份和来源版本身份。

字段边界建议如下：`source_work`/`target_work` 只放已经通过 registry 解析的 canonical display/key；原始输入放 `case_json._migration.raw_source_work`、`raw_target_work`，证据放 `evidence_json.raw_cited_work`，并保留 source file、record/evidence index、原始字符串和 hash。当前 `case_json`/`evidence_json` 能容纳这些内容，但 schema 没有强制要求，`external_source_registry.cited_work` 在 upsert 时还可能被后来的标签覆盖，因此需要显式的 alias/mapping 记录而不应只依赖最后一次 raw 值。

已先落地 `work_registry`/`work_aliases`：四部 canonical work key、旧派生 source、旧目录著作和 external pending identity 分开登记，raw label、mapping method、confidence、source record 均保留；这一步不替换现有案例的 raw/source/target 字段，也不把 candidate 映射升级为 resolved。证据：`v2/data/real_runs/work_registry_report.json`、`v2/schemas/annotation_v2.sql`。

规范化只做可逆的格式处理：NFKC、外层书名号和空白；简繁、异体、篇名、省称、注本/传本不能静默合并。公开来源脚本中的小型简繁映射已经被注释为“只用于跨脚本查找，不是语义等价”，这条边界应推广到 work registry。证据：`v2/scripts/fetch_external_public_candidates.py:37-42`、`v2/scripts/fetch_external_public_candidates.py:67-70`。

### 4.3 验收门 WORK-1

1. 每条案例/evidence 同时具备 raw label 和 canonical mapping；没有 mapping 的 target 继续为 unresolved/machine_inferred，不允许写入一个猜测的 `target_work`。
2. 同一 canonical `work_key` 的别名映射可追溯、可解释、可撤销；“《礼记·檀弓》”“礼记·檀弓”等格式差异可以归并，但“礼记”与某一篇、某一注本不能自动视为同一 identity。
3. `target_work` resolved 必须有来源依据：明确的原始标签或人工确认；仅由 source_work、字符串相似度、外部搜索标题推断的结果只能是 candidate。
4. 对现有 932 个 pending target_work 案例生成分层队列：可机械拆分的 label、需人工消歧的 label、无足够信息的 unresolved；三类数量和案例/evidence ID 必须可复核。

已先生成可复核队列：第一批加入后，`target_work_resolution_queue` 共 1,317 项，1,212 项是机器候选标签，105 项是无 target label、需补上下文的 unresolved 项；没有自动改写 `annotation_cases.target_work`。队列明细为 `v2/data/real_runs/queues/target_work_resolution_queue.target_work.v1.jsonl`。

## 五、问题 3：80 条 `external_source_pending` 如何进入 canonical source registry/edition/passages

### 5.1 当前状态

V2 已把 80 条 external pending evidence 关联到 100 个外部 registry 条目中的相应来源；当前 registry 为 99 `pending`、1 `registered`，`canonical_file_registered_count=0`，外部 quote validation=0。项目内本地材料的命中只能是 context：报告记录 351 条有 local context match、6,894 条无命中；这不等于引用典籍的底本核验。证据：`v2/data/real_runs/external_source_inventory.json:13-33`。

公开转录检索也只完成“定位候选”阶段：80 条中 68 条 `no_public_match`、11 条 `search_hit_only`、1 条 `candidate_found`；形成 3 个连续文本候选、22 个页面原文，但 manifest 明确规定 Wikisource revision 不是已选择的 edition，所有 V2 evidence 仍 unchecked。证据：`v2/data/real_runs/external_public_candidate_manifest.json:6-22`。

### 5.2 哪些可以自动化

可以自动化的部分是资料工程而非学术确认：从 evidence 中抽取并去重 raw cited label；按 work registry 生成外部 source 任务；检查本地/公开候选文件是否存在；冻结文件路径、预期大小、来源 URL、revision ID 和抓取时间；把 candidate passage 切分为带 edition/source_document/location 的 `passage.v1`；在 raw/normalized text 上做连续子串和字符偏移检查；将每个 evidence 绑定到 candidate passage，同时维持 `source_resolution=external_source_pending` 或 `public_candidate_unverified`。

不能自动化为“verified”的部分是选择何种底本/版本、版本与引文是否对应、影印/校勘图像核对、篇章位置确认、异文是否影响结论，以及将候选升级为 canonical。`fetch_external_public_candidates.py` 的 `_register_candidates()` 已正确把公开转录写成 `registered` 而非 `verified`；下一步应新增人工确认的 edition/source record，而不是直接把 registered 改成 verified。证据：`v2/scripts/fetch_external_public_candidates.py:255-305`、`v2/schemas/annotation_v2.sql:151-178`。

### 5.3 推荐的外部来源流水线

按“work identity → source edition → source document → passage → evidence validation”五步推进。第一步先从 100 个 registry 条目中合并同一规范著作身份，但保留全部 raw cited labels；第二步每个 identity 至少登记 `edition`、编者/出版信息或网页 revision、版本选择理由和验证人；第三步以独立 source document 注册文件和 hash，只有可被项目接受的底本才允许 `canonical_active`；第四步从该 source document 生成 passages，保留原文、规范化文本、章节/页码/卷篇位置和 line/offset；第五步逐条重新核验 80 条 quote，把状态细分为 `passed`、`normalized_passed`、`failed`、`unchecked`，并在 case 的 evidence JSON 记录验证依据。

### 5.4 验收门 EXT-1

1. 80 条 pending evidence 每一条都有 external_source_id、raw cited label、目标 canonical work、edition/source document 状态和最终处理结果；不能用“本地搜到相同字符串”代替。
2. 每个 `verified` source 必须有可复核的 edition/version identity、source file/revision、hash、location policy 和人工确认记录；没有这些字段，registry 只能是 pending/registered。
3. 每条 `quote_check=passed` 必须同时满足：quote 在对应 canonical passage 中可定位、`source_resolution=canonical_source_passage`、source document 为 `canonical_active`、hash/offset 一致；验证报告的 canonical quote violations 必须为 0。
4. external pending 清零的含义是“每条都有明确结果”，不是“每条都通过”：无法找到底本的记录必须是 `unresolved/no_source`，不得被删除或强行标成 rejected/verified。
5. 外部底本导入不改变原始 AI/legacy evidence 的 raw quote、raw label 或 provenance；只新增 source resolution 和人工验证事件。

已先生成外部核验队列：100 个 external source registry 项、121 条 external evidence passage 项；当前 source 队列状态为 candidate_available 1、no_public_match 88、pending 11，passage 队列状态为 candidate_available 1、no_public_match 68、search_hit_only 11、其余 pending。候选页和 revision/hash 已保留，但 edition 仍是 `candidate_registered`/`missing`，quote 仍 unchecked；没有自动升级 canonical。队列明细为 `v2/data/real_runs/queues/external_source_resolution_queue.edition.v1.jsonl` 和 `external_passage_resolution_queue.passage.v1.jsonl`。

## 六、问题 4：machine draft、人 pending、gold/人工审校与数据库/UI 边界

### 6.1 当前数据库边界

V2 已在一个物理工作库中分离状态：`annotation_cases` 保存 machine/human/review/lifecycle，`machine_result_json`、`human_review_json` 和完整 `case_json` 分开；`v_machine_cases`、`v_human_review_queue`、`v_gold_cases` 分别提供机器草稿、人工队列和 gold 投影。`_lifecycle()` 规定只有 `human_status=approved` 才进入 gold，机器 rejected 或人工 rejected 才进入 rejected，人工 uncertain 进入 human_review；旧主库和旧标注库仍保持独立，不应绕过 V2 状态直接回写主库。证据：`v2/schemas/annotation_v2.sql:47-74`、`v2/schemas/annotation_v2.sql:224-256`、`v2/src/erwang_v2/database.py:335-343`、`02-数据库/README.md:28-39`。

当前已完成的是“状态模型、只读队列和受控写入边界”，不是人工审校本身：936 个案例全为 machine draft/human pending，review_events=0，gold=0；validation 已检查 machine/human separation、quote boundary、外键、queue references 和 orphan。`apply_review_event()` 已定义 reviewer、operation ID、前后状态、field decisions、逐条 evidence decisions 和 gold approval gate；缺口是尚未接入真实 reviewer UI、分配/锁和冲突解决流程。证据：`v2/data/real_runs/work_queues_report.json`、`v2/src/erwang_v2/database.py`、`v2/tests/test_database.py`。

### 6.2 推荐的数据库/UI分层

数据库是状态和 provenance 的唯一事实源；UI 只读投影和发起受控 review command，不直接编辑 `case_json`、不直接把 lifecycle 改成 gold。最小 UI/服务边界应有三类队列：候选队列（candidate text、source passage、risk、是否已物化）、案例审校队列（source/target、证据逐条、五步过程、机器输出、raw provenance）、外部来源队列（work identity、edition、passages、pending evidence）。每次人工动作写入 `review_events`，带 reviewer、时间、前后状态、note、依据 passage/edition 和幂等 operation ID；同一事件重复提交不得重复晋级。

人工审校表单至少要能分别确认：source passage、target work/target passage、term relation、每条 quote/source resolution、五步过程、结论以及“保留/退回/不确定”。`human_status=approved` 的数据库事务应同时要求审校人、审校时间、审校依据和所有必需 evidence 已有明确状态；否则只能 pending/uncertain。gold 视图只能输出通过该事务的案例，主库/网站快照只能消费 gold 导出，不应直接消费 `v_machine_cases`。

### 6.3 验收门 REVIEW-1

1. 初始基线验收：`machine_status=draft`、`human_status=pending`、`lifecycle=machine_draft`、gold=0、review_events=0 的数量与报告一致。
2. 单条审校验收：一次人工动作产生一条不可变 review event；案例状态、`human_review_json`、lifecycle 和 `v_human_review_queue/v_gold_cases` 同一事务更新，重复提交幂等。
3. 反向验收：机器 validator 通过、引文定位通过、external candidate found、旧字段 `已审核/确定` 都不能单独造成 human approved 或 gold。
4. 不确定/退回验收：uncertain 保留在人工队列并显示原因；rejected 保留完整 raw provenance 和 rejection reason，不能删除 candidate/evidence。
5. UI 读写验收：UI 的数量必须能由视图/查询复算；展示文案明确区分“候选审计通过”“机器草稿”“人工已审”“gold”，禁止用“已校对/已审核”等旧库标签覆盖 V2 状态。
6. 主库边界验收：在 V2 gold 非空且导出契约通过前，不运行把 V2 工作库直接同步成旧 `dictionary.db` 或网站公开快照的路径；`02-数据库` 现有“审核通过案例再考虑迁移到主库”的优先级只能作为后置出口。

已实现 review 写入边界：`apply_review_event()` 要求唯一 `operation_id`，在一个事务中写入不可变 `review_events`、更新 `human_review_json` 和案例 lifecycle/status；重复 operation 幂等。`approved` 还要求 reviewer、六类字段决定、逐条 evidence decisions、resolved target passage 和已通过 quote；机器 validator、candidate shell、旧字段“确定”都不能绕过。生产库当前 `review_events=0`，人工审校尚未执行。验证样例在 `v2/tests/test_database.py`。

## 七、建议的下一步顺序

1. 已完成第一批 100 条 candidate shell；下一批先按风险/来源分层选择，不自动把 6,645 条全部物化成空壳。
2. 先处理 target_work 队列中有明确篇名但缺 canonical edition/passage 的高优先项，再处理 105 条无上下文项；任何机械别名都保持 candidate_only。
3. 将 100 个 external registry 条目按 canonical work 合并任务，优先处理已有 public candidate 的来源；公开转录只作为 candidate，先补 edition/verification record。
4. 接入只读审校界面的受控 review command，先用临时数据库完成 pending → uncertain/rejected/approved 的事务回放，再决定是否开放生产写入。
5. 只有上述四个验收门都能由报告和数据库查询复算后，才考虑 gold 导出、旧主库新 source 渠道和网站公开快照。

## 八、资料索引

- Schema：`v2/schemas/annotation_v2.sql`、`v2/schemas/annotation_case.v1.schema.json`。
- 候选与案例：`v2/src/erwang_v2/candidate_extractor.py`、`candidate_auditor.py`、`original_candidate_adapter.py`、`target_inference.py`、`database.py`。
- 运行入口：`v2/scripts/run_unified_ingress.py`、`run_machine_completion.py`、`run_external_source_inventory.py`、`fetch_external_public_candidates.py`、`reconcile_external_public_matches.py`、`run_v2_validation.py`。
- 当前报告：`v2/data/real_runs/unified_ingress_report.json`、`machine_completion_report.json`、`batch_migration_report.json`、`external_source_inventory.json`、`external_public_candidate_manifest.json`、`v2_validation_report.json`、`legacy_machine_conversion_report.json`、`legacy_dictionary_field_audit.json`。
- 旧数据库边界：`02-数据库/README.md`、`02-数据库/annotation/schema.sql`、`02-数据库/main/schema.sql`。
