# 外部原典候选冻结报告（Round 7）

生成日期：2026-08-13。范围：在 Round 6 的公开版本检索基础上，补入史记、孟子注疏、周礼注疏、广雅、春秋繁露、战国策等候选卷册，并为《系辞传》《射义》补充已有候选包的保守匹配入口。本轮仍不登记 external canonical，不改变 evidence 的 `passage_id`、`quote_check`、`source_resolution`，不改变人工 pending 或 gold。

## 结果

当前清单 `v2/data/real_runs/external_edition_fetch_manifest.v1.json` 共 34 个候选包，其中 32 个为 Internet Archive 公共扫描/OCR 候选，2 个为 CText 直接入口受 HTTP 403 阻断的 edition lead。共 191 个候选条目、191 个完整 OCR 文件记录、95 个关联外部来源；扫描 PDF 策略为 `on_match`，由于自动 OCR quote match 为 0，本轮没有下载大体量 PDF；SQLite 行变更为 0。候选 manifest SHA-256 为 `a1ae81a1f1bf599d67f0d92b9936d04a525deff2aac0d7ffc6f5f702a05ce0de`，`.part` 临时文件为 0。

新增或补强的定位入口包括：史记卷四十至卷四十一（《越世家》候选）、卷一百九至卷一百十（《李将军列传》候选）；孟子注疏卷三上至卷三下（《公孙丑》候选）；周礼注疏卷四至卷十五的公开卷段（《疾医》《乡大夫》邻域候选）；广雅卷一至卷十；春秋繁露卷一至卷十七；战国策卷二至卷三十三；以及把《系辞传》挂到周易注疏候选、把《射义》挂到仪礼注疏候选。上述均是 locating candidate，不是底本选择或 canonical passage。

## 覆盖与未覆盖

当前 100 个 external source registry 项中，候选包已关联 95 个；尚未关联的 5 项为“众经音义引仓颉篇”“众经音义引通俗文”“汉成阳灵台碑”“宋玉风赋”“吕氏春秋·乐成”。其中《宋玉风赋》已记录公开网页候选但没有可冻结的 source-specific IA 文件；其余项目本轮没有取得足以登记为本地候选文件的公开底本。它们继续留在 external source resolution queue 的 pending/no-public-match 边界，不以相近典籍或外部网页拼接替代。

## 自动校验

`build_external_evidence_packets.py` 的 `validate_external_edition_candidate_manifest()` 逐文件核验候选包、条目、路径、大小、SHA-256 和临时文件；当前应达到候选包 34/34、条目 191/191、完整文件 191/191、缺失 0、大小不符 0、SHA-256 不符 0、不安全路径 0、`.part` 0、`database_rows_changed=0`。外部 source queue 和 passage queue 仍分别保持 100/100、121/121 的任务覆盖；候选包的 95 个来源引用只进入机器证据包，不直接改变数据库状态。

## 解释口径

`downloaded_candidate` 只表示公开 metadata/OCR 文件已经取得并可按大小和 SHA-256 复核，不表示版本已选定、引文已在对应 canonical passage 中出现，也不表示语义正确。`candidate_ocr_match` 只用于定位；本轮命中为 0，因此没有任何外部引文被提升为 canonical quote passed。外部 canonical 底本计数仍为 0，外部证据仍保持 `quote_check=unchecked`，人工状态仍保持 pending。

## 后续人工入口

机器部分已经把绝大多数外部任务的候选书名、卷段、URL、metadata、OCR 路径、文件 hash 和文本层边界放入可复核包；后续人工只需选择/确认具体版本与文本层，在影印页确认 quote 和 location，决定是否登记 canonical passage，并记录人审事件。未覆盖的五项和所有无 OCR 连续命中的项目不能被机器自动判为错误或正确。
