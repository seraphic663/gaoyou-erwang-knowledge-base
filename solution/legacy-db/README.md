# 旧 SQLite 与标注导入工具

> 本目录保留历史兼容库和人工标注导入代码。机器字词/案例主链已转到 [网站机器库](../website/MACHINE-LIBRARY.md)。

## 目录角色

- `main/`：旧 `source.txt → parser.py → importer.py → dictionary.db` 管线，原始来源仅为《广雅疏证》。文件保留供旧数据审计和迁移，不用于重建四书机器库。
- `annotation/` 与 `lib/`：标注数据库 schema、导入和共享 SQLite 工具。当前人工数据目录在仓库根 `data/D-标注/`，数据库位于 `05-数据库/annotations.db`。
- `data/dictionary.db`：旧机器库文件；网站的 `sqlite-snapshot.json` 是对应旧快照。当前机器库使用网站 `runtime-bundle/machine-library.sqlite3.xz`。

## 数据库边界

| 数据层 | 当前用途 | 状态说明 |
| --- | --- | --- |
| `dictionary.db` / `sqlite-snapshot.json` | 旧机器目录兼容和对照 | 49 works、3,385 terms、815 cases、7,120 evidences 是 2026-10-31 旧快照计数；passages 为 0 |
| `data/D-标注/05-数据库/annotations.db` | 人工撰写案例与证据的展示/检索库 | 78 documents、117 cases；117 条 status 为草稿、certainty 为待核 |
| `v2/data/real_runs/annotation_v2.db` | 独立 V2 机器/人工审校工作流 | 按 V2 状态和 review gate 管理；不从旧库状态推断 gold |
| `solution/website/runtime-bundle/machine-library.sqlite3.xz` | 当前四书机器关系和案例浏览 | 由新 parser 构建，所有结果是候选数据 |

四者不合并身份。人工标注数据库和快照不得被机器构建覆盖；旧 `dictionary.db` 不作为当前机器库的缺失回退。

## 维护

如变更标注 schema 或导入过程，先检查 `annotation/` 代码及 [D-标注流程](../../data/D-标注/README.md)，导入后再通过 `npm --prefix solution/website run sync:annotation` 导出快照。不要在此目录新建或重新启用旧机器 `sync:sqlite` 发布链。

新四书机器库的构建、manifest、回滚和在线验收见 [MACHINE-LIBRARY.md](../website/MACHINE-LIBRARY.md)。V2 的来源、审核门禁和生产数据库见 [V2 README](../../v2/README.md)。
