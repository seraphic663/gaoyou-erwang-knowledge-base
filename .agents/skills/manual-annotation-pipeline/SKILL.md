---
name: manual-annotation-pipeline
description: 在本项目中将获准处理的人工标注 DOCX 转成文档 Markdown、案例 Markdown、现有 annotation_case.v1 JSONL 和人工标注库，并按用户要求部署网站快照。适用于新增标注批次或修正指定标注条目。
---

# 人工标注入库流程

在项目根目录使用 Windows PowerShell 7 和 Windows Python。只处理用户指定批次、条目和输出；原始 DOCX 保留原位。不计算哈希，不创建备份、工作副本或额外一套 JSON。旧 `full_json`、`ai_json` 不作为当前转换依据。

## 路径与现有格式

所有标注材料集中在 `data/D-标注/`：

| 阶段 | 位置 |
| --- | --- |
| 原始文档 | `01-原始DOCX/<批次>/` |
| 完整文档 Markdown | `02-文档Markdown/` |
| 案例 Markdown | `03-案例Markdown/` |
| JSONL | `04-案例JSONL/manual_annotation_cases.annotation_case.v1.candidates.jsonl` |
| 转换记录 | `04-案例JSONL/manual_annotation_conversion_report.json` |
| 人工库 | `05-数据库/annotations.db` |
| 网站快照 | `solution/website/data/annotation-snapshot.json` |

开始前读取两个 Markdown 目录的 README 和同类旧案例。读书杂志可参考 047–050，广雅疏证参考 053–056，经义述闻参考 005–008、077–078。以实际旧文件的栏目和正文形态为准，不设计新模板。`annotation_case.v1` 是现有 JSONL 的格式版本，与项目 V2 的称呼无关。

文件名沿用 `编号-二王出处-考据文献-条目-标注者.md`，如 `077-经义述闻-诗经-伊予來塈-未知.md`。从现有最大来源编号之后续编。多个独立案例才加 A、B 等后缀；同一论证中的并列词和多条引文不据此拆案。单案例的文档 Markdown 和案例 Markdown 可以一致。

## 作者和输入范围

- 按用户指定的 `docProps/core.xml` 中 `dc:creator` 记录作者：`飞宇 卢` → 卢飞宇，`妺晗 李` → 李妺晗；直接姓名照录。`Un-named`、空值等未知作者统一写“未知”，文件名和 JSONL 作者字段一致。
- “分析体例总结”等说明文档作为格式参考，不生成案例或入库。
- 用户要求四个 Luna Max 时，按实际四个文件夹各分配一个代理；体例组负责对照格式。主代理统一维护编号、JSONL、数据库及部署，避免并发修改共享产物。Fast 没有可用设置接口时如实说明。

## DOCX → 两层 Markdown

使用 `data/D-标注/json/docx_to_markdown.py`：

```powershell
python data/D-标注/json/docx_to_markdown.py "原始DOCX路径" "编号-出处-考据文献-条目-作者.md" --title "条目"
```

脚本写入 02、03 两层输出，已有同名文件会停止。仅在获准修正本次生成文件时使用 `--overwrite`。

保留原 Word 的段落、栏目、繁简、标点、引文、内嵌字形和实际顺序，不为了凑齐栏目补写内容。正文使用旧文件的 `DOCX-BODY-START/END` 标记，来源链接指向 01 原件。逐份对照正文和 OOXML 注释部件；脚注编号 0 可能是真实脚注，分隔符应按 `w:type` 排除。保留真实脚注锚点及注文。

原稿疑似错贴、残留其他条目等问题保留原文，在本次记录的 `_migration.source_notes` 和转换报告记明，维持待核状态。

## 案例 Markdown → JSONL → 人工库

使用维护脚本，只列本次获准的新案例编号：

```powershell
python data/D-标注/json/publish_manual_batch.py convert --ids 062 063
python data/D-标注/json/publish_manual_batch.py import --ids 062 063
```

把示例编号换成本次编号。转换调用既有 Markdown 解析器并关闭哈希计算，追加候选和更新现有转换报告；旧 JSONL 记录保留。先检查新条目的栏目、引文和结论有没有被解析器漏掉，修正后再入库。修正仅限本次记录，不重生成旧批次。

人工库以稳定的 `manual_md:<编号>` 防止重复插入。新增记录保持“草稿/待核”；未解析或未核实的字段保留对应说明，不伪装成人工确认。只写上述人工库，`v2/data/real_runs/annotation_v2.db` 仅可只读匹配原典，`dictionary.db` 不写入。

已入库原稿修订时，上述追加命令会跳过已有编号。按原编号重新调用 `build_record(..., compute_hashes=False)`，替换 JSONL 对应行，并使用 `publish_manual_batch.py` 的投影函数更新数据库原记录及其原文数据。保留案例数值 ID、来源 ID 和创建时间；子记录内容变化时仅刷新该案例的子记录。清除已解决的原稿疑点标记，更新对应目录行，再导出快照并按授权部署。不要追加一个新编号代替旧案例。

入库后更新两个 Markdown README 的映射、`data/D-标注/README.md` 的实际计数及相关作者记录。不要新建重复索引或另存一套结果。

## 网站快照与部署

用户已要求部署时，先导出快照，再发布：

```powershell
python solution/website/scripts/annotation_bridge.py export
railway up --detach --service gaoyou-erwang-knowledge-base --environment production --message "Import approved manual annotation batch"
```

CLI 超时时先查 `railway deployment list`，服务器可能已经接受部署；不要直接重复发布。等待目标部署 `SUCCESS` 并读取启动日志，再查 `https://gaoyou-demo.up.railway.app/api/annotation/index` 的计数和新增条目。通过索引中的数值 `id` 查询 `/api/annotation/detail?id=<id>`，核对新增内容及未知作者；不能只凭健康接口报告完成。

最后简短汇报新增来源/案例数、数据库总数、线上结果和必要的原稿待核问题，并给出本项目文件链接。提交、推送按用户本次授权范围处理。
