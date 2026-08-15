# 外部原典资料研究（Round 2）

> 研究性质：外部资料检索与可复核元数据整理；本轮新增的候选物化由独立 V2 入库脚本完成。没有把任何来源标记为 canonical，也没有修改 annotation evidence 的 passage、quote_check 或 canonical 状态。

- 研究日期：2026-08-13
- 输入清单：v2/data/real_runs/external_source_inventory.json
- external source 数：100
- 数据库关联证据数：121；另有 7,120 条旧 dictionary.db 证据没有 external_source_id，不计入本 100 项来源表
- 外部原典待核验：80；王氏正文二次命中：41
- 既有公开候选清单：80 条；本轮对已冻结页面，并从 V2 外部 passage 队列恢复已有的 hash-addressed 页面后，用共用的保守 Wikitext 清理和小范围简繁定位重算：candidate_found=6、search_hit_only=8、no_public_match=66，共 15 个连续文本候选、26 个页面；这些仍是 candidate，不是 canonical。

## 1. 结果摘要

- 本轮逐项结果：verified metadata=75，candidate=22，unavailable=3。
- verified metadata 只表示高信任平台的作品或篇名、公开 URL、页面标示底本或版本信息，以及下一步可用的篇章、卷、条定位键可复核；不表示该条引文已在对应底本中核对。
- candidate 表示已有公开页面、revision、图书馆目录、馆藏元数据或 CText OCR 可以支持下一步，但版本未唯一化、页面不是正式底本、下载/冻结未完成，或原始引文是复合来源/特定注家。
- unavailable 只用于本轮仍不能唯一对应的来源身份或残引系统；不删除、不忽略，也不以搜索命中替代原典。
- 本轮新增下载并冻结的公开页面文件：4 个；当前本地冻结候选页面共 26 个；对已有冻结页面新增可定位的候选判定 12 个 passage（与既有 3 个合计 15 个）；canonical 晋级：0。网络搜索结果可能随排序变化，因此以冻结页面、raw hash 和队列恢复记录为准，不把一次重抓结果当作历史事实。

## 2. 判定口径与外部平台

### 2.1 CText（中国哲学书电子化计划）

CText 原典页会显示电子底本和可用版本列表，并通常提供按篇、卷、年次、字头或卦爻的定位入口。本轮使用的主要直接页面包括：

- <https://ctext.org/shang-shu/zhs>
- <https://ctext.org/chun-qiu-zuo-zhuan/zhs>
- <https://ctext.org/mengzi/zhs>
- <https://ctext.org/rites-of-zhou/zhs>
- <https://ctext.org/guliang-zhuan/zhs>

CText 的使用说明提醒数字文本可能存在录入或 OCR 差异，并要求按对应页面引用；网站页脚还提示禁止自动批量下载。本轮因此只记录 URL、页面底本和定位键，不批量抓取、不声称已取得本地可冻结底本。方法与引用边界见 <https://ctext.org/introduction/zhs> 和 <https://ctext.org/faq/cite/zhs>。

### 2.2 中华经典古籍库、国家图书馆与其他正式入口

这些平台对正式版本、图像对照和机构授权很有价值，但当前不能把机构登录入口等同于匿名公开可下载底本：

- 中华经典古籍库入口：<https://jingdian.ancientbooks.cn>；高校图书馆说明见 <https://lib.zjnu.edu.cn/2021/0506/c14570a357850/page.htm>、<https://lib.ecnu.edu.cn/92/1c/c38585a496156/page.htm>。
- 国家图书馆/中华古籍资源库入口说明：<https://www.nlc.cn/pcab/zx/xw/20240131_2637771.shtml>、<https://www.nlc.cn/pcab/zy/qglh_zyk/>。
- 中国基本古籍库高校服务说明：<https://library.suda.edu.cn/cb/75/c4807a52085/page.htm>。
- 对复合来源中被并列的《说苑·敬慎》，CText 有独立《说苑》入口和版本列表：<https://ctext.org/shuo-yuan/zhs>；本轮仍不把它自动并入原复合 source_id。
- Wikisource API 与页面只作候选文本或 revision：<https://zh.wikisource.org/w/api.php>；本报告不会把 Wikisource 候选当作 canonical。

## 3. 证据量优先的入口

下表只用于安排下一轮核对优先级；代表 quote 是 V2 当前证据记录中的字符串，不是本轮对外部底本的通过结论。

| evidence 数 | 来源 | 当前代表 quote（最多 3 条） | 本轮意义 |
|---:|---|---|---|
| 13 | 说文解字 | 宾，所敬也。；敬，肃也。从攴苟。苟，自急敕也。从羊省，从包省，从口，口犹慎言也。从羊，与义、善、美同意。；㥛，谨重皃。 | 先做版本唯一化和逐引文定位 |
| 4 | 《玉篇》 | 苟，居力切，亦作亟。；㿃，牛頭瘡也。；㿓，羊蹄閒㿓疾也。 | 先做版本唯一化和逐引文定位 |
| 2 | 《礼记·檀弓》 | 昔者吾有斯子也，吾以将为贤人也；吾未尝以就公室 | 先做版本唯一化和逐引文定位 |
| 2 | 《尔雅》 | 已，此也；骭瘍爲微。 | 先做版本唯一化和逐引文定位 |
| 2 | 《吴语》 | 昔楚灵王不君，其臣箴谏以不入；譬諸疾疥癬也。 | 先做版本唯一化和逐引文定位 |
| 2 | 礼记·曲礼 | 心服曰畏。；身有瘍則浴。 | 先做版本唯一化和逐引文定位 |
| 2 | 《礼记·祭统》 | 对扬以辟之勤大命，施于烝彝鼎；诚信之谓尽，尽之谓敬。 | 先做版本唯一化和逐引文定位 |
| 2 | 《书·洛诰》 | 公定予往已；已！女惟冲子！ | 先做版本唯一化和逐引文定位 |
| 1 | 《左传·昭公二十五年》 | 公以告臧孙，臧孙以难。告郈孙，郈孙以可，劝 | 先做版本唯一化和逐引文定位 |
| 1 | 左传僖二十二年 | 君子不重傷。 | 先做版本唯一化和逐引文定位 |
| 1 | 礼记·表记 | 大人之器威敬。 | 先做版本唯一化和逐引文定位 |
| 1 | 史记·李将军列传 | 悛悛如鄙人，口不能道辞。 | 先做版本唯一化和逐引文定位 |

