# V2 统一工作库

这是独立于旧 `dictionary.db` 和 `annotations.db` 的 V2 数据核心目录，包含 schema、实现、测试、机器运行、统一工作数据库、工作队列和人工审校任务。2026-08-30 复核时机器链路已跑通，但全部 7,581 个案例仍为机器草稿和人工待审，gold=0。

## 定位与工作流

V2 先验证这一条最小闭环：

    原典 Markdown
      -> 预处理 -> passage -> candidate -> candidate_items
                                      │
    旧 AI JSON ------------------------┤
    旧 dictionary.db ------------------┘
                                      ▼
                         annotation_case.v1 校验
                                      ▼
                         统一工作数据库（V2）
      -> 人工审校
      -> gold / 主库 / 网站快照

本目录不复制四部原典、PDF 或 DOCX。真实资料仍位于：

- 04-项目文献/A-原著原典/
- 04-项目文献/D-标注/
- 05-归档文献/

data/fixtures/ 中只有短小的合成测试片段，用来验证代码结构和字段关系，不作为原典底本。

## 目录

    v2/
      README.md
      requirements.txt
      schemas/
        annotation_case.v1.schema.json
        annotation_v2.sql
      src/erwang_v2/
        markdown_preprocess.py
        passage_builder.py
        candidate_extractor.py
        candidate_auditor.py
        database.py
        legacy_ai_adapter.py
        legacy_dictionary_adapter.py
        original_candidate_adapter.py
        target_inference.py
        validate_annotation_case.py
        pipeline.py
      data/fixtures/
        sources/
        passages.jsonl
        cases/
      tests/
      scripts/

## 当前边界

- 这是 V2 的基础架构，不是完整主库。
- V2 独立位于项目根目录 `v2/`；旧数据库仍位于 `02-数据库/`，二者通过适配器连接。
- 不修改 `02-数据库/main/` 的旧 parser/importer。
- 不自动覆盖原始 Markdown。
- 机器案例可以在通过校验后进入 V2 统一工作数据库；不能把机器通过结果当作人工审校结果。
- `annotation_cases` 同时保存机器状态和人工状态；只有 `human_review.status=approved` 的案例才能晋级 gold。
- `passage_id`、quote、offset、来源位置和状态字段先在小样本上跑通，再接真实全量资料；同一 `work_key/source_file` 只对应一个稳定 source document。
- `target_work` 不明确时保留为空，并使用 `target_works`、`target_scope` 记录未决状态；原典明确不引证时使用 `evidence_state=source_no_citation`，不制造占位 evidence。
- 机器可以从旧 evidence 的显式 `source_work` 生成 `target_works` 候选，但候选状态为 `machine_inferred/candidate_only`，不等于 resolved `target_work`，也不等于机器通过。
- 引文区分 `canonical_source_passage`、`secondary_citation_match`、`external_source_pending`；后两者都不能当作原典核验通过。
- `candidate_items` 是原典入口的机器候选层，和 `annotation_cases` 分开；候选只有在明确走 AI 或其他案例适配器后，才生成 `annotation_case.v1`。
- 每条案例都保留 `_migration.source_layer`、`transformation_kind`、来源文件/记录 ID 和上游 revision。当前来源类型为：`legacy_ai_json_reprocessing`（旧 AI JSON 再加工）、`legacy_dictionary_db_reprocessing`（旧机器库再加工）、`original_markdown_machine_extraction`（原文机器抽取）、`original_markdown_ai`（原文候选经 AI 再加工）。

## 运行最小测试

无需复制原典，也无需先安装外部包：

    python v2/scripts/smoke_test.py

可选依赖写在 requirements.txt 中。后续接入正式 JSON Schema 校验和 pytest 时再安装：

    python -m pip install -r v2/requirements.txt

## 接入真实文件的原则

