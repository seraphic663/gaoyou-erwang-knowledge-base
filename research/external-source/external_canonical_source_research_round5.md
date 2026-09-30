# V2 外部来源 canonical 底本研究 Round 5

研究日期：2026-08-13。研究范围是 `v2/data/real_runs/queues/external_source_resolution_queue.edition.v1.jsonl` 中与《说文解字》《礼记》《左传》《急就篇》《管子》《论语》相关的 30 条待办；其中 25 条属于本轮点名的书目/篇章，另有《礼记·表记》《礼记·大学》《礼记·礼运》《礼记·郊特牲》《礼记·聘义》5 条同书族待办。

## 结论

1. CText Library 能给出若干清楚的版本名、卷数、章节/卷号和馆藏扫描来源，但本轮直接尝试的 CText Library 页面均得到 HTTP 403；CText OCR/网页正文只作为定位和版本目录证据，没有作为 canonical 引文。
2. CText 页面所列的《钦定四库全书》影印集，在 Internet Archive（IA）一手 item metadata 中能看到 `浙江大学图书馆`、`CADAL`/universallibrary、卷册描述和非零大小的 PDF、CNBook ZIP、TIFF ZIP 文件。因此下列各族系都能形成“可下载底本候选”，但本轮没有下载到本地，也没有把任何候选登记为 V2 canonical。
3. CText 的主要电子底本与上述 Siku 扫描并不总是同一版本：例如《说文解字》主要电子底本是《四部丛刊初编》，《急就篇》主要电子底本是《四部丛刊续编》，《管子》主要电子底本是《四部丛刊初编》，而本轮可确认下载的是对应的 Siku 版本。若 V2 引文要求严格跟随 CText 主底本，仍缺该版本的可下载图像/底本入口。
4. 因而当前可以形成“候选 freeze package 的清单和卷册映射”，不能声称已经形成“本地 freeze package”：本轮按要求未下载文件、未生成 hash、未改 SQLite、manifest、queue 或 production status。后续只有在明确选定版本/注本并下载图像或 CNBook 后，才能创建本地冻结包。

## 证据和访问边界

