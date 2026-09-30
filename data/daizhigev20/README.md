[殆知阁网站 daizhige.org](https://daizhige.org/) 中国古典文献全文检索工具 

## 格式转换

本项目已将原始 TXT 文件全部转换为 Markdown 格式，并确保其渲染结果与原版保持一致。在此基础上，作为简单扩展，在文件头部增加了 YAML 格式的元数据。

## 错误修正

* **繁简转换错误**：在古文献中发现了相当数量的「记忆体」(实际应为「内存」)、「香港脚」（实际应为「脚气」）、「利瓦伊」（实际应为「李维」）等，这些是某些繁简转换工具造成的错误，目前发现的已全部修复。
* **非文献内容**：原始文本部分来自现已关闭的论坛；在复制过程中，部分文本被贴上了论坛的内容及链接。
* **HTML及脚本**：某些文本中存在 HTML 及脚本代码，数据清洗不够精确。
* **重新导入与互校**：对重点典籍（如《宋史》《本草纲目》《全唐文》等），以维基文库校对文本或点校本重新导入、按卷拆分，并与其他传本互校，保留校勘记；修正之处以编校注及 frontmatter 元数据注明依据。

## 检索工具部署方法

[本 fork](https://github.com/daizhige-org/daizhigev20/) 建立了一个基于 Elasticsearch 的可检索版本，包括导入脚本。部署方法详见[DEPLOYMENT.md](https://github.com/daizhige-org/daizhigev20/blob/tools/DEPLOYMENT.md)。

## 下载说明

如需获取完整的文本文件，可通过以下方式：

* 若仅需获取数据文件，可使用以下命令克隆仓库 `data` 分支的最新版本：
    ```bash
    git clone --branch data --depth 1 https://github.com/daizhige-org/daizhigev20.git
    ```
  这将仅下载 data 分支的最新快照，不包含完整提交历史。
* 若要进行开发（例如代码修改或生成数据），应改为克隆 `tools` 分支。`data` 分支在此情境下作为一个 Git 子模块（submodule）管理，保持与主仓库同步。
* GitHub Pages 打包下载：访问 GitHub repo Actions 页面找到最新一次 "Deploy GitHub Pages" 运行，下载名为 `github-pages` 的 artifact 压缩包（仅包含站点正文，不含原始数据快照等辅助文件）。截至 2026 年 7 月，此压缩文件的总体积约为 2.15GB。
