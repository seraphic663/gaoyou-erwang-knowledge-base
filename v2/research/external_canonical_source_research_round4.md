# 外部 canonical 底本研究（Round 4）

## 研究结论

本轮针对当前外部待办中尚未形成本地候选文件的来源，检索了《急就篇》《管子·形势解》《礼记·月令》《论语·微子》的公开电子入口和版本线索。结果可以推进“外部来源候选/后续下载任务”，但还不能登记为 V2 的独立 canonical source document：当前环境对 CText 篇章页的直接读取返回 HTTP 403，搜索结果只能作为入口和版本线索；本轮没有下载扫描文件、没有完成文件完整性检查、没有冻结本地 hash，也没有修改 `external_source_registry`、`annotation_evidences.quote_check` 或 human/gold 状态。

本轮本地边界以以下项目产物为准：

- `v2/data/real_runs/workflow_coverage_report.v1.json`：外部 canonical document `0`，外部公开候选 passage `29`，外部 quote passed `0`。
- `v2/data/real_runs/external_evidence_packets_report.json`：外部 source/passage queue 已逐条打包，但证据包仍是机器定位材料。
- `v2/research/external_source_research_round3.md`：此前 100 个外部来源的 Wikisource 候选/搜索线索审计；其结论仍然是公开转录候选不等于选定底本。

## 1. 本轮发现的公开入口

### 1.1 《急就篇》

- [CText《急就篇》](https://ctext.org/jijiupian/zh) 的检索结果标出其电子图书馆底本为《四部丛刊续编》本《急就篇》，并同时列出《天壤阁丛书》本《弟子职正音·弟子职·急就篇直音》。这至少说明“急就篇”不能在没有 edition 字段时被当成唯一文本。
- 本轮直接打开该篇章页时收到 HTTP 403，未取得可本地冻结的完整正文或影印分册。因此仍保持 `external_source_pending` / `edition_status=missing`，不把搜索结果当 quote evidence。
- [维基文库《急就篇》卷四](https://zh.wikisource.org/zh/%E6%80%A5%E5%B0%B1%E7%AF%87/%E5%8D%B7%E5%9B%9B) 和 [《四庫全書本》卷四](https://zh.wikisource.org/zh-hant/%E6%80%A5%E5%B0%B1%E7%AF%87_%28%E5%9B%9B%E5%BA%AB%E5%85%A8%E6%9B%B8%E6%9C%AC%29/%E5%8D%B74) 只作为此前的公开转录候选；不同页面的正文、注释和版本层不能合并为一条 canonical quote。

### 1.2 《管子·形势解》

- [CText《管子·形势解》](https://ctext.org/guanzi/xing-shi-jie/zhs) 的检索结果提供了篇章级机器文本入口，并显示《形势解》的篇章内容。
- [CText《管子》卷一](https://ctext.org/wiki.pl?chapter=427170&if=gb&remap=gb) 的检索结果显示《形势第二》等篇目；但“《管子》正文”“《管子注》”“《管子补注》”是不同文本层，不能仅凭篇名相同自动合并。
- 本轮直接打开 CText 篇章页返回 HTTP 403；没有获取可核验的扫描底本和本地 hash。旧 AI 的“管子注”还存在注家/注本不明问题，所以当前只能建立篇章候选线索，不能把 CText 页面文本写成 external canonical passage。

### 1.3 《礼记·月令》

- [CText《礼记·月令》](https://ctext.org/liji/yue-ling/zh) 提供篇章级入口；本轮直接读取返回 HTTP 403。
- [CText《钦定四库全书》本《礼记大全》](https://ctext.org/library.pl?if=gb&remap=gb&res=5230) 的检索结果明确给出“钦定四库全书·经部四·礼类”、30 卷拆 18 册、浙江大学图书馆来源、CADAL 扫描者及 IA 分册入口，并列出包含《月令》的卷册。这是可继续追踪的影印候选，但《礼记大全》是集说/注释层，不等同于未经选择的《礼记》经文或郑玄注。
- 因而下一步必须先决定要核验的是经文、郑玄注、孔颖达疏还是《礼记大全》集说，再下载相应卷册；不能用经文命中替代注文命中。

### 1.4 《论语·微子》

- [CText《论语·微子》](https://ctext.org/analects/wei-zi/zh) 提供篇章入口；本轮直接读取返回 HTTP 403。
- [CText《论语集解》Library 条目](https://ctext.org/wiki.pl?if=gb&remap=gb&res=676421) 的检索结果明确标出《四部丛刊初编》本，并说明该数字资料是对相应底本影印本进行 OCR 自动建立，文字可能有错字，应回看图像核对。这使它适合作为“明确 edition 的影印/OCR 候选”，但尚未下载到本地，不能直接登记 canonical。
- [CText《论语》Library](https://ctext.org/library.pl?if=en&node=1081&remap=gb) 还列出《古逸丛书》本《论语》《阮元校刻十三经注疏》本《论语注疏》和《四部丛刊初编》本《论语集解》等不同版本；因此旧 AI 仅写“《论语·微子》”时，仍需先确定证据所指的文本层。

## 2. 当前可写入 V2 的内容与不可写入内容

可以写入或保留为机器候选的内容：

1. 稳定的作品/篇名 URL、检索时间、外部站点、搜索结果中的 edition 描述和“待下载”状态。
2. 已登记的 Wikisource 冻结页面及其 revision/raw hash；它们保持 `external_public_candidate` / `canonical_status=unknown`。
3. CText Library 中明确标出底本、馆藏来源、扫描者和 IA 分册的条目链接，作为后续下载任务的 source candidate，不作为本地 source document。

不能写入 canonical 或 quote passed 的内容：

1. CText 搜索摘要、403 页面响应、搜索引擎摘要或未下载的 IA 链接。
2. 没有确定经文/注释层的“《礼记》”“《论语》”“《管子注》”泛标签。
3. Wikisource 协作转录、OCR 文本或同一篇不同版本的相似句，若没有与所选底本一致的扫描/图像和本地 hash。

## 3. 下一步自动化动作

1. 对 CText Library 给出的 IA 分册 URL 做受控解析，只保存下载成功、文件大小非零、卷次/篇名可识别的文件；下载失败则保留 URL 和失败原因，不把它变成 canonical。
2. 为每个下载文件生成 `external_source_candidate` 记录：作品、篇章、edition、馆藏/扫描者、URL、下载时间、文件 hash、文件类型和完整性检查结果。
3. 从 OCR/文本文件生成独立 `external_passage_candidate`，保留页码/卷次/字符范围；以扫描图像为核验依据，不以 OCR 连续命中单独通过。
4. 只有在人工选择了底本、确认图文一致并提交受控 resolution event 后，才允许把外部来源从 pending/candidate 推进到 verified；本轮不执行这一人工动作。

本轮因此新增的是“可继续获取的外部入口和明确失败边界”，不是 canonical 原典本身。它与 V2 workflow 的第 7 步相接：为人工审校准备可追溯材料，但不缩短 quote、hash、版本和 human/gold 的真实边界。