优先级结论：先处理《说文解字》（13 条）和《玉篇》（4 条），再处理 evidence=2 的《书·洛诰》、吴语、尔雅、礼记系列；其余单条来源按本报告的 verified metadata 与复合/注家边界排队。

## 4. 100 个 external source 逐项结果

URL 是直接页面或正式检索/馆藏入口。public candidate 复用已有 manifest 状态，只表示先前候选搜索结果，不表示本轮通过。

| # | external_source_id | evidence | cited work | 结果 | public candidate | 直接 URL | 版本/底本或 revision 信息 | 下载/冻结 | 定位能力与边界 |
|---:|---|---:|---|---|---|---|---|---|---|
| 1 | external:8dfd1c062a931f5a | 1 | 《书·大诰》某氏传 | unavailable | no_public_match | <https://ctext.org/searchbooks.pl?if=en&searchu=%E4%B8%80%E5%88%87%E7%B6%93%E9%9F%B3%E7%BE%A9> | 未确认能唯一对应仓颉篇、通俗文残引的独立公开底本 | 否；来源身份或传本未唯一确认。 | 先定音义系统/卷次/上下文 本轮不强行补证；保留身份问题，避免搜索命中冒充原典。 |
| 2 | external:11f2fbee20be6ac6 | 1 | 《书·尧典》 | verified metadata | no_public_match | <https://ctext.org/shang-shu/zhs> | 武英殿十三经注疏本尚书正义；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 3 | external:1efd7b5b088f5c84 | 1 | 《书·康诰》 | verified metadata | no_public_match | <https://ctext.org/shang-shu/zhs> | 武英殿十三经注疏本尚书正义；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 4 | external:7784b4b6e9ec5644 | 1 | 《书·梓材》 | verified metadata | no_public_match | <https://ctext.org/shang-shu/zhs> | 武英殿十三经注疏本尚书正义；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 5 | external:f6e2137567ff87fb | 2 | 《书·洛诰》 | verified metadata | no_public_match | <https://ctext.org/shang-shu/zhs> | 武英殿十三经注疏本尚书正义；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 6 | external:54249af3e0d249fa | 1 | 《书·牧誓》 | verified metadata | no_public_match | <https://ctext.org/shang-shu/zhs> | 武英殿十三经注疏本尚书正义；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 7 | external:d961824e0fbf7e4e | 1 | 《书·盘庚》 | verified metadata | no_public_match | <https://ctext.org/shang-shu/zhs> | 武英殿十三经注疏本尚书正义；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 8 | external:c9d3f8f1b2e90a73 | 1 | 《书·金縢》 | verified metadata | no_public_match | <https://ctext.org/shang-shu/zhs> | 武英殿十三经注疏本尚书正义；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 9 | external:d8e70ea81ba95f1a | 1 | 《仪礼·乡射礼》 | verified metadata | no_public_match | <https://ctext.org/yili/zhs> | 四部丛刊初编本仪礼；另列仪礼注疏和阮元校刻本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 仪礼篇名/条次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 10 | external:ae2dfc2b943173ea | 1 | 《仪礼·大射仪》 | verified metadata | no_public_match | <https://ctext.org/yili/zhs> | 四部丛刊初编本仪礼；另列仪礼注疏和阮元校刻本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 仪礼篇名/条次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 11 | external:23cbb13576cc52d9 | 1 | 众经音义引仓颉篇 | unavailable | — | <https://ctext.org/searchbooks.pl?if=en&searchu=%E4%B8%80%E5%88%87%E7%B6%93%E9%9F%B3%E7%BE%A9> | 未确认能唯一对应仓颉篇、通俗文残引的独立公开底本 | 否；来源身份或传本未唯一确认。 | 先定音义系统/卷次/上下文 本轮不强行补证；保留身份问题，避免搜索命中冒充原典。 |
| 12 | external:8cdc1c668e4f13d7 | 1 | 众经音义引通俗文 | unavailable | — | <https://ctext.org/searchbooks.pl?if=en&searchu=%E4%B8%80%E5%88%87%E7%B6%93%E9%9F%B3%E7%BE%A9> | 未确认能唯一对应仓颉篇、通俗文残引的独立公开底本 | 否；来源身份或传本未唯一确认。 | 先定音义系统/卷次/上下文 本轮不强行补证；保留身份问题，避免搜索命中冒充原典。 |
| 13 | external:53315f76b7e50407 | 1 | 《公羊传·庄公二十四年》 | verified metadata | no_public_match | <https://ctext.org/gongyang-zhuan/zhs> | 武英殿十三经注疏本春秋公羊传注疏 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 14 | external:070ad5cdcb5ba91e | 1 | 史记·李将军列传 | verified metadata | search_hit_only | <https://ctext.org/shiji/zhs><br><https://zh.wikisource.org/wiki/%E5%8F%B2%E8%A8%98/%E5%8D%B7109> | 武英殿二十四史本史记；有列传、世家导航 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 15 | external:74564004c45c713d | 1 | 史记·越世家 | verified metadata | — | <https://ctext.org/shiji/zhs> | 武英殿二十四史本史记；有列传、世家导航 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 16 | external:ed5963b2e62a70dc | 1 | 后汉书·鲜卑传 | verified metadata | — | <https://ctext.org/hou-han-shu/zh> | 武英殿二十四史本后汉书 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 列传篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 17 | external:dff47c336e8a2cac | 1 | 《吕氏春秋·乐成》 | verified metadata | no_public_match | <https://ctext.org/lv-shi-chun-qiu/zhs> | 四部丛刊初编本吕氏春秋 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 18 | external:3e901111216d9db9 | 1 | 《吕氏春秋·精谕》与《淮南·道应》 | candidate | no_public_match | <https://ctext.org/lv-shi-chun-qiu/zhs><br><https://ctext.org/huainanzi/zh> | 四部丛刊初编本吕氏春秋；复合来源的淮南子入口另列 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 19 | external:3419d825b1d7f8d9 | 2 | 《吴语》 | verified metadata | no_public_match | <https://ctext.org/guo-yu/zhs> | 四部丛刊初编本国语；有吴、晋、越等语目录 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 语别/篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 20 | external:43ff9abf9672cf62 | 1 | 周官·乡大夫 | verified metadata | no_public_match | <https://ctext.org/rites-of-zhou/zhs> | 四部丛刊初编本周礼；另列周礼注疏 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 官名/篇名/条次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 21 | external:9fa5a53474a9d0cd | 1 | 周官·疾医 | verified metadata | no_public_match | <https://ctext.org/rites-of-zhou/zhs> | 四部丛刊初编本周礼；另列周礼注疏 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 官名/篇名/条次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 22 | external:593560252b9404b6 | 1 | 《周语》引《汤誓》 | candidate | no_public_match | <https://ctext.org/guo-yu/zhs><br><https://ctext.org/shang-shu/zhs> | 四部丛刊初编本国语；被引《汤誓》应另回尚书来源 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 语别/篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 23 | external:470164fd8f443521 | 1 | 《大戴礼·子张问入官》 | verified metadata | search_hit_only | <https://ctext.org/da-dai-li-ji/zhs><br><https://zh.wikisource.org/wiki/%E5%A4%A7%E6%88%B4%E7%A6%AE%E8%A8%98/%E5%AD%90%E5%BC%B5%E5%95%8F%E5%85%A5%E5%AE%98> | 四部丛刊初编本大戴礼记；另见四库等版本 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 24 | external:8e2c88e55cbe430a | 1 | 《大戴礼·曾子制言》 | verified metadata | no_public_match | <https://ctext.org/da-dai-li-ji/zhs> | 四部丛刊初编本大戴礼记；另见四库等版本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 25 | external:469c5ccd5c500d35 | 1 | 孟子·公孙丑 | verified metadata | — | <https://ctext.org/mengzi/zhs> | 武英殿十三经注疏本孟子注疏 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公孙丑篇/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 26 | external:dc218d6015fe43c6 | 1 | 宋玉风赋 | candidate | — | <https://ctext.org/wiki.pl?chapter=8410926&if=en><br><https://zh.wikisource.org/zh-hant/%E9%A2%A8%E8%B3%A6_%28%E5%AE%8B%E7%8E%89%29> | CText文选Wiki与Wikisource风赋均为候选，正式影印底本未固定 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 文选卷次/篇名；候选 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 27 | external:39d4251f8580122f | 1 | 《射义》引诗 | candidate | — | <https://ctext.org/yili/zhs><br><https://ctext.org/book-of-poetry/zhs> | 四部丛刊初编本仪礼；被引诗篇需另回毛诗来源 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 仪礼篇名/条次 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 28 | external:205014307b3ea5fd | 2 | 《尔雅》 | verified metadata | — | <https://ctext.org/er-ya/zhs> | 武英殿十三经注疏本尔雅注疏；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇/章/条目 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 29 | external:84d680e7512cac8b | 1 | 《左传·文公五年》 | verified metadata | no_public_match | <https://ctext.org/chun-qiu-zuo-zhuan/zhs> | 武英殿十三经注疏本春秋左传正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 30 | external:013641580de28101 | 1 | 《左传·昭公二十五年》 | verified metadata | no_public_match | <https://ctext.org/chun-qiu-zuo-zhuan/zhs> | 武英殿十三经注疏本春秋左传正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 31 | external:2ee2b51fd39c6b47 | 1 | 《左传·昭公二十年》 | verified metadata | no_public_match | <https://ctext.org/chun-qiu-zuo-zhuan/zhs> | 武英殿十三经注疏本春秋左传正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 32 | external:6ca38523a3372bc8 | 1 | 《左传·昭公十一年》 | verified metadata | no_public_match | <https://ctext.org/chun-qiu-zuo-zhuan/zhs> | 武英殿十三经注疏本春秋左传正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 33 | external:2f630c866c1e5f53 | 1 | 《左传·襄公二十九年》 | verified metadata | no_public_match | <https://ctext.org/chun-qiu-zuo-zhuan/zhs> | 武英殿十三经注疏本春秋左传正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 34 | external:daf036c0c547934d | 1 | 《左传·襄公二十年》 | verified metadata | search_hit_only | <https://ctext.org/chun-qiu-zuo-zhuan/zhs><br><https://zh.wikisource.org/wiki/%E6%98%A5%E7%A7%8B%E5%B7%A6%E5%82%B3%E8%A6%81%E7%BE%A9%20%28%E5%9B%9B%E5%BA%AB%E5%85%A8%E6%9B%B8%E6%9C%AC%29/%E5%8D%B716> | 武英殿十三经注疏本春秋左传正义 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 35 | external:f82fc3379647f9aa | 1 | 《左传·闵公二年》 | verified metadata | no_public_match | <https://ctext.org/chun-qiu-zuo-zhuan/zhs> | 武英殿十三经注疏本春秋左传正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 36 | external:0248a59eb0263c53 | 1 | 左传僖二十二年 | verified metadata | no_public_match | <https://ctext.org/chun-qiu-zuo-zhuan/zhs> | 武英殿十三经注疏本春秋左传正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 37 | external:f0820d3b563ac3d6 | 1 | 左传襄十九年 | verified metadata | — | <https://ctext.org/chun-qiu-zuo-zhuan/zhs> | 武英殿十三经注疏本春秋左传正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 38 | external:49c77aa81fc0c574 | 1 | 《广雅》 | candidate | no_public_match | <https://ctext.org/wiki.pl?chapter=1191069&if=en&remap=gb> | CText Wiki OCR查找入口；独立正式底本记录未充分确认 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 篇/条；OCR需另核 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 39 | external:08b95d674f60a75d | 1 | 广雅·释言 | candidate | — | <https://ctext.org/wiki.pl?chapter=1191069&if=en&remap=gb> | CText Wiki OCR查找入口；独立正式底本记录未充分确认 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 篇/条；OCR需另核 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 40 | external:e9942b49bb30b460 | 1 | 《庄子·养生主》 | verified metadata | no_public_match | <https://ctext.org/zhuangzi/zhs> | 续古逸丛书本南华真经 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 41 | external:e76a8d8af96b971b | 1 | 《庄子·庚桑楚》 | verified metadata | no_public_match | <https://ctext.org/zhuangzi/zhs> | 续古逸丛书本南华真经 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 42 | external:b947c4a6eb3a29fa | 1 | 《庄子·齐物论》 | verified metadata | no_public_match | <https://ctext.org/zhuangzi/zhs> | 续古逸丛书本南华真经 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 43 | external:f602917bee5b892e | 1 | 急就篇 | verified metadata | search_hit_only | <https://ctext.org/jijiupian/zhs><br><https://zh.wikisource.org/wiki/%E6%80%A5%E5%B0%B1%E7%AF%87%20%28%E5%9B%9B%E9%83%A8%E5%8F%A2%E5%88%8A%E6%9C%AC%29/%E6%96%87> | 四部丛刊续编本急就篇；另列四库、古逸丛书本 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇章/句次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 44 | external:ea3bc829642592e2 | 1 | 方言 | verified metadata | no_public_match | <https://ctext.org/fang-yan/zhs> | 四部丛刊初编本方言 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 卷/条 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 45 | external:e08b63cd94b33014 | 1 | 《易·剥》初六、六二、六四 | verified metadata | no_public_match | <https://ctext.org/book-of-changes/zhs> | 武英殿十三经注疏本周易正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 卦名/爻位/传注层次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 46 | external:8ce605b5541c5448 | 1 | 《易·同人彖传》 | verified metadata | no_public_match | <https://ctext.org/book-of-changes/zhs> | 武英殿十三经注疏本周易正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 卦名/爻位/传注层次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 47 | external:a325362d923ff84f | 1 | 《易·复》上六 | verified metadata | no_public_match | <https://ctext.org/book-of-changes/zhs> | 武英殿十三经注疏本周易正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 卦名/爻位/传注层次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 48 | external:edf0a8a16db346dd | 1 | 《易·小畜》九五虞翻注 | candidate | no_public_match | <https://ctext.org/book-of-changes/zhs> | 武英殿十三经注疏本周易正义 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 卦名/爻位/传注层次 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 49 | external:87d9afdaa90894a3 | 1 | 《易·泰》六四 | verified metadata | — | <https://ctext.org/book-of-changes/zhs> | 武英殿十三经注疏本周易正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 卦名/爻位/传注层次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 50 | external:ffe2305cea6346f4 | 1 | 《易·泰》初九 | verified metadata | no_public_match | <https://ctext.org/book-of-changes/zhs> | 武英殿十三经注疏本周易正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 卦名/爻位/传注层次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 51 | external:a507727f5b39ad11 | 1 | 《易·鼎》初六 | verified metadata | — | <https://ctext.org/book-of-changes/zhs> | 武英殿十三经注疏本周易正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 卦名/爻位/传注层次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 52 | external:e79dad3df9b7c10c | 1 | 春秋繁露·五行顺逆 | verified metadata | — | <https://ctext.org/chun-qiu-fan-lu/zhs> | 四部丛刊初编本春秋繁露 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 53 | external:cda01e8a80327403 | 1 | 《晋语》 | verified metadata | no_public_match | <https://ctext.org/guo-yu/zhs> | 四部丛刊初编本国语；有吴、晋、越等语目录 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 语别/篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 54 | external:7c26b385e6e57398 | 1 | 《汉书·刘向传》注 | candidate | no_public_match | <https://ctext.org/han-shu/zhs> | 武英殿二十四史本汉书；注家和具体版本另核 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 55 | external:42f56de1c48af001 | 1 | 《汉书·宣帝纪》颜师古注 | candidate | no_public_match | <https://ctext.org/han-shu/zhs> | 武英殿二十四史本汉书；注家和具体版本另核 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 56 | external:e63058f135f3f588 | 1 | 《汉书·翟义传》颜师古注 | candidate | no_public_match | <https://ctext.org/han-shu/zhs> | 武英殿二十四史本汉书；注家和具体版本另核 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 57 | external:f5dda673427458a0 | 1 | 汉书·赵充国传 | verified metadata | no_public_match | <https://ctext.org/shang-shu/zhs> | 武英殿十三经注疏本尚书正义；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 58 | external:c9f37e91795e9c89 | 1 | 汉成阳灵台碑 | candidate | no_public_match | <https://www.dpm.org.cn/collection/impres/231827.html> | 故宫藏品页确认重刻成阳灵台碑宋拓本等对象；不是开放汉碑全文底本 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 藏品对象；无全文版式 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 59 | external:acc0d0e3f3c42d2e | 1 | 《淮南·道应》 | verified metadata | no_public_match | <https://ctext.org/huainanzi/zh> | 四部丛刊初编本淮南鸿烈解；另列四库、道藏版本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 60 | external:53b12a56c1e7b615 | 1 | 《淮南子·权勋》与《说苑·敬慎》 | candidate | no_public_match | <https://ctext.org/huainanzi/zh><br><https://ctext.org/shuo-yuan/zhs> | 四部丛刊初编本淮南鸿烈解；复合来源的说苑入口另列 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 61 | external:4948ef1e9c22e8c3 | 1 | 《燕策》与《史记·燕世家》 | candidate | no_public_match | <https://ctext.org/zhan-guo-ce/zh><br><https://ctext.org/shiji/zhs> | 士礼居丛书本战国策；复合来源的史记入口另列 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 策别/篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 62 | external:36fe94ec8eea077e | 1 | 爾雅 | verified metadata | — | <https://ctext.org/er-ya/zhs> | 武英殿十三经注疏本尔雅注疏；另列四部丛刊本 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇/章/条目 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 63 | external:f4236b681959fc8b | 4 | 《玉篇》 | candidate | no_public_match | <https://ctext.org/searchbooks.pl?if=en&searchu=%E7%8E%89%E7%AF%87> | 同时列原本玉篇残卷、古逸丛书本玉篇、大广益会玉篇；版本未唯一化 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 字头/卷；版本不可混用 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 64 | external:0e4af81ea01d4bc8 | 1 | 《礼记·乐记》 | verified metadata | search_hit_only | <https://ctext.org/liji/zh><br><https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98/%E6%A8%82%E8%A8%98> | 武英殿十三经注疏本礼记正义 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 65 | external:288ccd898a049ace | 1 | 礼记·大学 | verified metadata | — | <https://ctext.org/liji/zh> | 武英殿十三经注疏本礼记正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 66 | external:5fd9fd6fab996cd0 | 2 | 礼记·曲礼 | verified metadata | — | <https://ctext.org/liji/zh> | 武英殿十三经注疏本礼记正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 67 | external:c3def6d236981f13 | 1 | 礼记·月令 | verified metadata | search_hit_only | <https://ctext.org/liji/zh><br><https://zh.wikisource.org/wiki/%E6%AC%BD%E5%AE%9A%E7%A6%AE%E8%A8%98%E7%BE%A9%E7%96%8F%20%28%E5%9B%9B%E5%BA%AB%E5%85%A8%E6%9B%B8%E6%9C%AC%29/%E5%8D%B723> | 武英殿十三经注疏本礼记正义 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 68 | external:1a34ea15bc079eb2 | 2 | 《礼记·檀弓》 | verified metadata | search_hit_only | <https://ctext.org/liji/zh><br><https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98/%E6%AA%80%E5%BC%93%E4%B8%8B> | 武英殿十三经注疏本礼记正义 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 69 | external:12c1b2ae0312e390 | 1 | 《礼记·檀弓》卢植注 | candidate | no_public_match | <https://ctext.org/liji/zh> | 武英殿十三经注疏本礼记正义 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 礼记篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 70 | external:6c8f5a25fbcf9036 | 1 | 《礼记·檀弓》郑玄注 | candidate | search_hit_only | <https://ctext.org/liji/zh><br><https://zh.wikisource.org/wiki/%E7%BA%82%E5%9C%96%E4%BA%92%E8%A8%BB%E7%A6%AE%E8%A8%98%20%28%E5%9B%9B%E9%83%A8%E5%8F%A2%E5%88%8A%E6%9C%AC%29/%E5%8D%B7%E7%AC%AC%E4%B8%89> | 武英殿十三经注疏本礼记正义 已有候选 revision 可从 URL 复核。 | 既有候选目录有页面或 revision；本轮不升级为底本、不写 canonical。 | 礼记篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 71 | external:6242169e40e87889 | 1 | 礼记·礼运 | verified metadata | candidate_found | <https://ctext.org/liji/zh><br><https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98/%E7%A6%AE%E9%81%8B> | 武英殿十三经注疏本礼记正义 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 72 | external:acb1ffa71c2b89f3 | 2 | 《礼记·祭统》 | verified metadata | search_hit_only | <https://ctext.org/liji/zh><br><https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98%E6%AD%A3%E7%BE%A9/49> | 武英殿十三经注疏本礼记正义 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 73 | external:cc9f0a75c9b4b295 | 1 | 《礼记·聘义》 | verified metadata | search_hit_only | <https://ctext.org/liji/zh><br><https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98/%E8%81%98%E7%BE%A9> | 武英殿十三经注疏本礼记正义 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 74 | external:03332422ff166657 | 1 | 礼记·表记 | verified metadata | — | <https://ctext.org/liji/zh> | 武英殿十三经注疏本礼记正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 75 | external:254bfba806f192fb | 1 | 《礼记·郊特牲》 | verified metadata | search_hit_only | <https://ctext.org/liji/zh><br><https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98%E6%AD%A3%E7%BE%A9/25> | 武英殿十三经注疏本礼记正义 已有候选 revision 可从 URL 复核。 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 礼记篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 76 | external:178921ce00bd6675 | 1 | 穀梁传文十一年 | verified metadata | no_public_match | <https://ctext.org/guliang-zhuan/zhs> | 武英殿十三经注疏本春秋谷梁传注疏 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 公名/年次/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 77 | external:a9c945b82cf3c3a3 | 1 | 管子·地员 | verified metadata | — | <https://ctext.org/guanzi/zhs> | 四部丛刊初编本管子；另列四库、房玄龄注等 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落；注家另核 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 78 | external:ecdbabb6f9c9fa8a | 1 | 《管子·形势》 | verified metadata | no_public_match | <https://ctext.org/guanzi/zhs> | 四部丛刊初编本管子；另列四库、房玄龄注等 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落；注家另核 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 79 | external:14c0e8bead2c6969 | 1 | 管子·形勢解 | verified metadata | — | <https://ctext.org/guanzi/zhs> | 四部丛刊初编本管子；另列四库、房玄龄注等 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/段落；注家另核 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 80 | external:6630620b4c00837a | 1 | 管子注 | candidate | — | <https://ctext.org/guanzi/zhs> | 四部丛刊初编本管子；另列四库、房玄龄注等 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 篇名/段落；注家另核 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 81 | external:e34b8c0c6bc12c88 | 1 | 《系辞传》 | verified metadata | no_public_match | <https://ctext.org/book-of-changes/zhs> | 武英殿十三经注疏本周易正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 卦名/爻位/传注层次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 82 | external:1d5a3d1f7d577b8d | 1 | 经典释文 | candidate | no_public_match | <https://ctext.org/wiki.pl?if=gb&remap=gb&res=138421> | CText Wiki记陆德明、三十卷及四库本；为OCR/Wiki入口 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 卷/经/音义条目 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 83 | external:f74c802efb4df58c | 1 | 《论语·为政》 | verified metadata | no_public_match | <https://ctext.org/analects/zhs> | 武英殿十三经注疏本论语注疏 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/章次；王肃注另核 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 84 | external:89cbcfaf933cd1dc | 1 | 论语·乡党 | candidate | no_public_match | <https://ctext.org/analects/zhs> | 武英殿十三经注疏本论语注疏 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 篇名/章次；王肃注另核 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 85 | external:09443c3e6afd3199 | 1 | 《论语·微子》 | verified metadata | no_public_match | <https://ctext.org/analects/zhs> | 武英殿十三经注疏本论语注疏 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 篇名/章次；王肃注另核 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 86 | external:71577bed5bc1a07a | 1 | 《诗·击鼓》 | verified metadata | no_public_match | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 87 | external:b887e31fd953eb17 | 1 | 《诗·小明》 | verified metadata | no_public_match | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 88 | external:31195980b8c109c4 | 1 | 《诗·旄邱》 | verified metadata | no_public_match | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 89 | external:aaf9d8191c2fb976 | 1 | 《诗·桑柔》 | verified metadata | — | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 90 | external:dc5ac9a90db13b5f | 1 | 《诗·江有汜》 | verified metadata | — | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 91 | external:dc1b2e45d8afebf4 | 1 | 《诗·瞻卬》 | verified metadata | — | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 92 | external:df197dbd13ca053b | 1 | 诗经·召南·采蘋 | verified metadata | no_public_match | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 93 | external:bb97deed2278849a | 1 | 诗经·商颂·殷武 | verified metadata | — | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 94 | external:1151020f38da5acd | 1 | 诗经·大雅·常武 | verified metadata | — | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 95 | external:58c1d0d954524cd8 | 1 | 诗经·大雅·韩奕 | verified metadata | no_public_match | <https://ctext.org/book-of-poetry/zhs> | 武英殿十三经注疏本毛诗正义 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 诗篇名/章次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 96 | external:d418a82b6f8ced81 | 13 | 说文解字 | verified metadata | no_public_match | <https://ctext.org/shuo-wen-jie-zi/zhs><br><https://ctext.org/library.pl?if=gb&res=95214> | 四部丛刊初编本说文解字；另有哈佛燕京藏本扫描记录 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 部首/字头/卷次 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |
| 97 | external:78195fc7f00db94f | 1 | 《越语》与《史记·越世家》 | candidate | no_public_match | <https://ctext.org/guo-yu/zhs><br><https://ctext.org/shiji/zhs> | 四部丛刊初编本国语；复合来源的史记入口另列 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 语别/篇名/段落 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 98 | external:1d3e421d15914a3e | 1 | 集韻 | candidate | — | <https://ctext.org/wiki.pl?if=gb&remap=gb&res=518011> | CText Wiki记丁度、北宋、二十卷并提示OCR误差；印本字段不足 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 卷/韵部/字头；候选 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 99 | external:41147de1dc438eb8 | 1 | 齐民要术 | candidate | no_public_match | <https://ctext.org/library.pl?if=en&remap=gb&res=77414> | CText图书馆有四部丛刊初编本齐民要术记录 | 否；有入口，但本轮未取得可冻结的 source-specific 文件。 | 卷/篇/方名；未冻结 可进入下一轮版本和逐引文核对；不等于底本或引文已核验。 |
| 100 | external:c1b6ad2b3b97a8c9 | 1 | 《齐策》 | verified metadata | no_public_match | <https://ctext.org/zhan-guo-ce/zh> | 士礼居丛书本战国策 | 否；本轮未下载、未冻结、未生成本地 hash；只记公开元数据。 | 策别/篇名/段落 仅元数据和定位入口通过；不等于 quote 已通过 canonical quote_check。 |

