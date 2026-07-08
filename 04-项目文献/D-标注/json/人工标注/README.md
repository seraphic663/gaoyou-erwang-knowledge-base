# 人工标注 JSON 提交区

成员从本地标注工作台导出的 `*.annotation.json` 放在这里。

建议结构：

```text
人工标注/
├─ 张三/
│  └─ 造舟于河_张三.annotation.json
└─ 李四/
   └─ 平原之隰_李四.annotation.json
```

规则：

1. 一个案例一个 JSON 文件。
2. 文件名尽量包含案例标题和提交者。
3. 不要手工修改 `full_json/`、`ai_json/`、`annotations.db` 或网站快照。
4. 提交前先确认 JSON 中没有 `【必填】`、`【建议】`、`【选填】`。