真实 Markdown 通过路径传入 `passage_builder`；旧 AI JSON 通过 `legacy_ai_adapter` 映射到 V2；校验通过的机器案例进入统一 V2 工作数据库，人工状态保留为 `pending`。原始文件只读，来源路径、稳定记录 ID 和上游 revision 进入输出元数据。未加载的外部典籍会进入 `external_source_registry`，等待独立底本登记和核验。

真实案例跑通命令：

    python v2/scripts/run_real_case.py

该命令默认读取《读书杂志》真实 Markdown 和现有 AI JSON 的“平原之隰”案例，执行段落定位、引文匹配、旧格式映射、V2 校验、统一数据库机器入库和机器/人工状态分离；它不会把原始文档复制进 V2，也不会写入旧数据库。

批量迁移 3 个旧 AI JSON，并同时盘点四部原典：

    python v2/scripts/run_batch_migration.py

该命令会把所有旧 AI JSON 作为迁移/回归材料写入同一个 V2 工作库，并额外登记《经义述闻》的 passage 和候选审计，不凭空生成案例。报告区分 `approved`、`draft`、`rejected`，保留人工 `pending`；未加载的外部原典引文只记为 `unchecked`，同时保留 full JSON 上下文命中和王氏正文二次命中，但不会被误报为原典核验通过。

旧 AI 的 full JSON 定位现在也被完整保存：每条迁移证据保留 full JSON 相对路径、段落号、匹配模式和段落内字符起止位置。full JSON 命中只是旧标注上下文的迁移线索，不等于外部原典 quote passed。

两条来源入口统一跑通：

    python v2/scripts/run_unified_ingress.py

该命令将 3 个旧 AI JSON 的 17 条案例、旧 `02-数据库/data/dictionary.db` 的 815 条机器案例和四部王氏原文的 6,749 条候选汇合到同一个 V2 工作库；四部原文各抽取 1 条代表候选实际调用 AI，生成 4 条 `original_markdown_ai` 案例。全量原文候选都进入 `candidate_items`，不是把 6,749 条直接冒充案例。报告位于 `v2/data/real_runs/unified_ingress_report.json`，明细 JSONL 位于 `v2/data/real_runs/unified_ingress/`。

统一入口与全量候选壳结果（不含外部公开候选 passage 导入）：6 个 source documents、15,467 个 passages、6,749 个 candidate items、7,581 个 annotation cases；其中 17 个来自旧 AI JSON、815 个来自旧机器库、4 个来自原典代表性 AI 样例、6,745 个是原典 candidate shell。当前生产工作库已登记 29 个 `external_public_candidate` source documents/passages，因此实际为 35 个 source documents、15,496 个 passages；这些外部页面仍是 `canonical_status=unknown` 的候选，不改变 annotation evidence。机器状态为 `draft=7,581`、`rejected=0`，人工状态 `pending=7,581`，gold 为 0。当前工作库有 13,990 条证据、37,905 个过程步骤、`review_events=0`。数据库完整性、外键、候选/案例孤儿和候选壳物化覆盖均通过。四部原典的 7,532 个 canonical passages 通过稳定 source document、来源路径和标题路径登记；LF/CRLF 不再被视为两个内容版本。

机器侧完整运行：

    python v2/scripts/run_machine_completion.py

该命令依次执行批量迁移、四部原典/候选盘点、外部来源本地文件盘点、数据库完整性和外键检查，并生成 `v2/data/real_runs/machine_completion_report.json` 与 `v2/data/real_runs/external_source_inventory.json`。它不会进行人工审校、不会写入 gold、不会覆盖原始资料。

公开外部文本候选获取（不自动通过 canonical）：

    python v2/scripts/fetch_external_public_candidates.py \
      --output-dir v2/data/external_sources/wikisource_candidate \
      --manifest v2/data/real_runs/external_public_candidate_manifest.json \
      --candidates v2/data/real_runs/external_passage_candidates.passage.v1.jsonl