## 5. 具体边界记录

### 5.1 已有 Wikisource 候选的处理

当前 manifest 中的 candidate_found=6 与 search_hit_only=8 只说明检索到公开页面或 revision，且其中 15 个页面文本经过保守清理后出现连续 quote 候选。例如《礼记·乐记》的候选页面可在 <https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98/%E6%A8%82%E8%A8%98> 复核，页面 revision、原始文件和 hash 已在 manifest 登记；本轮仍把它当 candidate，不用它替代 CText 或正式影印底本，也不写入 canonical。

当前 manifest 中带有可复核 revision/raw hash 的 candidate page 共 26 个（同一 source 可能有多个版本/页面）。下面只列代表性 source、revision、时间、raw hash 与直接 URL；这些是候选冻结线索，不是 canonical 底本。完整 URL 和其余候选版本仍以 `v2/data/real_runs/external_public_candidate_manifest.json` 为准：

| external_source_id | revision / 时间 / raw SHA-256 / URL |
|---|---|
| external:070ad5cdcb5ba91e | `1765440 / 2020-02-03T16:29:02Z / 6fdb401be6787c9c7a724b4970f057ce5d5ee898f3d5f1a03a427b28a3fb3dda` / <https://zh.wikisource.org/wiki/%E5%8F%B2%E8%A8%98/%E5%8D%B7109>；`2514779 / 2025-01-06T08:32:38Z / c5e0dfeca5dbd51db7e83a9abb095554257f402fbc9a931e381aa3198721406f` / <https://zh.wikisource.org/wiki/%E5%8F%B2%E8%A8%98%E4%B8%89%E5%AE%B6%E8%A8%BB/%E5%8D%B7109>；另有 3 个同 source 候选版本，详见 `external_public_candidate_manifest.json`。 |
| external:0e4af81ea01d4bc8 | `2346508 / 2023-12-21T03:48:18Z / f5cd5d8d3975444b20aa647fcb4a34c122402ffa53dddd5e571533ed6919e42f` / <https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98/%E6%A8%82%E8%A8%98>；`544488 / 2016-10-04T00:22:43Z / 4bd29d2a9a8e552bed8ec040310e10e9a727d9b0f5268f841a7d6b0e3c732e41` / <https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98%E6%B3%A8%E7%96%8F%20%28%E5%9B%9B%E5%BA%AB%E5%85%A8%E6%9B%B8%E6%9C%AC%29/%E5%8D%B737> |
| external:1a34ea15bc079eb2 | `2346897 / 2023-12-21T13:29:35Z / c9ac8d67a37aaa7a3f5ad10a5b75d4cf0476d68388449b1ddb53010dd13f44fa` / <https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98/%E6%AA%80%E5%BC%93%E4%B8%8B> |
| external:254bfba806f192fb | `7904391 / 2026-06-28T01:27:54Z / f8f948550d378e958dac0bfa0558c00df68bbfd21c0f1e96bb0c6c2e93d35ee0` / <https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98%E6%AD%A3%E7%BE%A9/25>；另有 2 个同 source 候选版本，详见 manifest。 |
| external:470164fd8f443521 | `2703721 / 2026-04-20T11:21:56Z / 2272c4722f8e1b7f2e02d5282ad4d07193b21533f7ce8042534cd3bd7f44505b` / <https://zh.wikisource.org/wiki/%E5%A4%A7%E6%88%B4%E7%A6%AE%E8%A8%98/%E5%AD%90%E5%BC%B5%E5%95%8F%E5%85%A5%E5%AE%98>；另有四库候选版本。 |
| external:6242169e40e87889 | `2626644 / 2025-11-30T04:01:05Z / 31a2da49ccb913c8a4fe0f109c7f94cd64303cb48ec93946348496f53272156f` / <https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98/%E7%A6%AE%E9%81%8B>；另有 2 个同 source 候选版本。 |
| external:6c8f5a25fbcf9036 | `2652452 / 2026-02-27T03:29:17Z / 9ce4b1135abe16cca0f16ee3c4aabc03dfbb74372fd5168237ac8b4cc7e3f9f6` / <https://zh.wikisource.org/wiki/%E7%BA%82%E5%9C%96%E4%BA%92%E8%A8%BB%E7%A6%AE%E8%A8%98%20%28%E5%9B%9B%E9%83%A8%E5%8F%A2%E5%88%8A%E6%9C%AC%29/%E5%8D%B7%E7%AC%AC%E4%B8%89> |
| external:acb1ffa71c2b89f3 | `2399629 / 2024-04-27T03:18:55Z / 49104524992ba1b89906111eb308f288d80fb7f2e6deaf4104bb3acf65838d9d` / <https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98%E6%AD%A3%E7%BE%A9/49> |
| external:c3def6d236981f13 | `764013 / 2016-10-24T19:34:58Z / 284cf0b3ca3eb326c3d8f54b93f1c732ad4daf9935d7d7ac6a6eb0211613fc94` / <https://zh.wikisource.org/wiki/%E6%AC%BD%E5%AE%9A%E7%A6%AE%E8%A8%98%E7%BE%A9%E7%96%8F%20%28%E5%9B%9B%E5%BA%AB%E5%85%A8%E6%9B%B8%E6%9C%AC%29/%E5%8D%B723> |
| external:cc9f0a75c9b4b295 | `2346520 / 2023-12-21T03:48:53Z / 8fb93a3fa0ad8c5d1d83c04ba8498436940d619a932840702418163b99315595` / <https://zh.wikisource.org/wiki/%E7%A6%AE%E8%A8%98/%E8%81%98%E7%BE%A9> |
| external:daf036c0c547934d | `761331 / 2016-10-24T11:07:10Z / b76fa7230b48545ae58c7f6aae5fe9718aa0f788348a06bf413b7889a497694a` / <https://zh.wikisource.org/wiki/%E6%98%A5%E7%A7%8B%E5%B7%A6%E5%82%B3%E8%A6%81%E7%BE%A9%20%28%E5%9B%9B%E5%BA%AB%E5%85%A8%E6%9B%B8%E5%本%29/%E5%8D%B716> |
| external:f602917bee5b892e | `2661983 / 2026-02-27T10:41:06Z / 68c72a2d07575f4ce9de4eac1718882aa77bd17f2dc198249e9fec9597e28c02` / <https://zh.wikisource.org/wiki/%E6%80%A5%E5%B0%B1%E7%AF%87%20%28%E5%9B%9B%E9%83%A8%E5%8F%A2%E5%88%8A%E6%9C%AC%29/%E6%96%87> |

