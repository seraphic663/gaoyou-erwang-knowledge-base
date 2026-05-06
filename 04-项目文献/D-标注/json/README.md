# D-标注 JSON 流程

现在只保留一个脚本：

```text
run.py
```

两个结果目录：

```text
full_json/  DOCX 完整转换 JSON
ai_json/    DeepSeek 整理后的 JSON
annotation_db/ 独立人工标注 SQLite
```

不写数据库。

这里的“不写数据库”指不碰 `02-数据库/data/dictionary.db` 主库。`run.py` 会自动创建一个独立的空库：

```text
04-项目文献/D-标注/json/annotation_db/annotation_results.db
```

它只用于以后暂存人工标注和 AI 整理结果，和原数据库不冲突。

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
    "database": "annotation_db/annotation_results.db",
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

当前只建表，不导入内容。后面等 `ai_json/` 稳定后，再加一个明确的导入开关，不会自动混入主库。

## 说明

- 脚本会自动校验 `full_json` 的段落数、批注数、文本长度和 checksum。
- 脚本会校验 `ai_json` 的枚举字段。
- DeepSeek 只接收瘦身后的字段，不发送完整 package 清单。
- 暂时不碰 `02-数据库`。
