# 工程与运行方案

> 工程入口复核于 2026-10-31。

- `website/`：当前站点、四书机器库 API、Corpus、校读实验和人工标注只读界面。先看 [网站 README](website/README.md) 与 [机器库契约](website/MACHINE-LIBRARY.md)。
- `legacy-db/`：旧 dictionary 兼容库及人工标注导入/共享工具。旧机器 parser 不再构建新四书机器库；见 [旧库边界](legacy-db/README.md)。
- `corpus-standardization/`：原典文本标准化与只读审阅实验；逐个版本带其自身日期和范围，不作为机器 relation parser 的结果。
- `reading-harness-20261026/`、`reading-harness-20261025/`：具体阅读实验和部署快照，保留历史版本，不作为当前 API 契约。
- `../ops/`：Docker、Node 运行依赖和 Railway build contract。
- `../v2/`：独立 V2 工作库与正式人工审校 gate；不等于网站机器库或 D-标注人工库。