- CText 入口：主文本页和 Library 目录页只用于识别电子底本、版本、卷册和扫描入口。代表性直接请求包括 [说文解字 Library](https://ctext.org/library.pl?if=gb&node=26160&remap=gb)、[礼记大全 Library](https://ctext.org/library.pl?if=gb&remap=gb&res=5230) 和 [左传 Library](https://ctext.org/library.pl?if=en&remap=gb&title=%E5%B7%A6%E5%82%B3)，均返回 HTTP 403（HTML 错误页，约 3930 bytes），没有取得 CText 文件本体。
- IA 入口：`https://archive.org/metadata/<identifier>` 是本轮核对卷册、贡献者、描述和文件清单的一手 metadata；`https://archive.org/details/<identifier>` 是 item 页面；`https://archive.org/download/<identifier>/<filename>` 是 metadata 中列出的直接文件入口。代表性的 PDF HEAD 请求返回 200，但没有在本轮完成下载。代表 metadata 记录：[说文](https://archive.org/metadata/06050615.cn)、[礼记](https://archive.org/metadata/06048491.cn)、[左传](https://archive.org/metadata/06050393.cn)、[急就篇](https://archive.org/metadata/06050614.cn)、[管子](https://archive.org/metadata/06049836.cn)、[论语](https://archive.org/metadata/06043739.cn)。
- V2 边界：Wikisource 页面、CText OCR、搜索结果摘要、文件名/章节命中都只是 locating candidate；不能替代图像底本、选定 edition 或 quote-level passage validation。

## 书目族系与可下载候选

| 书目族系 | CText/版本入口 | 本轮确认的下载候选 | 可下载判断 | 主要失败或保留边界 |
|---|---|---|---|---|
| 说文解字 | CText 主页标为《四部丛刊初编》本；Library 有 [四部丛刊初编 66–69 册](https://ctext.org/library.pl?if=gb&remap=gb&res=77351) 和 [四库全书本](https://ctext.org/library.pl?if=gb&remap=gb&res=77356) | Siku：15 卷/8 册，IA `06050615.cn`–`06050622.cn`；代表 [卷一 PDF](https://archive.org/download/06050615.cn/06050615.cn.pdf) | Siku：是（IA metadata 列出 PDF/CNBook/TIFF）；代表 PDF 3,773,216 bytes | CText 主底本的四部丛刊页未核到 IA/扫描下载文件；Siku 不是同一 edition |
| 礼记 | 主页为《武英殿十三经注疏》本《礼记正义》；[仿宋相台五经](https://ctext.org/library.pl?if=en&res=77828) 明确列卷；[礼记大全](https://ctext.org/library.pl?if=gb&remap=gb&res=5230) 有 Siku 扫描 | Siku《礼记大全》30 卷/18 册，IA `06048477.cn`–`06048494.cn`；代表 [卷一 PDF](https://archive.org/download/06048477.cn/06048477.cn.pdf) | 是（metadata 列出非零 PDF/CNBook/TIFF）；代表 PDF 8,104,161 bytes | 《礼记大全》是明代汇编/注释层，不等于单独的郑玄注或卢植注；仿宋相台五经页未核到下载文件 |
| 左传 | 主页为《武英殿十三经注疏》本《春秋左传正义》；Library 有 [Siku《春秋左传注疏》](https://ctext.org/library.pl?if=gb&remap=gb&res=5566) | Siku 60 卷/32 册，IA `06050387.cn`–`06050418.cn`；本轮点名年份的卷册见下表 | 是（IA metadata 和直接 PDF 入口均可列出）；本轮关键卷 PDF metadata 大小约 6.5–8.9 MB | 年份→卷号需以经文/目录层复核；Siku 注疏包不能直接等同于 CText 主底本的版本身份 |
| 急就篇 | 主页为《四部丛刊续编》本；[CText Library 目录](https://ctext.org/library.pl?if=en&node=279526) 同时列 Siku、古逸丛书、四部丛刊续编、天壤阁丛书 | Siku《急就篇》4 卷/2 册，IA `06050613.cn`–`06050614.cn`；代表 [卷二至卷四 PDF](https://archive.org/download/06050614.cn/06050614.cn.pdf) | 是；代表 PDF 6,568,458 bytes | CText 说有扫描版，但四部丛刊续编条目未核到直接下载文件；Siku 为替代候选 |
| 管子 | 主页为《四部丛刊初编》本；有 [Siku《管子》](https://ctext.org/library.pl?if=gb&remap=gb&res=5559) 和 [四部丛刊初编注本](https://ctext.org/library.pl?if=gb&remap=gb&res=77410) | Siku《管子》24 卷/7 册，IA `06049831.cn`–`06049837.cn`；代表 [卷二十至卷二十二 PDF](https://archive.org/download/06049836.cn/06049836.cn.pdf) | 是；代表 PDF 5,293,170 bytes | `管子注` 的具体注本/作者尚未由 queue 语义唯一确定；四部丛刊注本虽版本清楚但未核到 IA 下载 |
| 论语 | CText Library [Siku《论语注疏》](https://ctext.org/library.pl?if=gb&remap=gb&res=5097) | 20 卷/5 册，IA `06043739.cn`–`06043743.cn`；代表 [卷一至卷三 PDF](https://archive.org/download/06043739.cn/06043739.cn.pdf) | 是；代表 PDF 6,812,183 bytes | CText chapter 页是定位/文本页，不是本地图像冻结；仍需人工确定采用注疏层还是纯经文层 |

IA 记录的共同 metadata 是 `contributor=浙江大学图书馆`、`mediatype=text`，描述通常标明“影印古籍”和 Siku 经/史/子部分类；本轮用 `archive.org/metadata` 直接读取了这些字段和文件清单。可下载表示“IA metadata 暴露了非零文件和直接 URL”，不表示本地已经有文件，也不表示文本已通过 V2 quote check。

## 《礼记》重点篇章映射

《礼记大全》Library/目录页把篇章映射到 Siku 逻辑卷；IA item 的卷册标题可直接对照。以下是本轮重点篇章的可下载候选：

| 队列目标 | CText 逻辑卷/篇 | IA item | 直接文件 | 版本判断 |
|---|---|---|---|---|
| 曲礼 | 卷一曲礼上、卷二曲礼下 | `06048477.cn`、`06048478.cn` | [06048477 PDF](https://archive.org/download/06048477.cn/06048477.cn.pdf)、[06048478 PDF](https://archive.org/download/06048478.cn/06048478.cn.pdf) | Siku《礼记大全》候选 |
| 檀弓 | 卷三檀弓上、卷四檀弓下 | `06048478.cn`、`06048479.cn` | [06048479 PDF](https://archive.org/download/06048479.cn/06048479.cn.pdf) | Siku《礼记大全》候选；覆盖 queue 的普通《檀弓》 |
| 月令 | 卷六月令第六 | `06048481.cn` | [06048481 PDF](https://archive.org/download/06048481.cn/06048481.cn.pdf) | Siku《礼记大全》候选 |
| 乐记 | 卷十八，篇名“乐记第十九” | `06048488.cn`（卷十七至十八） | [06048488 PDF](https://archive.org/download/06048488.cn/06048488.cn.pdf) | Siku《礼记大全》候选；代表 PDF 11,832,680 bytes |
| 祭统 | 卷二十三，篇名“祭统第二十五” | `06048491.cn`（卷二十三至二十四） | [06048491 PDF](https://archive.org/download/06048491.cn/06048491.cn.pdf) | Siku《礼记大全》候选 |

交叉版本方面，[仿宋相台五经](https://ctext.org/library.pl?if=en&res=77828) 目录把曲礼/檀弓放在卷一至三、月令放在卷四至五、乐记放在卷十至十一、祭统放在卷十二至十四；这说明 CText 还有清楚的相台五经版本路径，但本轮未见其可下载扫描文件。`礼记正义` 的 CText Library 条目（[res=237159](https://ctext.org/library.pl?if=gb&remap=gb&res=237159)）能定位曲礼、檀弓、月令等注疏卷，但同样未核到可下载 IA 文件。

`《礼记·檀弓》卢植注` 与 `《礼记·檀弓》郑玄注` 不能用《礼记大全》无条件替代：后者是 Siku 汇编/注释本，前者/后者要求的是特定注本或注释层。本轮没有找到能同时证明“正确注本 + 明确 edition + 可下载底本”的一手文件，仍应保持 unresolved。

## 《左传》点名年份映射

本表采用 CText 的 60 卷《春秋左传注疏》卷序与 [十三经注疏卷目定位页](https://ctext.org/wiki.pl?chapter=919059&if=gb&remap=gb) 对照，再连接 Siku IA item；不是以 Wikisource 转录正文作为 canonical。

| queue 目标 | 逻辑卷 | IA item / 卷册标题 | 直接 PDF |
|---|---:|---|---|
| 闵公二年 | 11 | `06050393.cn`，卷十一至十二 | [PDF](https://archive.org/download/06050393.cn/06050393.cn.pdf) |
| 僖公二十二年 | 15 | `06050395.cn`，卷十五至十六 | [PDF](https://archive.org/download/06050395.cn/06050395.cn.pdf) |
| 文公五年 | 19 | `06050397.cn`，卷十九至二十 | [PDF](https://archive.org/download/06050397.cn/06050397.cn.pdf) |
| 襄公十九年 | 34 | `06050405.cn`，卷三十四至三十五 | [PDF](https://archive.org/download/06050405.cn/06050405.cn.pdf) |
| 襄公二十年 | 34 | `06050405.cn`，卷三十四至三十五 | 同上 |
| 襄公二十九年 | 39 | `06050407.cn`，卷三十八至三十九 | [PDF](https://archive.org/download/06050407.cn/06050407.cn.pdf) |
| 昭公十一年 | 45 | `06050410.cn`，卷四十四至四十五 | [PDF](https://archive.org/download/06050410.cn/06050410.cn.pdf) |
| 昭公二十年 | 49 | `06050412.cn`，卷四十八至四十九 | [PDF](https://archive.org/download/06050412.cn/06050412.cn.pdf) |
| 昭公二十五年 | 51 | `06050413.cn`，卷五十至五十一 | [PDF](https://archive.org/download/06050413.cn/06050413.cn.pdf) |

其中 `06050393.cn`、`06050395.cn`、`06050397.cn`、`06050405.cn`、`06050407.cn`、`06050410.cn`、`06050412.cn`、`06050413.cn` 的 IA metadata 均返回了浙江大学图书馆贡献者、Siku 60 卷/32 册描述和非零 PDF 文件；例如 `06050413.cn` 的 metadata 标题为“春秋左傳注疏·卷五十~卷五十一”，PDF 大小为 6,579,731 bytes。这个结果足以建立候选卷册清单，但还没有完成逐页图像核对。

## 其余重点书目

### 说文解字

[CText 主页](https://ctext.org/shuo-wen-jie-zi/zhs) 将主要电子底本标为《四部丛刊初编》本，Library 的 [res=77351](https://ctext.org/library.pl?if=gb&remap=gb&res=77351) 给出“初编 66–69 册”、汉许慎撰/宋徐铉校定等 edition 信息，但本轮没有看到 IA/扫描下载行。另一条 [Siku res=77356](https://ctext.org/library.pl?if=gb&remap=gb&res=77356) 明确为《钦定四库全书》本，15 卷/8 册，IA `06050615.cn`–`06050622.cn`；其 metadata 将 `06050615.cn` 标为卷一上下，PDF 可由 [直接入口](https://archive.org/download/06050615.cn/06050615.cn.pdf) 下载。故《说文解字》已有高信任的 Siku 下载候选，但还没有 CText 主底本的可下载 freeze 来源。

### 急就篇

[CText 主页](https://ctext.org/jijiupian/zh) 的主电子底本是《四部丛刊续编》本，并说明存在扫描版本；[Library 目录](https://ctext.org/library.pl?if=en&node=279526) 可见 Siku、古逸丛书、四部丛刊续编和天壤阁丛书。Siku [res=5451](https://ctext.org/library.pl?if=en&res=5451) 为《钦定四库全书》本，4 卷/2 册，IA `06050613.cn`（卷一）和 `06050614.cn`（卷二至四），均有浙江大学图书馆/CADAL metadata；卷二至四的 [PDF 直接入口](https://archive.org/download/06050614.cn/06050614.cn.pdf) 已确认列在 IA 文件清单。古逸丛书的 [CText OCR/目录页](https://ctext.org/wiki.pl?chapter=706489&if=gb&remap=gb) 能识别“光绪十年甲申”“仿唐石经体写本”等版本信息，但本轮未找到可下载扫描文件。

### 管子

[CText 主页](https://ctext.org/guanzi/zhs) 的主电子底本是《四部丛刊初编》本；[Siku res=5559](https://ctext.org/library.pl?if=gb&remap=gb&res=5559) 为《钦定四库全书》本，24 卷/7 册，IA `06049831.cn`–`06049837.cn`，所有目标篇章可按卷册定位：

| queue 目标 | Siku 逻辑卷 | IA item |
|---|---:|---|
| 《管子·形势》 | 卷一至三 | `06049831.cn`，[PDF](https://archive.org/download/06049831.cn/06049831.cn.pdf) |
| 管子·地员 | 卷十六至十九 | `06049835.cn`，[PDF](https://archive.org/download/06049835.cn/06049835.cn.pdf) |
| 管子·形势解 | 卷二十至二十二 | `06049836.cn`，[PDF](https://archive.org/download/06049836.cn/06049836.cn.pdf) |

`管子注` 不能仅凭 Siku《管子》解决。CText [四部丛刊初编注本 res=77410](https://ctext.org/library.pl?if=gb&remap=gb&res=77410) 标明（唐）房玄龄注、常熟瞿氏铁琴铜剑楼藏宋刊本、24 卷，但本轮未核到其 IA 下载行；另有 [《管子·地员篇注》res=2566](https://ctext.org/library.pl?if=en&res=2566) 的后出注本，页面注明有字迹不清和残页，不能把它当作 queue 所需的通用“管子注” canonical。

### 论语

[CText Library res=5097](https://ctext.org/library.pl?if=gb&remap=gb&res=5097) 为《钦定四库全书》本《论语注疏》，20 卷/5 册，IA `06043739.cn`–`06043743.cn`。篇章映射为：为政在卷一至三（`06043739.cn`）、乡党在卷九至十三（`06043741.cn`）、微子在卷十六至二十（`06043743.cn`）。对应的 [为政 PDF](https://archive.org/download/06043739.cn/06043739.cn.pdf)、[乡党 PDF](https://archive.org/download/06043741.cn/06043741.cn.pdf)、[微子 PDF](https://archive.org/download/06043743.cn/06043743.cn.pdf) 均有 IA metadata 文件记录；CText 的 [为政](https://ctext.org/wiki.pl?chapter=764750&if=gb)、[乡党](https://ctext.org/wiki.pl?chapter=723389&if=en)、[微子](https://ctext.org/wiki.pl?chapter=485747&if=gb&remap=gb) 页只用于篇章/卷次定位。

## 失败原因与 canonical 风险

| 检查项 | 结果 | 对 V2 的含义 |
|---|---|---|
| CText Library 直接访问 | 代表性 Library URL 均 HTTP 403 | 不能从本轮直接响应取得 CText 文件；网页仍只能作目录/版本定位 |
| CText 主电子底本的下载 | 《说文》四部丛刊初编、《急就篇》四部丛刊续编、《管子》四部丛刊初编、相台五经《礼记》等未核到直接 IA 文件 | 不能把 Siku 替代版伪装成 CText 主底本；若必须复现主底本，需要新的授权/可访问扫描入口 |
| IA 文件可用性 | metadata 有非零 PDF/CNBook/TIFF，代表性 PDF HEAD 200；部分后续 HEAD 请求有 IA 网络连接错误 | “可下载候选”已成立，但本轮未完成实际传输和本地完整性核验 |
| OCR/转录正文 | CText Wiki、Wikisource、搜索摘要可用于找卷/篇 | 不得作为 canonical passage 或 quote validation 证据 |
| 注本层 | 《礼记大全》、`论语注疏`、`春秋左传注疏`、Siku《管子》都包含注疏/汇编层 | 需要先决定 V2 证据要经文、正义、郑玄注、卢植注还是其他注本，再冻结相应图像 |

## 能否形成 local freeze package

可以形成“候选包规划”，目前不能报告为已经形成的本地 freeze package。

候选包优先级如下：

1. 若接受 Siku 替代版，六个书族均有 IA item、卷册标题、馆藏/扫描 metadata 和直接文件 URL；《左传》9 个年份、《礼记》5 个重点篇章、《论语》3 篇、《管子》3 个明确篇章均已有卷册映射。
2. 若要求 CText 主底本完全一致，当前至少《说文》《急就篇》《管子》《礼记》相台五经缺少本轮可验证的下载文件；《礼记·檀弓》郑玄注/卢植注还缺明确的注本匹配。因此只能保留为 unresolved，不能由 Siku package 自动关闭。
3. 真正冻结时应在批准的本地目录保存选定的 IA item metadata、原始图像/CNBook（必要时另存 PDF derivative）、直接 URL、edition、卷册到篇章映射、下载响应记录和文件完整性记录；完成后仍需逐条 canonical passage/quote check，再进入 V2 人工审核链。本轮没有执行这些写入或下载动作。

本轮未修改 `v2/` 下 SQLite、manifest、queue、production status 或其他状态文件；只写入本报告。
