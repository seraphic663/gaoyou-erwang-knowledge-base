# D-标注 JSON 流程

现在只保留一个脚本：

```text
run.py
```

主要结果目录：

```text
full_json/  DOCX 完整转换 JSON
ai_json/    DeepSeek 整理后的 JSON
```

辅助目录：

```text
ai_json_failed/  DeepSeek 调用失败时保存的原始响应
```

旧的 `annotation_db/` 不再保留。人工标注数据库统一放在 `02-数据库/data/annotations.db`，与主库 `dictionary.db` 相邻，但由 `02-数据库/annotation/` 独立管理。

不写主库。

这里的”不写数据库”指不碰 `02-数据库/data/dictionary.db` 主库。`run.py` 会自动创建独立的标注库：

```text
02-数据库/data/annotations.db
```

它只用于暂存人工标注和 AI 整理结果，和原数据库不冲突。数据库操作委托到 `02-数据库/annotation/importer.py`。

## 1. DOCX 转完整 JSON

```bash
python 04-项目文献/D-标注/json/run.py
```

输出到：

```text
04-项目文献/D-标注/json/full_json/
```

完整 JSON 保留：

- 段落顺序，包括空段落
- 段落文本和 run 级基础格式
- 表格
- 批注
- 批注锚点
- 脚注/尾注
- checksum
- 初步标注块

## 2. 调 DeepSeek 整理 JSON

PowerShell：

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的key"
python 04-项目文献/D-标注/json/run.py --api
```

输出到：

```text
04-项目文献/D-标注/json/ai_json/
```

只处理一个文件：

```bash
python 04-项目文献/D-标注/json/run.py --api --only 经传释词
```

已经有 `full_json`，不想重转 DOCX：

```bash
python 04-项目文献/D-标注/json/run.py --api --skip-convert
```

## 3. 录入第二数据库

如果已经有 `ai_json/`：

```bash
python 04-项目文献/D-标注/json/run.py --skip-convert --import-ai
```

调 DeepSeek 后直接录入第二数据库：

```bash
python 04-项目文献/D-标注/json/run.py --api --import-ai
```

录入后，`ai_json` 会自动加状态：

```json
{
  "database_ingestion": {
    "imported": true,
    "database": "02-数据库/data/annotations.db",
    "imported_at": "..."
  }
}
```

每个 `case` 也会有：

```json
{
  "database_ingestion": {
    "imported": true,
    "annotation_case_id": 1,
    "imported_at": "..."
  }
}
```

## API key 怎么写

推荐固定写到本目录 `.env`：

```text
04-项目文献/D-标注/json/.env
```

内容：

```text
DEEPSEEK_API_KEY=sk-你的key
```

`.env` 已加入 `.gitignore`，不会提交。

也可以临时写环境变量：

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."
```

## 第二数据库

只初始化数据库：

```bash
python 04-项目文献/D-标注/json/run.py --init-db
```

`--init-db` 只建表，不导入内容。导入必须显式使用 `--import-ai`，不会自动混入主库。

## 说明

- 脚本会自动校验 `full_json` 的段落数、批注数、文本长度和 checksum。
- 脚本会校验 `ai_json` 的枚举字段。
- DeepSeek 只接收瘦身后的字段，不发送完整 package 清单。
- 写入 `02-数据库/data/annotations.db`，不与主库 `dictionary.db` 混用。
