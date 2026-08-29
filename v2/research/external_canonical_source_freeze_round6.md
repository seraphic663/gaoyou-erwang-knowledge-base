# 外部原典候选冻结报告（Round 6）

生成日期：2026-08-13。范围：为 V2 外部来源解析队列准备可追溯的版本候选、卷册扫描、OCR 定位材料和文件完整性记录；本轮不登记 external canonical，不改变 evidence 的 `passage_id`、`quote_check`、`source_resolution`，不改变人工 pending 或 gold。

## 结果

本轮清单 `v2/data/real_runs/external_edition_fetch_manifest.v1.json` 共 28 个候选包，其中 26 个为 Internet Archive 公共扫描候选，2 个为 CText 直接入口受 HTTP 403 阻断的 edition lead。共 171 个候选条目、335 个完整 OCR/PDF 文件记录、83 个关联外部来源；自动 OCR quote match 为 0，SQLite 行变更为 0。

冻结产物位于 `v2/data/external_sources/edition_candidates/`，汇总 manifest 位于 `v2/data/real_runs/external_edition_candidate_manifest.v1.json`。每个可下载条目保存 Internet Archive metadata、DjVu OCR；当前与外部引文存在关联的条目同时保存 PDF 影印候选。下载采用临时文件、预期大小和原子改名顺序，最终 `.part` 文件数为 0。

## 主要来源与版本边界

- 《说文解字》《玉篇》《急就篇》使用浙江大学图书馆相关 Internet Archive 公共扫描候选，例如 [说文解字 metadata](https://archive.org/metadata/06050615.cn) 和 [说文解字 PDF](https://archive.org/download/06050615.cn/06050615.cn.pdf)。这些是书影/文本候选，不是已确认的项目 canonical 底本。
- 《管子校正》保留戴望 1873 年校正层候选，并与 Siku 《管子》候选分开；二者不能自动替代旧 AI 中的《管子注》或无版本书名。
- 《礼记大全》保留为四库编纂/评注层候选，不自动当作 plain 礼记、郑玄注或卢植注；[Internet Archive 礼记卷册 metadata](https://archive.org/metadata/06048491.cn) 只支持候选卷册和版本线索。
- 《春秋左传注疏》《论语注疏》《尚书注疏》《周易注疏》《公羊传注疏》《穀梁传注疏》《仪礼注疏》等均按 text/commentary bundle 保存。候选卷册可以帮助人工定位，却不自动决定旧引文要的是经文、传、注、疏还是其他层。
- 《国语》《庄子》《尔雅》《方言》《经典释文》《集韵》《齐民要术》《说苑》《汉书》《后汉书》《淮南鸿烈》《诗经集传》《大戴礼记》等按各自 candidate_id 和卷册保存；混合卷册不会合并成一个“完整 canonical 版本”。
- CText 的 [《礼记·月令》入口](https://ctext.org/liji/yue-ling/zh) 和 [《论语·微子》入口](https://ctext.org/analects/wei-zi/zh) 在本环境直接请求返回 403，因此只保留 URL、edition lead 和响应 hash；[礼记大全 Library metadata](https://ctext.org/library.pl?if=gb&remap=gb&res=5230) 与 [论语集解 Library lead](https://ctext.org/library.pl?if=gb&res=77340) 不能冒充已下载底本。

## 自动校验

`build_external_evidence_packets.py` 的 `validate_external_edition_candidate_manifest()` 已逐文件核验：候选包 28/28，条目 171/171，完整文件 335/335，缺失 0，大小不符 0，不安全路径 0，`.part` 0，`database_rows_changed=0`。外部 evidence packet 覆盖 source queue 100/100、passage queue 121/121；候选文件存在性和预期大小复核通过，候选包引用到 83 个 source 和 96 条 evidence。

## 解释口径

`downloaded_candidate` 只表示公开文件已经冻结并能被完整性复核，不表示版本已选定、引文已在对应 canonical passage 中出现，也不表示语义正确。`candidate_ocr_match` 只用于检索和定位；本轮没有把任何 OCR 命中写成 canonical quote passed。外部 canonical 底本计数仍为 0，外部证据仍保持 `quote_check=unchecked`，人工状态仍保持 pending。

## 后续人工入口

后续审校不需要重新找卷册，主要只需对每条外部任务选择/确认目标版本与文本层、在影印页确认 quote 和 location、决定是否把候选 passage 登记为 canonical，并记录人审事件。未能由机器安全决定的《吕氏春秋》、诸经音义、宋玉赋、广雅及其余未覆盖版本仍保留在外部解析队列，不用候选扫描伪造结论。
