# 原著标准化与本地审阅

本目录保存从二王原著与外典建立的只读语料发布、位置映射和浏览页面。清理后的当前发布使用 `structure-clean`；原著文件、旧发布和历史试验结果彼此分开保存。

[清理后原著审阅（3269）](http://127.0.0.1:3269/) · [冻结的 v3 三方对比（3266）](http://127.0.0.1:3266/#view=comparison) · [冻结的 v2 对比（3267）](http://127.0.0.1:3267/#view=comparison) · [small 标签判读实验页（3268）](http://127.0.0.1:3268/)

## 当前发布与历史边界

- `generated/release-20261025-small-clean/` 是按 small 标签清理后的原著建立的新发布。新发布单独保存原文快照、规范化文本和字符映射；网页中的位置按此快照重新计算。
- 该发布清单的 `source_cleanup_note` 指向四份原著清理复核，并记录了 288 个白名单来源均未检出残留标签。这个说明是本次构建的证据记录，不由切分模式自动推断；后续输入需要按自己的快照另行核验。
- `structure-clean` 是本地构建的默认模式，以 v2 通用章卷、条目、段落和括注处理为底座。它不再识别或切分 `<small>` 标签；通用成对括注仍参与切点保护、相邻正文注释并接和续接标记。
- v1、v2、v3 发布库、比较结论及 84 次 DeepSeek 请求记录保持冻结。各轮比较对应不同样本和基线；small 标签两条件试验也不构成本次切分效果评价。见 [v2 对比](COMPARISON-v2.md)、[v3 对比](COMPARISON-v3.md) 和原始[试验报告](evaluation/small-boundary-20261025/REPORT.md)。
- 新版没有证明注释识别更准确。`role` 是排版线索，不判定具体作者；括注关系和切分结果仍需结合原文复核。

旧定位继续使用历史服务及其旧坐标：3266 对应 v3 发布，3267 对应 v2 发布。清理标签会改变后续字符位置；新版 3269 的定位只按清理后原文解释。不要把旧片段偏移直接套到新版原文。

## 字符与位置

原文按 UTF-8 读取，保留原字、换行、缺损标记和现有书目信息；本处理程序不改写输入文件。每个源文件单独保存，不因书名相同而合并。规范化只用于检索：逐字符做 Unicode NFKC，再合并连续空白，不转简繁、不猜缺字。引用和映射视图仍显示对应发布中的原文。

原文位置按整个文件的 Unicode codepoint 计数，包括书目前置信息；规范化位置按片段计数。区间均为左闭右开。一个原字展开成多个规范化字符、或多个空白合成一个字符时，映射会保留对应关系。

## 本地页面

分别在 PowerShell 7 终端运行服务。页面仅监听本机并提供只读接口。

清理后当前发布：

```powershell
python -B solution/corpus-standardization/server.py `
  --data 'D:\26大创\solution\corpus-standardization\generated\release-20261025-small-clean' `
  --port 3269
```

冻结的 v3 三方比较：

```powershell
python -B solution/corpus-standardization/server.py `
  --data 'D:\26大创\solution\corpus-standardization\generated\release-20261025-v3' `
  --comparison 'D:\26大创\solution\corpus-standardization\evaluation\v3\run\comparison.json' `
  --port 3266
```

冻结的 v2 双版比较：

```powershell
python -B solution/corpus-standardization/server.py `
  --data 'D:\26大创\solution\corpus-standardization\generated\release-20261024-v2' `
  --comparison 'D:\26大创\solution\corpus-standardization\evaluation\run-20261024-v2\comparison.json' `
  --port 3267
```

3269 用于查看新原文、检索块和映射；3266、3267 保留旧版坐标及比较页。3268 是单独的 small 标签实验页面，不属于本次代码或发布更新。

## 生成与检查

新建发布必须使用此前未存在的输出目录；默认采用 `structure-clean`。旧发布目录不得覆盖：

```powershell
python -B solution/corpus-standardization/pipeline.py build `
  --workspace 'D:\26大创' `
  --output 'D:\26大创\solution\corpus-standardization\generated\next-run'
```

如需研究旧模式，须显式指定 `--segmentation structure-v3` 或 `--segmentation fixed`。它们仅用于对应旧算法实验；旧发布应直接读取保存的发布库，不要用清理后的源文件重建并称为原历史版本。

检查命令：

```powershell
python -B -m unittest discover -s solution/corpus-standardization/tests -v
node --check solution/corpus-standardization/web/app.js
```

结构检查覆盖原文哈希、映射、正文覆盖、位置和 SQLite 完整性；它不等同于语义审定、切分优劣或模型效果。

## 主要文件

| 文件 | 用途 |
| --- | --- |
| `pipeline.py` | 读取、规范化、位置映射、切分与结构校验 |
| `segmentation_clean.py` | 新默认 `structure-clean`，仅处理通用版式与括注线索 |
| `segmentation_v2.py` | 历史 v2 算法实现，保留供复现 |
| `segmentation.py` | 历史 v3 实验算法实现，保留供复现 |
| `server.py`、`web/` | 本地只读接口与审阅页面 |
| `tests/` | 合成文本、映射和服务检查 |
| `generated/release-20261023-v1/` | 冻结的定长发布 |
| `generated/release-20261024-v2/` | 冻结的 v2 结构发布 |
| `generated/release-20261025-v3/` | 冻结的 v3 实验发布 |
| `generated/release-20261025-small-clean/` | small 标签清理后的当前发布 |
| `evaluation/small-boundary-20261025/REPORT.md` | 原 21 例、84 次请求试验报告，原样保留 |

三方对比中 32 个位置已用于历史评价；不把它们复用成新版本的盲测结果。87 份人工校勘案例也不提供切分边界 gold，详见 [适用性盘点](evaluation/v3/GOLD-AUDIT.md)。

## 评价记录的公开范围

版本库保留评价协议、脚本和汇总结论。`evaluation/` 下的 JSON/JSONL 与预览图包含历史样本、标注、盲评密钥及模型请求记录，按本目录 `.gitignore` 留在本地，不随源码发布；克隆仓库后不能据此重放历史评价，也不应把旧样本当作未见测试集。后续正式评测应另建并登记新的隔离样本。
