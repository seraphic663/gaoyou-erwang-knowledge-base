# 高邮二王知识库网站

> 当前运行边界复核于 2026-10-31。网站是研究整理和操作原型；页面汇总不改变来源记录或人工审核状态。

## 本地运行

需要 Node.js 18+ 和 Python 3。从仓库根目录运行：

```powershell
npm --prefix solution/website start
```

默认地址为 `http://localhost:3000/`；可通过 `PORT` 指定端口。Railway 从根 `railway.toml` 使用 `ops/Dockerfile` 构建。运行时依赖在 `ops/package.json`，网站依赖和构建任务在本目录 `package.json`。

## 页面

| 路径 | 用途 | 数据身份 |
| --- | --- | --- |
| `/` | 项目定位与代表案例入口 | 展示导航 |
| `/library`、`/terms` | 字词关系视图 | 四书机器库 |
| `/cases` | 案例视图，可切换字词/案例分组 | 默认四书机器库；`source=annotation` 为独立人工库 |
| `/corpus` | 原典与外典统一检索 | 只读语料检索 |
| `/reading-lab` | v1/v2 五步校读实验与本次材料展示 | 直接回答与检索材料实验 |
| `/audit` | 旧案例审校/记录入口 | 不与机器库候选身份合并 |

## 数据和 API

- 四书机器库随应用发布压缩 bundle。当前入口为 `GET /api/machine/meta`、`GET /api/machine/search`、`GET /api/machine/detail`；新构建不读取旧 `dictionary.db`，机器库缺失时不回退旧库。详见 [机器库实现与发布契约](MACHINE-LIBRARY.md)。
- 人工标注浏览只读 `/api/annotation/bootstrap`、`/api/annotation/index`、`/api/annotation/detail` 和 `/api/annotation`。来源库为 `data/D-标注/05-数据库/annotations.db`；`annotation-snapshot.json` 从该库导出。
- `/api/corpus/unified-search` 接收检索 POST 请求；正文检索和书名命中分别计数。它不把候选自动写入 machine library 或 V2。
- `/api/v2/*` 是独立 V2 案例、审校和五步流程接口，状态门禁仍由 V2 数据库控制。
- `/api/health` 报告旧 SQLite snapshot 的状态，不代表 `/api/machine/meta` 的机器库状态。报告中注明自己引用的接口与数据身份。

## 构建

本地重新解析四书是显式操作，页面 UI 更新不触发解析：

```powershell
npm --prefix solution/website run machine:build -- --workers 4
npm --prefix solution/website run machine:pack
```

压缩包及 manifest 是运行输入；原始 SQLite 是生成产物。manifest 记录 source、parser、输入清单、内容哈希和 bundle 大小。更新原典或 parser 后才重建，并依据 [机器库契约](MACHINE-LIBRARY.md) 检查输出。

人工标注快照只在人工数据库完成预期更新后导出：

```powershell
npm --prefix solution/website run sync:annotation
```

旧 `sync:sqlite` 任务已移除。不得用旧 dictionary.db 覆盖当前机器库，也不得把人工快照复制进 V2。

## 发布和验证

上传成功不等于部署已切换。以 Railway deployment status、运行时 `/api/machine/meta`、关键查询和 `/api/annotation/bootstrap` 的发布前后核对作为发布证据。机器库发版应确认 `run.id`、content SHA 和 manifest 一致；人工数据库保持独立。

本地页面、接口和生成报告属于不同证据。若浏览器自动化未能读取线上页面，明确说明限制，不把本地截图写成线上 UI 验收。
