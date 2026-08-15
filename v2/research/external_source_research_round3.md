# 外部来源公开页面研究（Round 3）

> 研究性质：只读外部检索与报告。没有修改 SQLite、代码、external source queue、external passage queue、manifest 或 review task 文件；本文件是本轮唯一新增交付物。
>
> 快照说明：本报告记录的是 2026-08-13 13:20 的 80 条外部证据检索快照。随后主流程在 13:41 起按同一来源边界重跑并纳入 41 条 `secondary_citation_match`，当前 manifest 已扩展为 121 条、当前 hash 为 `26bd49e0c41bc1ba2887709d17ef8aa4383861bf564ff02be606ce64bc5d521d`；因此本报告中的 `6/8/66` 和旧 hash 是研究时点记录，不是当前生产统计。当前生产统计以 `external_public_candidate_manifest.json`、`external_evidence_packets_report.json` 和 `v2_validation_report.json` 为准。

- 检索时间：2026-08-13 13:20（Asia/Shanghai；报告写入后仅做文件复核）
- 审计对象：当前 `external_source_resolution_queue.edition.v1.jsonl` 的 100 个来源；重点复核 manifest 中 6 个 `candidate_found`/queue `candidate_available` 来源和 8 个 `search_hit_only` 来源。
- manifest：`v2/data/real_runs/external_public_candidate_manifest.json`；SHA-256 `57492f8f18723abbad454277a800542e440274c22426a79580bb22b961518a0d`。
- source queue：`v2/data/real_runs/queues/external_source_resolution_queue.edition.v1.jsonl`；SHA-256 `861e57d0329d258558223233f8217dd0f34723d6a79e945d7097332873b0bc15`。
- 任务快照（只读辅助逐项取 quote）：`v2/data/real_runs/review_tasks/external_source_resolution.review_task.v1.jsonl`；报告写入前曾为 `88280e753d7ac300d6ad2e68b30174a6f33b95b0dbb9809b493379007ca83c9f`，随后被并发的候选抓取进程改写；最终复核 hash 为 `cc42593894d6095769957f5cbde020b413ee6fe8eaea6a89d7359826196a5e7a`。

## 1. 结论先行

- 100 个 source queue：`candidate_available=6`、`pending=8`、`no_public_match=86`；本轮没有把任何一项改写为 `verified`。
- manifest 的 80 条外部证据记录：`candidate_found=6`、`search_hit_only=8`、`no_public_match=66`；共有 26 个已冻结 Wikisource 页面、15 个机器连续文本候选。
- 6 个 `candidate_available` 来源均能从冻结页面得到可复核的文本片段，但它们仍只有 `Wikisource public transcription; edition unresolved`；页面 revision 是版本定位线索，不是所引原典的选定底本。
- 本轮新增可复核发现：`external:013641580de28101` 在《春秋左傳正義/卷51》的冻结文本中出现对应句（引文的简体字转为页面繁体字后连续命中）；`external:d8e70ea81ba95f1a` 在官方 Wikisource《仪礼/乡射礼》页面出现“主人以宾揖，先入”；`external:1a34ea15bc079eb2` 的第二条 quote“吾未尝以就公室”也在同一已冻结页面出现，但旧 manifest 没有把这个 passage candidate 绑定到第二条 evidence。
- `《礼记·乐记》`、`《礼记·祭统》`、`急就篇`、`礼记·月令`、`《礼记·檀弓》郑玄注`、`《左传·襄公二十年》` 的若干页面只有分句、正文/注文、二次引用或相近文字，不能把整条 AI quote 写成“原典连续命中”。
- 结论边界：本轮没有 canonical quote passed、没有 external source verified、没有 quote_check 变更；新增发现只进入本报告，等待后续人工/受控队列决策。

## 2. 检索口径与失败边界

