# 三方匿名切分初评说明

只读 `blind_packets.json` 和本说明；不要读取 `method_key.json`、`comparison.json` 或任何旧评分。A、B、C 是随机字母，不能从长度、标题或文风猜方法。每处样本共用同一原文锚点、附近原文和可选的 `reference_spans`。后者是从原文件按位置摘出的补充原文，可用于核查最近的实际标题候选；它也不是标准答案。

三列各自的 `source_title`、`heading` 与 `role` 原样来自相应发布版；`heading`、`role` 都只是算法候选。判断缺条头、说话者、注释解释对象和序跋角色时，回到共同的原文参考核对；不能把某一列识别到的标题或角色当作正确答案。检索块 `text` 是主评对象；`reading_text` 只用于备注它是否帮助读者恢复上下文。共同原文参考不属于任何方法的输出，不能给某列记功。

每列独立填写五维分数：`0` 无此问题，`1` 局部问题，`2` 明显妨碍理解或定位，`null` 证据不足。维度如下：

| 键 | 核查问题 |
| --- | --- |
| `missing_heading` | 当前锚点需要的真实卷、章、条头或说话者提示是否缺失或错配。普通正文无需条头时记 0。 |
| `cut_note` | 注释本身是否被截断。没有注释的普通正文记 0。 |
| `detached_note` | 注释是否与它解释的正文、对象或说话者脱离。没有注释的普通正文记 0。 |
| `unrelated` | 是否混入另一条、另一说话者或无关序跋，影响当前锚点理解。 |
| `cut_body` | 正文或当前论述是否在关键处被截断；普通半句截断只记此项，不转记断注。 |

特别核对当前锚点的说话者、注释解释对象，以及序、跋、案语与正文的角色边界。必要时可只读原文件更大上下文核查，并在该项 `extra_source_ranges` 记录实际查看的原文件 codepoint 区间，例如 `[{"start": 100, "end": 450}]`。看不到足够原文时，该维记 `null`；不要凭提供的候选标题补事实。每列写简短 `reason`，指出实际原文边界与影响。

三组两两判断都要填写：`A:B`、`A:C`、`B:C`。`preferred` 只能取该对中的字母、`tie`、`undetermined`。综合判断围绕当前锚点的结构完整性与混入风险；长度更长不自动算改善。若两列各有得失、证据不足，填 `undetermined` 并在 `reason` 说明取舍。`tie` 用于证据足以判断效果相当。阅读窗口的帮助或不足写在 `reading_note`，不要把共同原文参考算成某列的能力。

输出 UTF-8 JSON，完整 32 项合并到一个 `items` 数组。每项格式如下（五维键每列都要齐全）：

```json
{
  "items": [
    {
      "id": "样本ID",
      "A": {"scores": {"missing_heading": 0, "cut_note": 0, "detached_note": 0, "unrelated": 0, "cut_body": 1}, "reason": "正文在当前句中断。"},
      "B": {"scores": {"missing_heading": 0, "cut_note": null, "detached_note": null, "unrelated": 0, "cut_body": 0}, "reason": "注释关系所需原文不足。"},
      "C": {"scores": {"missing_heading": 0, "cut_note": 0, "detached_note": 0, "unrelated": 0, "cut_body": 0}, "reason": "当前论述完整。"},
      "pairwise": {
        "A:B": {"preferred": "undetermined", "reason": "边界与注释证据不足，无法强排。"},
        "A:C": {"preferred": "C", "reason": "C 保留当前完整句。"},
        "B:C": {"preferred": "tie", "reason": "已见范围内效果相当。"}
      },
      "reading_note": "阅读窗口可恢复前句，但主评仍按检索块。",
      "extra_source_ranges": []
    }
  ]
}
```