上述 revision/hash 只确认候选页面在某一时间点的可复核版本，不确认其底本、文字质量或学术正确性。个别旧 manifest URL 含有历史页面编码差异；以表中页面标题、manifest 原始 `page_url` 与 `api_url` 三者交叉复核为准，不把 URL 本身当作版本证明。

《宋玉风赋》可见候选页面 <https://zh.wikisource.org/zh-hant/%E9%A2%A8%E8%B3%A6_%28%E5%AE%8B%E7%8E%89%29>，但它与《文选》正式底本的关系、篇次和文字异文仍需逐页核对。

### 5.2 版本不应混用的例子

- 《说文解字》：CText 主页面标示四部丛刊初编本，另有哈佛燕京藏本扫描记录 <https://ctext.org/library.pl?if=gb&res=95214>；本轮没有把不同版本合并为一个 hash，也没有冻结本地文件。
- 《玉篇》：CText 搜书页同时列原本玉篇残卷、古逸丛书本玉篇和大广益会玉篇；在版本未选定前只能 candidate，不能用一个“玉篇”标签覆盖不同传本，见 <https://ctext.org/searchbooks.pl?if=en&searchu=%E7%8E%89%E7%AF%87>。
- 《礼记》及注文：CText 的礼记正义页面可定位经文篇章，但卢植注、郑玄注、王肃注不是同一个默认底本层；逐条证据必须先拆出经文、注家和版本。
- 复合来源（如越语与史记·越世家、燕策与史记·燕世家、吕氏春秋·精谕与淮南·道应）：每一部分都可能有公开入口，但不能用一个 source_id 或一个 URL 代替拆分后的两个 source passage。

