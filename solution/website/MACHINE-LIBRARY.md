# 机器字词与案例库

机器库单独发布，人工标注数据库和 `data/annotation-snapshot.json` 不参与构建。

## 运行与入口

- `/terms`、`/library`：字词关系视图。
- `/cases`：案例视图。`view=terms|cases` 可切换同一检索结果的分组。旧 `source=main|all|parser` 同样使用新机器库。
- `/cases?source=annotation`：原人工标注入口；既有人工接口保持原样。
- `GET /api/machine/meta`：运行版本、源文件哈希、分层计数。
- `GET /api/machine/search`：`q`、`view`、`match=all|any`、`position=any|source|target`、重复 `work_key`、`type`、`page`；每页十张完整卡。
- `GET /api/machine/detail?id=...`：校读点、原文定位、关系候选及证据。

多词默认在同一关系的两端合集中执行 AND。字词与案例视图具有相同的完整命中主张 ID 集合，各自分组后分页，不能把证据先分页再拼卡。单字查询排除未变化文字和反切标记的偶然命中；有效短语关系仍进入主结果。

本地检索位置筛选默认为 `any`（不限）；`source` 对应原文有序关系的原词／原句，`target` 对应释义／异文。选定一端后，AND 的全部词必须在该端匹配；明确对称的关系没有固定的起点与结果，两端都可匹配。位置筛选在证据分组及分页前执行，普通正文提及仍独立补查。该选项保存到 URL，切换视图、翻页、刷新均保留。此项是只读查询改动，不改写已有机器数据；运行记录中的 `machine_library_sha256` 仍是建库时的代码哈希，不能当成后续查询服务的版本哈希。

顶栏以 `/library` 的“字词与案例”为单一入口，`/terms` 与 `/cases` 保留既有 URL 和默认视图，且导航高亮统一到合并入口。

箭头保留原文关系的有序叙述，不一律表示“校正为”。只有明确对称的关系使用 `↔`；当作、本作、误作等原文措辞保留在证据中。`∅` 表示校勘式中的空位。机器立场判断、候选状态不等于人工作者归属或审校结论。

## 重建

核心实现是 `scripts/relation_parser.py`、`scripts/relation_identity.py`、`scripts/machine_library.py`。源文及词头输入来自被冻结并核对哈希的四书中间库；日志与旧代码备份保存在本地忽略的 ParseBench 目录。

```powershell
python solution/website/scripts/machine_library.py build --help
python solution/website/scripts/machine_library.py build --workers 4
```

构建遍历全部 7,532 个来源段，不受旧案例候选集合限制。原文、原词头、字词形式、关系、证据和有边界的机器校读点分开存储。相同字词跨词头及案例共用实体；同一案例可以关联多个关系，逐条证据保留。不能定位的记录与被驳斥/条件性主张独立补查，不混入主案例数。

构建结果默认写入 `runtime-bundle/machine-library.sqlite3`；旧输出先备份，新输出经过来源哈希、外键和引文回切检查后原子替换。

## 发布

```powershell
python solution/website/scripts/machine_bundle.py pack --db solution/website/runtime-bundle/machine-library.sqlite3 --bundle solution/website/runtime-bundle/machine-library.sqlite3.xz --manifest solution/website/runtime-bundle/machine-library.manifest.json
```

压缩库及清单是可随代码发布的运行输入；原始 SQLite 为本地生成文件。Docker 验证并解压后，运行时只读查询该库。清单记录压缩文件与数据库的字节数、SHA-256、解析器与构库代码版本、输入清单及内容哈希。

Railway 回归须验证实际运行 ID、典型查询、双视图、分页及人工库发布前后相同，不能只凭健康检查或上传成功判断发布完成。回滚使用保留的前一 Railway 部署及对应机器包；不回写人工数据库。

新算法已替代旧机器解析主链：`relation_parser.py → machine_library.py → machine-library.sqlite3 → /api/machine/* → 字词／案例双视图`。主构建不读取旧 dictionary.db，关系身份模块是必需依赖，缺失即报错；机器库缺失则返回不可用，不回退旧库。npm 的 `machine:build`／`machine:pack` 是当前构建和打包入口，旧 `sync:sqlite` 任务已移除。

已删除旧字词混库页面、旧候选实时重算接口 `/api/parser-candidates/*` 及其在 V2 桥接器和前端中的新增兼容层。旧的词典数据库、V2 审校记录和明确历史详情只作档案／审计材料保留，不参与当前机器解析、检索或主结果统计；人工标注接口和数据独立保留。原算法源文件保留供旧数据审计回放，正式机器链不再导入它们。
