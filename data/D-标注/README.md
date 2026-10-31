# 标注数据目录

> 处理链和数据库数量核对于 2026-10-31；案例状态仍为草稿/待核。

标注材料集中按处理阶段存放：DOCX → 文档 Markdown → 案例 Markdown → JSONL → `annotations.db`。

| 阶段 | 目录 | 核查数量 |
| --- | --- | --- |
| 原始 DOCX | [01-原始DOCX](01-原始DOCX/) | 7 个批次、82 份 DOCX；保留批次与标注人目录 |
| 完整转写 | [02-文档Markdown](02-文档Markdown/README.md) | 78 篇 |
| 个案拆分 | [03-案例Markdown](03-案例Markdown/README.md) | 117 篇，保留来源 ID |
| 结构化候选 | [04-案例JSONL](04-案例JSONL/manual_annotation_cases.annotation_case.v1.candidates.jsonl) | 117 条候选 |
| 人工标注库 | [05-数据库/annotations.db](05-数据库/annotations.db) | 78 documents、117 cases、206 terms、1,478 evidences、343 process steps |

## 20261027 批次

本批有 20 份 DOCX，其中 17 份案例材料对应 062–078，3 份分析体例总结只作格式参考。作者按 DOCX creator 核查；未知作者记为“未知”。作者清单见 [20261027-作者核查.md](20261027-作者核查.md)。

065、069 的原稿修改按用户提供的新 DOCX 同步到转写、案例 JSONL、数据库和线上快照。批次曾于 2026-10-29 部署；当前线上人工 API 返回 78 篇来源与117个案例。

## 状态和维护

数据库查询显示 117 条案例的 `status=草稿`、`certainty=待核`。这是人工撰写材料的当前记录状态，不表示正式审校完成或 V2 gold。

网站通过 `solution/website/scripts/annotation_bridge.py` 从本目录数据库导出 `solution/website/data/annotation-snapshot.json`。数据库更新与快照导出应作为同一流程处理。

旧 `json/full_json/`、`json/ai_json/` 中被新流程完整覆盖的文件和根目录重复原件已删除；保留旧脚本和失败响应供历史追溯。20261007 原始 DOCX 与 ZIP 按 `.gitignore` 规则保留在本地。

新增批次按 [manual-annotation-pipeline skill](../../.agents/skills/manual-annotation-pipeline/SKILL.md) 执行。