该命令现在通过 `--include-secondary-citations` 同时读取 80 条 `external_source_pending` 和 41 条 `secondary_citation_match` 引文，共 121 条；它通过维基文库公开 API 搜索并冻结页面 revision 原文，标题不命中被引作品/篇名的搜索结果不会下载为候选。对已冻结页面再运行 `v2/scripts/reconcile_external_public_matches.py`，用共用的保守 Wikitext 清理和小范围简繁定位重算连续命中，并从 V2 外部 passage 队列恢复按页面路径、pageid/revid 标识的候选页面。当前 manifest 为 `candidate_found=11`、`search_hit_only=10`、`no_public_match=100`，共 17 个候选记录、31 个公开页面记录，其中 17 个可作 `normalized_contiguous` 机器匹配；这是定位候选，不是 canonical。所有 external evidence 仍为 `quote_check=unchecked`；现有队列还保留此前检索已找到的候选，当前为 source `candidate_available=14`、`no_public_match=79`、`pending=7`，passage `candidate_available=15`、`no_public_match=96`、`pending=10`。外部版本/底本仍未确认。CText 的 API/网页人机验证边界及 Round 3 的逐来源研究记录在 `v2/research/external_source_research_round3.md`，早期入口记录仍保留在 `v2/research/external_source_research_round2.md` 和 `v2/research/external_source_research.md`。

冻结的公开候选 passage 入库（仍不自动通过 canonical）：

    python v2/scripts/ingest_external_candidate_passages.py \
      --database v2/data/real_runs/annotation_v2.db \
      --manifest v2/data/real_runs/external_public_candidate_manifest.json

该命令只将 manifest 中 `offline_match_mode=normalized_contiguous` 的冻结页面导入为 `source_kind=external_public_candidate`、`canonical_status=unknown` 的 passage，并把稳定 passage ID 写入外部 passage 待办队列；不改变 evidence 的 `passage_id`、`quote_check` 或 `source_resolution`。本轮扫描 17 个候选记录、导入/幂等写入 16 个唯一候选 passage ID，17 个候选-引文绑定均能在候选文本中机器命中 quote；连同之前保留的候选，数据库当前有 29 个唯一 candidate passage，队列中有 30 个候选 passage 关联（同一候选可被多条 evidence 共享），仍需版本/底本/影印层人工核验。结果记录在 `v2/data/real_runs/external_candidate_passage_ingest.v1.json`。

外部证据包与人工入口前置材料：

    python v2/scripts/build_external_evidence_packets.py

该命令把 100 个 external source queue 行和 121 个 external passage queue 行分别打包为可追溯的机器证据包，重检候选文件存在性、连续匹配、manifest、queue、registry 和 evidence 的对应关系；当前 source/passage 覆盖为 `100/100`、`121/121`。证据包只用于机器定位和人工审校准备，不改变 `canonical_status`、evidence link 或 `quote_check`。结果位于 `v2/data/real_runs/external_evidence_packets.v1.jsonl` 与 `v2/data/real_runs/external_evidence_packets_report.json`，并通过 `run_v2_validation.py` 的 `external_evidence_packets` 门。

外部独立底本候选冻结（仍不登记为 canonical）：

    python v2/scripts/freeze_external_edition_candidates.py

该命令读取 `v2/data/real_runs/external_edition_fetch_manifest.v1.json`，从 Internet Archive 冻结候选卷册的 metadata 和 DjVu OCR；扫描 PDF 只在 OCR 先命中引文时下载，当前没有自动 OCR 命中，因此本轮没有把大体量影印 PDF 伪装成已完成材料；CText 入口若被当前环境 403 阻断，则只记录阻断状态和 URL。结果位于 `v2/data/real_runs/external_edition_candidate_manifest.v1.json` 与 `v2/data/external_sources/edition_candidates/`。当前候选包为 34 个（32 个 IA 可下载候选、2 个 CText 阻断入口），191 个候选条目，191 个完整 OCR 文件记录，关联 95 个外部来源；文件缺失、大小错误均为 0，数据库写入为 0，自动 OCR quote match 为 0。OCR 只能定位，影印 PDF 仍需人工逐页确认；《礼记大全》《春秋左传注疏》《管子校正》《管子》及《论语注疏》保持不同版本/文本层，不互相替代。

