# V2 架构原型

这是依据 `00-项目说明` 规划建立的、独立于旧数据库实现的 V2 数据核心原型目录。

## 目标

V2 先验证这一条最小闭环：

    原典 Markdown
      -> 预处理
      -> passage
      -> candidate
      -> 机器审计
      -> annotation_case.v1 校验
      -> 统一工作数据库（机器案例先入库）
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
- `passage_id`、quote、hash、来源位置和状态字段先在小样本上跑通，再接真实全量资料。

## 运行最小测试

无需复制原典，也无需先安装外部包：

    python v2/scripts/smoke_test.py

可选依赖写在 requirements.txt 中。后续接入正式 JSON Schema 校验和 pytest 时再安装：

    python -m pip install -r v2/requirements.txt

## 接入真实文件的原则

真实 Markdown 通过路径传入 `passage_builder`；旧 AI JSON 通过 `legacy_ai_adapter` 映射到 V2；校验通过的机器案例进入统一 V2 工作数据库，人工状态保留为 `pending`。原始文件只读，原始 hash 必须进入输出元数据。

真实案例跑通命令：

    python v2/scripts/run_real_case.py

该命令默认读取《读书杂志》真实 Markdown 和现有 AI JSON 的“平原之隰”案例，执行段落定位、引文匹配、旧格式映射、V2 校验、统一数据库机器入库和机器/人工状态分离；它不会把原始文档复制进 V2，也不会写入旧数据库。

批量迁移 3 个旧 AI JSON：

    python v2/scripts/run_batch_migration.py

该命令会把所有旧 AI JSON 作为迁移/回归材料写入同一个 V2 工作库，并生成 `v2/data/real_runs/batch_migration_report.json`。报告区分 `approved`、`draft`、`rejected`，保留人工 `pending`；未加载的外部原典引文只记为 `unchecked`，不会被误报为已核验。
