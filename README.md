# 高邮二王考据过程知识库构建及应用

> 工作区口径核查于 2026-10-31。动态数量、状态和来源以 [当前状态](docs/project/05-当前状态与执行评估.md) 中的日期记录为准。

在线展示：[首页](https://gaoyou-demo.up.railway.app/) · [字词与案例](https://gaoyou-demo.up.railway.app/library) · [典籍检索](https://gaoyou-demo.up.railway.app/corpus) · [人工标注库](https://gaoyou-demo.up.railway.app/cases?source=annotation) · [校读实验](https://gaoyou-demo.up.railway.app/reading-lab)

## 项目定位

项目把高邮二王考据中的问题、出处、证据作用、推理和结论整理成可回查的论证路径。重点是让读者看见二王怎样提出问题、使用材料并形成判断；网站、数据库、检索和 AI 是研究环境，不是项目的学术结论。

本项目是王念孙、王引之专题研究整理原型，不面向一般古籍浏览。机器抽取便于发现和组织候选，只有经人工确认的具体案例才可以称为完成的考据整理。

## 当前工作

- [字词与案例库](https://gaoyou-demo.up.railway.app/library)：四部原典共用机器关系库，提供字词关系和案例两种浏览视图。每条记录仍是机器候选，详见 [机器库实现说明](solution/website/MACHINE-LIBRARY.md)。
- [人工标注库](https://gaoyou-demo.up.railway.app/cases?source=annotation)：展示由标注 DOCX 转换的人工撰写材料；原始作者和审校状态仍按各条记录保留。
- [典籍检索](https://gaoyou-demo.up.railway.app/corpus)：检索二王原典和外典；[校读实验](https://gaoyou-demo.up.railway.app/reading-lab) 对照直接校读与引入检索材料后的输出。实验页不能单独证明检索增强提高了考据质量。

## 重要边界

- 机器关系数、页面案例数和人工确认数是不同指标，不能混为学术统计。
- 当前还没有经过统一分类和逐条审核的四书讹误、通假总数。旧库类别、人工 Markdown 标签、V2 子类和新 parser 类型口径不同。
- V2 工作库、人工标注库和公开机器库各自有独立数据与状态；见 [数据库关系](docs/project/06-数据库关系与清理状态.md)。
- 所有当前数量都必须附数据来源和核查日期；历史报告保留为历史证据，不覆盖当前实现。

## 从哪里开始

| 目标 | 入口 |
| --- | --- |
| 理解研究定位 | [项目规划与进展](docs/project/00-项目规划与进展.md) |
| 看阶段状态、数量和下一步 | [当前状态与执行评估](docs/project/05-当前状态与执行评估.md) |
| 理解来源、证据和审核边界 | [架构与证据边界](docs/project/02-架构、证据与数据边界.md) |
| 参与人工案例复核 | [项目与人工审计指南](docs/project/01-项目与人工审计指南.md) |
| 维护网站机器库 | [机器库说明](solution/website/MACHINE-LIBRARY.md) · [网站 README](solution/website/README.md) |
| 处理人工标注材料 | [数据目录](data/README.md) · [D-标注流程](data/D-标注/README.md) |
| 查看旧方案和决策 | [决策记录](docs/project/04-决策记录.md) · [历史研究计划](docs/research-plan.md) |

## 工作区边界

`docs/` 维护当前定位与操作说明；`data/` 保存来源和标注数据；`solution/` 保存网站及工程；`v2/` 保存独立的 V2 审校工作流；`research/` 保存研究记录；`archive/` 保存历史材料；`tmp/` 保存可重建的本地实验与部署快照。

原始文献、用户报告、人工意见、数据库和部署快照按各自权威来源维护。不要用生成候选替换原文，也不要把历史实验副本写成当前运行版本。

README 只承担项目定位、主要入口和关键边界；工程细节、现场指标与历史推导放在对应说明中。