候选冻结包自校验由 `build_external_evidence_packets.py` 内的 `validate_external_edition_candidate_manifest()` 执行，并作为外部 evidence packet 和 `run_v2_validation.py` 的边界门：所有冻结文件逐个核安全路径、存在性和预期大小；候选只允许保持 unknown，不能改变 `source_documents`、`annotation_evidences.quote_check`、人工 pending 或 gold。当前外部 packet 会把 95 个来源的候选卷册引用、文件路径、上游标识和文本层直接带给后续人工任务。

当前外部来源状态以 `v2/data/real_runs/external_source_inventory.json`、`v2/data/real_runs/work_queues_report.json` 和 `v2/data/real_runs/v2_validation_report.json` 为准：100 个外部来源中 14 个是已登记但未核验的公开转录候选、86 个仍为 `pending`，独立 canonical 底本为 0；外部来源队列为 `candidate_available=14`、`no_public_match=79`、`pending=7`，外部 passage 队列为 `candidate_available=15`、`no_public_match=96`、`pending=10`。公开候选定位完成不等于版本确认、引文通过或 gold。本轮对《急就篇》《管子·形势解》《礼记·月令》《论语·微子》的入口和失败边界记录在 `v2/research/external_canonical_source_research_round4.md`。

只转换最大旧机器库（不调用 AI）：

    python v2/scripts/run_legacy_machine_conversion.py

该命令读取 `02-数据库/data/dictionary.db`，追溯其上游 `02-数据库/main/source.txt -> parser.py -> importer.py`，把 815 个旧机器案例、6,628 条案例-词条关系和 7,120 条证据重新写成 `annotation_case.v1` 并入 V2；同时从 `source.txt` 生成 815 个 `legacy_source_case` passage，从旧证据文本生成 7,120 个 `legacy_derived_quote` passage，并将 815 个案例的 source/target/process 字段和 7,120 条证据绑定到这些 legacy passage。它不会把旧 `certainty=确定` 当成人工通过，也不会把 legacy passage 或机器拼接文本冒充 canonical quote；7,120 条 evidence 均保持 `unchecked`、`source_resolution=legacy_derived_passage`。报告位于 `v2/data/real_runs/legacy_machine_conversion_report.json`，转换 JSONL 位于 `v2/data/real_runs/legacy_machine_conversion/`。

旧库中 14 个没有挂入任何案例的词条和 12 个没有被证据引用的著作目录项已经进入 V2 的 `legacy_catalog_terms` / `legacy_catalog_works`，状态为 `catalog_only`、`unreferenced`，保留旧 ID、来源文件和未引用原因；它们没有被伪造为研究案例、证据或 gold。

旧主库字段利用审计：

    python v2/scripts/audit_legacy_dictionary_usage.py

审计报告位于 `v2/data/real_runs/legacy_dictionary_field_audit.json`，只读比较 `02-数据库/data/dictionary.db` 与 V2 的实际表示。当前确认：旧库 3,385 个词条中 3,371 个被案例/证据使用，14 个保留为 `catalog-only`；49 个著作中 37 个被证据使用，12 个保留为 `catalog-only`；815 个案例、6,628 条案例-词条关系、7,120 条证据均已机械迁移且可回溯。`方言`、`声训`、`异文`、`同义实词`、`方言俗语`、`音训·通假字` 等字段/分类没有被丢弃，但它们仍是旧机器材料的结构化表示，不等于 canonical 原典核验或人工结论。