1. 优先使用 Wikisource 的公开页面、页面 revision 元数据和 MediaWiki API URL；同时用 CText/原始文本页面作版本与篇名交叉定位，不把搜索引擎摘要当原典。
2. 对已冻结 Wikitext，区分 `normalized_contiguous`（仅去标点/空白并使用项目已有小范围简繁定位）与“正文/注文分别出现”“二次引文”“只命中近似句”。后者均不是 canonical quote passed。
3. 本轮尝试再次访问 Wikisource API 时收到 `You are making too many requests to the API`（HTTP 429/速率限制）。因此新页面的 revision 未强行猜测；已有页面的 revision、timestamp、raw SHA-256 以 manifest 冻结记录为准，新增页面只记录稳定页面 URL和“revision 未取得”。
4. `Wikisource public transcription`、`四库全书本`页面标题和 CText 版本列表，都不能单独证明当前 evidence 使用的印本、底本、影印页或校勘层次；这些只构成 candidate/定位证据。

## 3. 六个 candidate_available 来源的逐项复核

| source id | quote / passage | 页面与 revision | 版本/edition | 片段判定与边界 |
|---|---|---|---|---|
| `external:470164fd8f443521` | `忿数者，狱之所由生也；距谏者，虑之所以塞也` | [大戴禮記/子張問入官](https://zh.wikisource.org/w/index.php?oldid=2703721)；revid `2703721`，2026-04-20；另有 [四庫全書本/卷08](https://zh.wikisource.org/w/index.php?oldid=548496)，revid `548496`，2016-10-04。 | Wikisource 转录；另一个页面标题标示四库全书本，具体影印底本未锁定。 | 两个冻结文本均出现连续对应片段；可复核 candidate，不能升级 canonical。 |
| `external:1a34ea15bc079eb2` | `昔者吾有斯子也，吾以将为贤人也`；另有 `吾未尝以就公室` | [禮記/檀弓下](https://zh.wikisource.org/w/index.php?oldid=2346897)；revid `2346897`，2023-12-21；raw SHA `c9ac8d67a37aaa7a3f5ad10a5b75d4cf0476d68388449b1ddb53010dd13f44fa`。 | Wikisource 转录，edition 未解析。 | 第一条是 manifest 的连续命中；本轮在同一冻结页面发现第二条也连续出现，但它在旧 manifest 中仍是 `no_public_match`，仅报告，不改队列。 |
| `external:cc9f0a75c9b4b295` | `温润而泽，仁也；缜密以栗，知也` | [禮記/聘義](https://zh.wikisource.org/w/index.php?oldid=2346520)；revid `2346520`，2023-12-21；raw SHA `8fb93a3fa0ad8c5d1d83c04ba8498436940d619a932840702418163b99315595`。 | Wikisource 转录；篇名可定位，传本/底本未选定。 | 在孔子论玉的完整语境中连续命中（页面繁体字）；quote 可复核但不是版本核验。 |
| `external:254bfba806f192fb` | `宾入大门而奏《肆夏》示易以敬也` | [禮記正義/25](https://zh.wikisource.org/w/index.php?oldid=7904391)；revid `7904391`，2026-06-28；另有 [四庫全書本/卷25](https://zh.wikisource.org/w/index.php?oldid=544447) 与 [日講禮記解義/卷28](https://zh.wikisource.org/w/index.php?oldid=548570)。 | 正义、四库、日讲礼记解义是不同文本层，不可合并成一个 edition。 | 三个候选页面都有相应连续片段；原始 quote 在页面中以繁体/标点形式出现，仍保持 candidate。 |
| `external:070ad5cdcb5ba91e` | `悛悛如鄙人，口不能道辞。` | [史記/卷109](https://zh.wikisource.org/w/index.php?oldid=1765440)，revid `1765440`，2020-02-03；另有 [史記三家註/卷109](https://zh.wikisource.org/w/index.php?oldid=2514779)，revid `2514779`，2025-01-06；另有《史記正義》及两种《史記集解》revision，见 manifest。 | 普通《史记》、三家注、四库正义/集解是不同版本或注本候选。 | 五个冻结页面均可在太史公曰语境中定位连续片段；不能据此决定旧 AI 引文对应哪一个版本/注层。 |
| `external:6242169e40e87889` | `山川所以儐鬼神也。` | [禮記/禮運](https://zh.wikisource.org/w/index.php?oldid=2626644)，revid `2626644`，2025-11-30；另有 [禮記注疏/卷22](https://zh.wikisource.org/w/index.php?oldid=544439) 和 [日講禮記解義/卷25](https://zh.wikisource.org/w/index.php?oldid=548564)。 | 礼记正文、礼记注疏、日讲解义不可混为同一底本。 | 三个页面均出现相应连续片段；页面间存在繁体、标点和注疏层差异，只能做 candidate locating。 |

这 6 项的共同结论是：`candidate_available` 代表“有可复核公开文本候选”，不是“外部来源 verified”。

## 4. 八个 search_hit_only 来源的 Round3 复核

| source id | quote | 公开页面与版本信息 | 本轮判定 |
|---|---|---|---|
| `external:d8e70ea81ba95f1a` | `主人以宾揖` | Wikisource [仪礼/乡射礼](https://zh.wikisource.org/zh-hans/%E5%84%80%E7%A6%AE/%E9%84%89%E5%B0%84%E7%A6%AE) 的公开页面检索片段明确显示“主人以宾揖，先入”。本轮 API 受限，未取得该页面 revision。 | 新增公开页面连续命中；页面版本、底本和原始图像未核验。旧 manifest 候选是《仪礼/特牲馈食礼》，该页面本身未命中，不能把错误篇名自动改成乡射礼。 |
| `external:013641580de28101` | `公以告臧孙，臧孙以难。告郈孙，郈孙以可，劝` | [春秋左傳正義/卷51](https://zh.wikisource.org/w/index.php?oldid=7910478)，revid `7910478`，2026-07-28；manifest 冻结 raw page。 | 在冻结文本中出现 `公以告臧孫，臧孫以難……告郈孫，郈孫以可，勸`；属于繁简/标点变体后的直接候选命中。旧有限字符映射把它留在 `search_hit_only`，本报告记录新发现，不写 queue。 |
| `external:daf036c0c547934d` | `赋《常棣》之七章以卒` | [春秋左傳要義/卷16](https://zh.wikisource.org/w/index.php?oldid=761331)，revid `761331`，2016-10-24；页面有“二十年季武子如宋赋常棣之七章，复命公享之”等相关叙述。 | 相关句命中，但不是 quote 原文：页面是“复命公享之”，未出现整条“以卒”；保持未通过。 |
| `external:0e4af81ea01d4bc8` | `治世之音安以乐，乱世之音怨以怒，亡国之音哀以思` | [禮記/樂記](https://zh.wikisource.org/w/index.php?oldid=2346508)，revid `2346508`，2023-12-21；另有 [禮記注疏/卷37](https://zh.wikisource.org/w/index.php?oldid=544488)。 | 页面分别有三句，但中间各有“其政和/其政乖/其民困”等文字；AI quote 把非连续句段拼成一条，不能标记整条 quote 命中。 |
| `external:6c8f5a25fbcf9036` | `以與已字本同` | manifest 候选 [纂圖互註禮記/卷第三](https://zh.wikisource.org/w/index.php?oldid=2652452)，revid `2652452`，2026-02-27；该冻结 raw 文件没有可用正文内容。Wikisource [經傳釋詞](https://zh.wikisource.org/wiki/%E7%B6%93%E5%82%B3%E9%87%8B%E8%A9%9E) 检索到相关郑注引文，但它是王氏二次引用，不是郑玄注底本。 | 没有本轮可独立复核的外部原典连续片段；相关二次引文不能替代 canonical source。 |
| `external:acb1ffa71c2b89f3` | `对扬以辟之勤大命，施于烝彝鼎`；另有 `诚信之谓尽，尽之谓敬` | [禮記正義/49](https://zh.wikisource.org/w/index.php?oldid=2399629)，revid `2399629`，2024-04-27。 | 页面有“对扬以辟之”以及“勤大命，施于烝彝鼎”，但中间夹有注疏解释；整条 quote 不连续。另一条未在本轮得到稳定直接页面命中。 |
| `external:f602917bee5b892e` | `痂疕疥癘癡聾盲；痂，創上甲也。` | Wikisource [急就篇/卷四](https://zh.wikisource.org/zh/%E6%80%A5%E5%B0%B1%E7%AF%87/%E5%8D%B7%E5%9B%9B) 检索到“痂疕疥癘癡聾盲”；另有 [四庫全書本/卷4](https://zh.wikisource.org/zh-hant/%E6%80%A5%E5%B0%B1%E7%AF%87_%28%E5%9B%9B%E5%BA%AB%E5%85%A8%E6%9B%B8%E6%9C%AC%29/%E5%8D%B74) 检索到“痂創上甲也”。两页 revision 未取得。 | 两个片段分别来自正文/注释或不同页面，不能作为一条连续 canonical quote；属于新增 partial hit。 |
| `external:c3def6d236981f13` | `命理瞻傷察創；創之淺者曰傷` | [欽定禮記義疏/卷23](https://zh.wikisource.org/w/index.php?oldid=764013)，revid `764013`，2016-10-24。 | 页面正文有“命理瞻傷察創”，郑玄注另有“創之淺者曰傷”；正文与注文分层，整条 quote 不连续。 |

因此，8 个 `search_hit_only` 中，当前最值得进入下一轮受控候选决策的是 `013...` 与 `d8e...`；但二者仍不能直接写成 canonical。

## 5. 100 个来源逐项审计表

下表覆盖 source queue 的全部 100 行。`no_public_match`/`pending` 行的“无页面/无命中”是本轮研究结果，不是删除、忽略或 canonical 否定；它们仍保留在 queue 中等待后续身份解析或人工核查。`manifest/quote status` 为空，表示该 source 在当前 80 条 manifest evidence 中没有对应条目，而不是“没有证据存在”。
| # | source id | work | queue | evidence | manifest/quote status | quote (truncated) |
|---:|---|---|---|---:|---|---|
| 1 | `external:470164fd8f443521` | 《大戴礼·子张问入官》 | `candidate_available` | 1 | `candidate_found` | 忿数者，狱之所由生也；距谏者，虑之所以塞也 |
| 2 | `external:1a34ea15bc079eb2` | 《礼记·檀弓》 | `candidate_available` | 2 | `candidate_found,no_public_match` | 昔者吾有斯子也，吾以将为贤人也；吾未尝以就公室 |
| 3 | `external:cc9f0a75c9b4b295` | 《礼记·聘义》 | `candidate_available` | 1 | `candidate_found` | 温润而泽，仁也；缜密以栗，知也 |
| 4 | `external:254bfba806f192fb` | 《礼记·郊特牲》 | `candidate_available` | 1 | `candidate_found` | 宾入大门而奏《肆夏》示易以敬也 |
| 5 | `external:070ad5cdcb5ba91e` | 史记·李将军列传 | `candidate_available` | 1 | `candidate_found` | 悛悛如鄙人，口不能道辞。 |
| 6 | `external:6242169e40e87889` | 礼记·礼运 | `candidate_available` | 1 | `candidate_found` | 山川所以儐鬼神也。 |
| 7 | `external:d8e70ea81ba95f1a` | 《仪礼·乡射礼》 | `pending` | 1 | `search_hit_only` | 主人以宾揖 |
| 8 | `external:013641580de28101` | 《左传·昭公二十五年》 | `pending` | 1 | `search_hit_only` | 公以告臧孙，臧孙以难。告郈孙，郈孙以可，劝 |
| 9 | `external:daf036c0c547934d` | 《左传·襄公二十年》 | `pending` | 1 | `search_hit_only` | 赋《常棣》之七章以卒 |
| 10 | `external:0e4af81ea01d4bc8` | 《礼记·乐记》 | `pending` | 1 | `search_hit_only` | 治世之音安以乐，乱世之音怨以怒，亡国之音哀以思 |
| 11 | `external:6c8f5a25fbcf9036` | 《礼记·檀弓》郑玄注 | `pending` | 1 | `search_hit_only` | 以與已字本同 |
| 12 | `external:acb1ffa71c2b89f3` | 《礼记·祭统》 | `pending` | 2 | `no_public_match,search_hit_only` | 对扬以辟之勤大命，施于烝彝鼎；诚信之谓尽，尽之谓敬。 |
| 13 | `external:f602917bee5b892e` | 急就篇 | `pending` | 1 | `search_hit_only` | 痂疕疥癘癡聾盲；痂，創上甲也。 |
| 14 | `external:c3def6d236981f13` | 礼记·月令 | `pending` | 1 | `search_hit_only` | 命理瞻傷察創；創之淺者曰傷。 |
| 15 | `external:8dfd1c062a931f5a` | 《书·大诰》某氏传 | `no_public_match` | 1 | `no_public_match` | 已！予惟小子！ |
| 16 | `external:11f2fbee20be6ac6` | 《书·尧典》 | `no_public_match` | 1 | `no_public_match` | 以亲九族 |
| 17 | `external:1efd7b5b088f5c84` | 《书·康诰》 | `no_public_match` | 1 | `no_public_match` | 已！女惟小子！ |
| 18 | `external:7784b4b6e9ec5644` | 《书·梓材》 | `no_public_match` | 1 | `no_public_match` | 已！若兹监！ |
| 19 | `external:f6e2137567ff87fb` | 《书·洛诰》 | `no_public_match` | 2 | `no_public_match` | 已！女惟冲子！ |
| 20 | `external:54249af3e0d249fa` | 《书·牧誓》 | `no_public_match` | 1 | `no_public_match` | 俾暴虐于百姓，以奸宄于商邑 |
| 21 | `external:d961824e0fbf7e4e` | 《书·盘庚》 | `no_public_match` | 1 | `no_public_match` | 尔忱不属，惟胥以沈 |
| 22 | `external:c9d3f8f1b2e90a73` | 《书·金縢》 | `no_public_match` | 1 | `no_public_match` | 天大雷电以风 |
| 23 | `external:ae2dfc2b943173ea` | 《仪礼·大射仪》 | `no_public_match` | 1 | `no_public_match` | 以耦左还 |
| 24 | `external:53315f76b7e50407` | 《公羊传·庄公二十四年》 | `no_public_match` | 1 | `no_public_match` | 戎众以无义 |
| 25 | `external:dff47c336e8a2cac` | 《吕氏春秋·乐成》 | `no_public_match` | 1 | `no_public_match` | 故民不可与虑化举始，而可以乐成功 |
| 26 | `external:3e901111216d9db9` | 《吕氏春秋·精谕》与《淮南·道应》 | `no_public_match` | 1 | `no_public_match` | 人可与微言乎”与“人可以微言 |
| 27 | `external:3419d825b1d7f8d9` | 《吴语》 | `no_public_match` | 2 | `no_public_match` | 昔楚灵王不君，其臣箴谏以不入；譬諸疾疥癬也。 |
| 28 | `external:593560252b9404b6` | 《周语》引《汤誓》 | `no_public_match` | 1 | `no_public_match` | 余一人有罪，无以万夫 |
| 29 | `external:8e2c88e55cbe430a` | 《大戴礼·曾子制言》 | `no_public_match` | 1 | `no_public_match` | 富以苟，不如贫以誉；生以辱，不如死以荣 |
| 30 | `external:39d4251f8580122f` | 《射义》引诗 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 31 | `external:205014307b3ea5fd` | 《尔雅》 | `no_public_match` | 2 | `—` | 任务材料未给出外部 quote |
| 32 | `external:84d680e7512cac8b` | 《左传·文公五年》 | `no_public_match` | 1 | `no_public_match` | 嬴曰：‘以刚。’ |
| 33 | `external:2ee2b51fd39c6b47` | 《左传·昭公二十年》 | `no_public_match` | 1 | `no_public_match` | 济其不及，以泄其过 |
| 34 | `external:6ca38523a3372bc8` | 《左传·昭公十一年》 | `no_public_match` | 1 | `no_public_match` | 桀克有缗以丧其国，纣克东夷而陨其身 |
| 35 | `external:2f630c866c1e5f53` | 《左传·襄公二十九年》 | `no_public_match` | 1 | `no_public_match` | 乐氏其以宋升降乎？ |
| 36 | `external:f82fc3379647f9aa` | 《左传·闵公二年》 | `no_public_match` | 1 | `no_public_match` | 亲以无灾，又何患焉 |
| 37 | `external:49c77aa81fc0c574` | 《广雅》 | `no_public_match` | 1 | `no_public_match` | 以，与也 |
| 38 | `external:e9942b49bb30b460` | 《庄子·养生主》 | `no_public_match` | 1 | `no_public_match` | 已而为知者，殆而已矣 |
| 39 | `external:e76a8d8af96b971b` | 《庄子·庚桑楚》 | `no_public_match` | 1 | `no_public_match` | 已！我安逃此而可？ |
| 40 | `external:b947c4a6eb3a29fa` | 《庄子·齐物论》 | `no_public_match` | 1 | `no_public_match` | 已而不知其然谓之道 |
| 41 | `external:e08b63cd94b33014` | 《易·剥》初六、六二、六四 | `no_public_match` | 1 | `no_public_match` | 剥床以足、以辨、以肤 |
| 42 | `external:8ce605b5541c5448` | 《易·同人彖传》 | `no_public_match` | 1 | `no_public_match` | 文明以健，中正而应 |
| 43 | `external:a325362d923ff84f` | 《易·复》上六 | `no_public_match` | 1 | `no_public_match` | 用行师，终有大败，以其国君 |
| 44 | `external:edf0a8a16db346dd` | 《易·小畜》九五虞翻注 | `no_public_match` | 1 | `no_public_match` | 富以其邻 |
| 45 | `external:87d9afdaa90894a3` | 《易·泰》六四 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 46 | `external:ffe2305cea6346f4` | 《易·泰》初九 | `no_public_match` | 1 | `no_public_match` | 拔茅茹，以其汇 |
| 47 | `external:a507727f5b39ad11` | 《易·鼎》初六 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 48 | `external:cda01e8a80327403` | 《晋语》 | `no_public_match` | 1 | `no_public_match` | 狐偃惠以有谋，赵衰文以忠贞，贾佗多识以恭敬 |
| 49 | `external:7c26b385e6e57398` | 《汉书·刘向传》注 | `no_public_match` | 1 | `no_public_match` | 以，由也 |
| 50 | `external:42f56de1c48af001` | 《汉书·宣帝纪》颜师古注 | `no_public_match` | 1 | `no_public_match` | 已，语终辞也 |
| 51 | `external:e63058f135f3f588` | 《汉书·翟义传》颜师古注 | `no_public_match` | 1 | `no_public_match` | 熙，叹辞 |
| 52 | `external:acc0d0e3f3c42d2e` | 《淮南·道应》 | `no_public_match` | 1 | `no_public_match` | 已虽无除其患... |
| 53 | `external:53b12a56c1e7b615` | 《淮南子·权勋》与《说苑·敬慎》 | `no_public_match` | 1 | `no_public_match` | 不谷无与复战矣”与“吾无以复战矣 |
| 54 | `external:4948ef1e9c22e8c3` | 《燕策》与《史记·燕世家》 | `no_public_match` | 1 | `no_public_match` | 得贤士与共国”与“得贤士以共国 |
| 55 | `external:f4236b681959fc8b` | 《玉篇》 | `no_public_match` | 4 | `no_public_match` | 以，为也 |
| 56 | `external:12c1b2ae0312e390` | 《礼记·檀弓》卢植注 | `no_public_match` | 1 | `no_public_match` | 已者，辞也 |
| 57 | `external:ecdbabb6f9c9fa8a` | 《管子·形势》 | `no_public_match` | 1 | `no_public_match` | 訾讆之人，勿与任大，谟臣者可以远举，顾忧者可与致道 |
| 58 | `external:e34b8c0c6bc12c88` | 《系辞传》 | `no_public_match` | 1 | `no_public_match` | 蓍之德圆而神，卦之德方以知 |
| 59 | `external:f74c802efb4df58c` | 《论语·为政》 | `no_public_match` | 1 | `no_public_match` | 季康子问使民敬忠以劝 |
| 60 | `external:09443c3e6afd3199` | 《论语·微子》 | `no_public_match` | 1 | `no_public_match` | 而谁以易之 |
| 61 | `external:71577bed5bc1a07a` | 《诗·击鼓》 | `no_public_match` | 1 | `no_public_match` | 不我以归 |
| 62 | `external:b887e31fd953eb17` | 《诗·小明》 | `no_public_match` | 1 | `no_public_match` | 神之听之，式谷以女 |
| 63 | `external:31195980b8c109c4` | 《诗·旄邱》 | `no_public_match` | 1 | `no_public_match` | 何其处也，必有与也。何其久也，必有以也 |
| 64 | `external:aaf9d8191c2fb976` | 《诗·桑柔》 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 65 | `external:dc5ac9a90db13b5f` | 《诗·江有汜》 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 66 | `external:dc1b2e45d8afebf4` | 《诗·瞻卬》 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 67 | `external:78195fc7f00db94f` | 《越语》与《史记·越世家》 | `no_public_match` | 1 | `no_public_match` | 节事者与地”与“节事者以地 |
| 68 | `external:c1b6ad2b3b97a8c9` | 《齐策》 | `no_public_match` | 1 | `no_public_match` | 臣之妻私臣，臣之妾畏臣，臣之客欲有求于臣，皆以美于徐公 |
| 69 | `external:23cbb13576cc52d9` | 众经音义引仓颉篇 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 70 | `external:8cdc1c668e4f13d7` | 众经音义引通俗文 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 71 | `external:74564004c45c713d` | 史记·越世家 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 72 | `external:ed5963b2e62a70dc` | 后汉书·鲜卑传 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 73 | `external:43ff9abf9672cf62` | 周官·乡大夫 | `no_public_match` | 1 | `no_public_match` | 宾，敬也。 |
| 74 | `external:9fa5a53474a9d0cd` | 周官·疾医 | `no_public_match` | 1 | `no_public_match` | 夏時有癢疥疾。 |
| 75 | `external:469c5ccd5c500d35` | 孟子·公孙丑 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 76 | `external:dc218d6015fe43c6` | 宋玉风赋 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 77 | `external:0248a59eb0263c53` | 左传僖二十二年 | `no_public_match` | 1 | `no_public_match` | 君子不重傷。 |
| 78 | `external:f0820d3b563ac3d6` | 左传襄十九年 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 79 | `external:08b95d674f60a75d` | 广雅·释言 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 80 | `external:ea3bc829642592e2` | 方言 | `no_public_match` | 1 | `no_public_match` | 稟、浚，敬也。秦晋之间曰稟，齐曰浚，吴楚之閒自敬曰稟。 |
| 81 | `external:e79dad3df9b7c10c` | 春秋繁露·五行顺逆 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 82 | `external:f5dda673427458a0` | 汉书·赵充国传 | `no_public_match` | 1 | `no_public_match` | 将军士寒手足皸瘃；瘃，寒創也。 |
| 83 | `external:c9f37e91795e9c89` | 汉成阳灵台碑 | `no_public_match` | 1 | `no_public_match` | 齐革精诚。 |
| 84 | `external:36fe94ec8eea077e` | 爾雅 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 85 | `external:288ccd898a049ace` | 礼记·大学 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 86 | `external:5fd9fd6fab996cd0` | 礼记·曲礼 | `no_public_match` | 2 | `—` | 任务材料未给出外部 quote |
| 87 | `external:03332422ff166657` | 礼记·表记 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 88 | `external:178921ce00bd6675` | 穀梁传文十一年 | `no_public_match` | 1 | `no_public_match` | 不重創。 |
| 89 | `external:a9c945b82cf3c3a3` | 管子·地员 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 90 | `external:14c0e8bead2c6969` | 管子·形勢解 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 91 | `external:6630620b4c00837a` | 管子注 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 92 | `external:1d5a3d1f7d577b8d` | 经典释文 | `no_public_match` | 1 | `no_public_match` | 儐，皇音宾，敬也。 |
| 93 | `external:89cbcfaf933cd1dc` | 论语·乡党 | `no_public_match` | 1 | `no_public_match` | 恂恂如也，似不能言者；王肃注：恂恂，温恭之貌。 |
| 94 | `external:df197dbd13ca053b` | 诗经·召南·采蘋 | `no_public_match` | 1 | `no_public_match` | 有齐季女；齐，敬也。 |
| 95 | `external:bb97deed2278849a` | 诗经·商颂·殷武 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 96 | `external:1151020f38da5acd` | 诗经·大雅·常武 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 97 | `external:58c1d0d954524cd8` | 诗经·大雅·韩奕 | `no_public_match` | 1 | `no_public_match` | 虔共尔位。 |
| 98 | `external:d418a82b6f8ced81` | 说文解字 | `no_public_match` | 13 | `no_public_match` | 宾，所敬也。；敬，肃也。从攴苟。苟，自急敕也。从羊省，从包省，从口，口犹慎言也。从羊，与义、善、美同意。；㥛，谨重皃。；恮，谨也。 |
| 99 | `external:1d3e421d15914a3e` | 集韻 | `no_public_match` | 1 | `—` | 任务材料未给出外部 quote |
| 100 | `external:41147de1dc438eb8` | 齐民要术 | `no_public_match` | 1 | `no_public_match` | 治羊挾蹄方。 |

## 6. 结果对 workflow 的意义

- 本轮完成的是外部来源的“可复核公开页面定位”和“quote 真实性边界拆分”，没有完成外部版本选择。
- `candidate_available` 可以支持后续人工任务的页面定位、版本候选和 quote 对照；不能自动填 `source_file`、`edition`、`source_passage_id` 或 `quote_check=canonical_passed`。
- 对正文与注文、普通本与注疏本、不同篇名、繁简变体，必须在后续 resolution event 中明确记录具体选择；不能用一个 Wikisource URL 覆盖多个文本层。
- `external:1a34...` 第二条、`external:013...` 和 `external:d8e...` 是本轮新增的可复核线索，但由于本任务禁止改队列，它们只停留在本报告。

## 7. 下一步建议（不在本轮执行）

1. 将 `external:013641580de28101` 与 `external:d8e70ea81ba95f1a` 建立候选页面复核项，补抓页面 revision/edition 元数据后再决定是否更新 queue。
2. 对 `external:1a34ea15bc079eb2` 的第二条 quote 建立独立 candidate ref，但先确认它与第一条 evidence 是否来自同一篇/同一底本层。
3. 对 `0e4af...`、`acb1...`、`f602...`、`c3de...` 先拆分“正文 quote / 注文 quote / 二次引用”，不要整体通过。
4. API 速率限制解除后，再从官方 API 取得新增页面的 revision、timestamp 和 raw content；否则保持本报告的 unknown，不猜版本。

## 8. 并发写入与不变更边界

- 本轮未执行任何 SQLite 写操作，未调用 review/resolution writer。
- 本轮没有写入代码、manifest、source queue、passage queue 或 review task。manifest 与 source queue 的 hash 在研究前后保持不变。
- 研究过程中发现后台 `python3 v2/scripts/fetch_external_public_candidates.py --include-secondary-citations` 进程在写候选/任务产物；任务快照 mtime 为 `2026-08-13 13:21:28 +0800`，hash 从研究开始时记录的 `88280e...` 变为最终 `cc4259...`。该进程不是本报告的研究步骤，已在 13:26 左右停止，以避免继续违反本轮只读范围。
- 因此，任务快照的最终内容属于“并发外部变更后的只读输入”，不是本研究产生的写入；若要恢复到更早任务快照，应另行明确授权，不能在本报告中擅自回滚。
- 最终复核：manifest `57492f...`、source queue `861e57...`、任务快照 `cc4259...`；本报告的 100 行逐项表与停止后的任务快照行数/顺序一致。

### 外部页面入口

- Wikisource API：<https://zh.wikisource.org/w/api.php>
- CText 礼记入口：<https://ctext.org/liji/zh>
- CText 左传入口：<https://ctext.org/chun-qiu-zuo-zhuan/zhs>
- CText 仪礼入口：<https://ctext.org/yili/zhs>
- CText 大戴礼记入口：<https://ctext.org/da-dai-li-ji/zhs>

结论：本轮没有把转录当作 canonical；新增的是两条直接页面线索、一条同页第二 quote 线索，以及对若干复合/非连续 quote 的否定性边界说明。