### 5.3 unavailable 的保留理由

- 《书·大诰》某氏传：原始名称中的某氏没有确定责任注家或版本，尚书正文页面不能代替该注文。
- 众经音义引仓颉篇、众经音义引通俗文：这是音义文献中的残引，当前没有确认能唯一对应的独立公开底本、卷次和传本；保留为 unavailable，待先确定引文系统。

## 6. 本轮没有做的事情

- 没有把外部候选写入 annotation evidence 的 passage、quote_check 或 canonical 字段；本轮把 15 个公开转录候选 passage 登记到 V2 的 `source_documents`/`passages` 和 external passage 队列，且均保持 `canonical_status=unknown`。
- 本轮没有改变四部王氏 canonical 文档、来源 hash、案例机器/人工状态或 gold；外部候选登记是可逆的机器工作库派生层。
- 没有把 CText 页面、Wikisource revision、馆藏元数据或搜索片段标记为 canonical quote passed。
- 没有宣称任何一条外部 quote 已完成学术核验；本轮最多完成到 verified metadata 或保留为 candidate/unavailable。

## 7. 下一步（仍属自动化可做范围）

1. 先对《说文解字》和《玉篇》建立版本决策表：选择具体底本，逐字或逐条确定卷、部首、字头和版面或稳定页码；没有底本选择就不写 canonical。
2. 对 CText 可定位的 verified metadata 条目，按 evidence_count 从高到低生成逐引文核对队列；保存外部 URL、页面 revision、访问日期和本地冻结 hash（只有确实取得并许可保存时）。
3. 对 candidate 条目拆分复合来源和注家层，优先补齐 CText、国家图书馆、中华经典古籍库的正式版本元数据；机构登录或许可不足时保持 candidate。
4. 对 unavailable 条目先做身份解析，不以外部搜索片段、王氏正文二次引文或旧机器源替代原典。
5. 通过 quote-in-passage、来源版本唯一性和证据层级校验后，仍只能由人工审校决定是否进入人工确认或 gold。

结论：本轮完成的是“100 项外部来源的研究入口、版本边界和下一步定位能力登记”，不是外部原典核验完成。