当前并不存在一个可直接读取的 MySQL10 运行库；本地旧主库实际是 SQLite `dictionary.db`，网站的旧入口读取 `sqlite-snapshot.json`。V2 不把这个快照当作 canonical 原典，而是把它按 `source.txt -> parser.py -> importer.py -> dictionary.db` 链路作为 `legacy_dictionary_db_reprocessing` 迁移来源；主库的 `passages=0`、案例 passage/process 字段为空、证据没有 source passage 的缺口，已由 V2 的 legacy passage 和机器补齐字段显式承接，未伪造为原典证据。

来源清点可重复运行：

    python v2/scripts/audit_source_inventory.py

报告 `v2/data/real_runs/source_inventory.v1.json` 明确列出四部 canonical Markdown、旧 SQLite 路线、旧 AI/full JSON、网站派生快照和当前项目树内的 MySQL/SQL/DUMP 搜索结果。当前项目树没有可独立识别为 MySQL10 运行库或 dump 的文件；`schema.sql` 只按 schema/扩展名候选列出，不能被误称为 MySQL10 数据快照。若另有未挂载或项目外的 MySQL10 快照，需要提供实际路径后才能纳入 V2 的输入清单。

独立数据库验收：

    python v2/scripts/run_v2_validation.py

该只读脚本检查 SQLite 完整性和外键、四部 canonical 来源、815/7,120 legacy passage 覆盖、五步字段、quote/offset、canonical quote 边界、孤儿引用、14/12 个 catalog-only 项、machine/human 状态分离、三类队列引用和 `review_events.operation_id` 幂等索引。报告位于 `v2/data/real_runs/v2_validation_report.json`。

著作身份/别名注册与候选分批计划：

    python v2/scripts/build_work_registry.py
    python v2/scripts/plan_candidate_materialization.py --batch-size 100

前一个命令建立可逆的 `work_registry` / `work_aliases` 层：格式等价的《》和空白差异可以映射到四部 canonical `work_key`；外部来源和无法安全消歧的目标标签保留为 `external_pending`/`unknown`，不静默写入 `target_work`。后一个命令只读扫描全部 6,749 个 `candidate_items`，输出逐条 `candidate_materialization_plan.candidate_shell.v1.jsonl` 和报告；4 条原典代表性 AI 案例保留，6,745 条候选已经全部按每批最多 100 条分成 68 批并物化为确定性 candidate shell。全量物化不调用 AI、不生成语义结论、不升级 target_work、target_passage 或 gold。报告位于 `v2/data/real_runs/work_registry_report.json`、`v2/data/real_runs/candidate_materialization_plan_report.json` 和 `v2/data/real_runs/candidate_shell_all_batches_report.json`。

全量物化候选壳：

    python v2/scripts/materialize_all_candidate_batches.py

该命令按确定性批次调用单批写入 seam，生成 68 份 `candidate_shell_batch_*.annotation_case.v1.jsonl` 和对应报告；6,745 条 candidate shell 逐条保留 source passage、连续 source quote、原文文件与来源 ID、候选规则/风险、计划批次和字段边界，`candidate_items.output_case_id` 全部建立回链，重复执行幂等跳过。每批 20/50/100 条的网页分页只改变展示范围，不改变数据库状态。

机器目标定位候选：

    python v2/scripts/infer_candidate_target_locations.py

该命令从 6,749 个原典候选中抽取显式《书名》标记并在四部 canonical passages 内做保守的精确片段搜索，生成 74,171 条 `candidate_target_locations`；其中 283 条标签可映射到四部 canonical work、139 条有其他 canonical passage 候选。它不写入 `annotation_cases.target_work` 或 `target_passage_id`，不改变机器/人工状态，报告为 `v2/data/real_runs/candidate_target_location_report.json`。

目标典籍解析 packet：

    python v2/scripts/build_target_work_resolution_packets.py

该只读命令把当前 target-work 队列的每一条任务整理为可追溯的紧凑机器材料：案例与过程摘要、source/evidence passage 引用、quote/source resolution 摘要、相关 `work_registry`/`work_aliases`、同标签原典候选定位样本、外部来源/段落队列摘要以及每个字段的机器边界。大段原文和完整 evidence/候选集合不在每条 packet 中重复嵌入，而以稳定 ID 和文件引用回链。当前生成 `7,962` 条 packet，覆盖 `7,577` 个案例；报告位于 `v2/data/real_runs/target_work_resolution_packets_report.json`，数据位于 `v2/data/real_runs/target_work_resolution_packets.v1.jsonl`。packet 只为人工审校准备，绝不自动写入 `target_work`、`target_passage_id`、quote 状态、人工状态或 gold；`run_v2_validation.py` 会以流式读取检查 packet 与 pending queue 的逐条覆盖、passage 回链和机器边界。

目标典籍解析 proposal 索引：

    python v2/scripts/build_target_work_resolution_proposals.py --validate

该只读命令从同一 target-work 队列生成轻量的 `target_work_resolution_proposals.v1.jsonl`，一条 queue item 对应一条 proposal，当前 `7,962/7,962` 覆盖、约 `19 MB`，不重复嵌入完整 packet。它把 `463` 条 canonical-active 机器身份、`425` 条 external-pending 身份、`305` 条 unknown 身份和 `6,769` 条无可用标签分成可执行的人工下一动作；同时嵌入 `112` 个机器 target-passage 候选引用。proposal 不是 resolution：不写 `target_work`、不写 `target_passage_id`、不写 queue 状态、不产生 resolution event，也不把 legacy-derived passage 升级为 canonical。报告和覆盖校验分别位于 `v2/data/real_runs/target_work_resolution_proposals_report.json` 与 `v2/data/real_runs/target_work_resolution_proposals_report.validation.json`。

自动化缺口审计：

    python v2/scripts/build_automation_gap_report.py

报告位于 `v2/data/real_runs/automation_gap_report.v1.json`，把“已经机器物化”与“仍需底本/语义判断/人工审校”分开统计。当前 7,577 个案例的 `target_work` 仍为空；其中 815 个旧机器案例的 `target_passage_id` 只是 `legacy_derived_quote`、`legacy_unverified`，不是 canonical target passage。旧库 3,385 个词条、49 个著作、6,628 条词条关系和 7,120 条著作-证据关系都有 V2 落点；14 个词条和 12 个著作保留为 `catalog_only`，没有伪造案例或引文。另将旧库中 37 个被证据实际引用的著作登记到 `work_registry/work_aliases` 的可追溯候选身份（合法 `identity_status=unknown`，metadata 标明 `legacy_dictionary_work_reference`），不改变 12 个 catalog-only 著作的边界，也不把这些著作变成 canonical。

工作流覆盖审计：

    python v2/scripts/audit_workflow_coverage.py

报告位于 `v2/data/real_runs/workflow_coverage_report.v1.json`，按项目定义的 11 步 workflow 逐步列出实际 artifact、数量、已完成的机器工作和剩余边界。它特别区分 `legacy_dictionary_db_reprocessing` 的 815 个机器迁移案例、17 个旧 AI 迁移案例、4 个原典代表性 AI 案例和 6,745 个 `original_markdown_candidate_shell`；因此 7,581 个 `annotation_cases` 的结构总数不会被误读成 7,581 个已经完成的学术案例。当前第 5–7 步是“机器材料已备齐、目标身份/外部底本仍待决”：source passage 已覆盖 7,581 个案例，target passage 只有 815 个 legacy-derived 未核验链接，外部 canonical 文件为 0；机器/人工状态仍为 `draft=7,581`、`human pending=7,581`、gold 为 0。

三类后续队列：

    python v2/scripts/build_work_queues.py

该命令生成 `target_work_resolution_queue`（当前 7,962 项）、`external_source_resolution_queue`（100 个外部来源）、`external_passage_resolution_queue`（121 条外部证据）和 `human_review_queue` 快照（7,581 个案例）。公开转录只进入 candidate_available，不进入 canonical；no_public_match/search_hit_only 保留原状态。队列报告位于 `v2/data/real_runs/work_queues_report.json`，JSONL 明细位于 `v2/data/real_runs/queues/`。

人工审校写入边界由四个事务 seam 提供：`apply_case_review_submission()` 写案例 patch 和 `review_events`，`apply_target_work_resolution()` 写目标典籍消歧但不改变 human pending，`apply_external_source_resolution()` 和 `apply_external_passage_resolution()` 写外部来源/段落的独立 `resolution_events`。每个命令必须带唯一 `operation_id`，重复提交幂等；案例审批还必须有 reviewer、source/target/evidence/process/conclusion 六类 field decisions、逐条 evidence decisions、已绑定 canonical target passage 和 quote passed；不满足时不能进入 gold。外部来源即使被人工标为 verified，也必须提供可核对的文件、版本/上游 revision 和与其一致的 canonical passage，且不会自动修改 annotation evidence 的 quote_check。当前生产库没有执行人工事件，`review_events=0`、`resolution_events=0`。

人工审校任务包：

    python v2/scripts/build_review_task_batches.py --batch-size 100

该只读命令把案例、target_work、外部来源版本和外部 passage/quote 分成四条 `review_task.v1` JSONL 流，每条任务有稳定 `task_id`、`batch_id`、核心摘要、detail ref 和对应的 machine-only target/external packet 引用；manifest 会逐条与当前 pending queue 反向比对，任务包不写数据库、不产生 review event。当前生产任务包为案例 7,581 条/76 批、target_work 7,962 条/80 批、外部来源 100 条/1 批、外部 passage 121 条/2 批，批次上限 100；manifest 位于 `v2/data/real_runs/review_tasks/review_task_manifest.review.v1.json`，并由 `run_v2_validation.py` 的 `review_task_artifacts` 与 `target_work_resolution_packets` 检查纳入正式验收。

本地只读工作库：启动 `03-项目网站` 后访问 `/v2-database.html`，在同一入口内按“数据浏览 / 待办审校 / 质量报告”切换；旧 `/v2-acceptance.html` 只保留兼容跳转。页面通过 `/api/v2/summary`、`/api/v2/cases` 和 `/api/v2/case?id=...` 读取同一个 V2 工作库；案例队列支持检索、来源/机器状态筛选、每批 20/50/100 条分页，列表默认只显示案例核心字段，目标定位候选、来源 passage、证据、词条、五步过程、来源记录和完整 JSON 在单条详情中按折叠区展开。质量报告会复用当前 `v2_validation_report.json`，报告过期时显示待重跑提示，不把旧验收结果冒充当前状态；外部候选 passage 在案例证据详情中按“候选、不等于 canonical”折叠展示。

当前 VR 还提供受控的人工审校任务入口：`GET /api/v2/review-tasks` 按四条任务流和批次读取静态 `review_task.v1`，`GET /api/v2/review-task` 读取单条任务，`POST /api/v2/review` 仅在以 `V2_REVIEW_WRITE_ENABLED=1` 启动本地服务时开放。VR 默认每批只显示前 20 条，可切换 50/100 条；提交 bridge 还会把 `task_id`、任务类型、queue item、当前 pending 状态与持久化任务包绑定，不能用任意 queue item 或 stale task 绕过任务流。提交接口只转发到 `apply_case_review_submission()`、`apply_target_work_resolution()`、`apply_external_source_resolution()` 或 `apply_external_passage_resolution()`；任务选择本身不写库，target/source/passage resolution 不晋级 gold，重复 `operation_id` 幂等，案例 `approved` 仍受完整字段决定、canonical target passage 和 quote gate 约束。提交后必须重建任务包，静态 JSONL 不会自行改变。默认启动仍是只读：

    V2_REVIEW_WRITE_ENABLED=1 npm start

该开关只用于本地受控审校，不代表已完成人工审校；当前生产库仍应保持 `review_events=0`、`resolution_events=0`、`machine_status=draft`、`human_status=pending`、gold 为 0。
