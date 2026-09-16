# 五步审计卡的 DeepSeek API 模型选择

调研基准：2026-09-15。仅核对 DeepSeek 官方 API 文档和仓库中的模型调用配置。

## 结论

首版建议用 API ID `deepseek-flash`，对应产品版本 **DeepSeek-V4.1-Flash**。`deepseek-v4-flash` 是已退役版本的兼容名称，目前也会路由到 V4.1-Flash；新配置不应再用它。官方 API 目前列出的 Pro ID 是 `deepseek-v4-pro`，对应 **DeepSeek-V4-Pro-0813**，不是 V4.1-Pro。

有一处口径需谨慎：较早的官方搜索摘要曾显示 V4 Pro 请求会在 9 月 14 日后转到 Flash；但我无法直接读取该新闻页。当前可直接读取的定价页和更新日志均明确说 V4 Pro 在 9 月 14 日后继续提供、计费不变，并分别列出 Pro 版本和价格。以下按这两份当前页面记录 API 状态；未用账户密钥做实调。

| API ID | 当前版本 | 缓存未命中输入价（高峰 / 空闲） | 输出价（高峰 / 空闲） |
|---|---|---:|---:|
| `deepseek-flash` | V4.1-Flash | $0.30 / $0.15 | $1.20 / $0.60 |
| `deepseek-v4-pro` | V4-Pro-0813 | $1.32 / $0.66 | $3.96 / $1.98 |

另：缓存命中输入价分别为 Flash `$0.006 / $0.003`、Pro `$0.044 / $0.022`。均为美元/百万 tokens；空闲价是高峰价一半，高峰为工作日 UTC 01:00–04:00、06:00–10:00（北京时间 09:00–12:00、14:00–18:00）。因此 Flash 的未缓存输入约便宜 4.4 倍、输出约便宜 3.3 倍。详见[官方模型与价格表](https://api-docs.deepseek.com/quick_start/pricing/)及[更新日志](https://api-docs.deepseek.com/updates/)，后者列有 V4.1-Flash 通用基准成绩。

**建议：**五步卡首版默认 `deepseek-flash`，显式设 `reasoning_effort: "high"`，用现有 Chat Completions 的 `response_format: {"type":"json_object"}` 输出草稿，并在本地校验五步字段、引文来源和完整性。官方更新日志列出的是通用基准，不是古籍训诂/中文学术审校测试；建议拿一小批同样本盲测 Flash 与 Pro，由人工按证据对应、引文准确、推理可追溯和无据断言评分，再决定是否为难例切换 Pro。此处是基于成本与任务边界的建议，不是对该领域准确率的已验证结论。

实现范围已据此支持审校者在 `deepseek-flash` 与 `deepseek-v4-pro` 间选择，并选择 `none/low/high/max`；默认仍是 Flash + high。每条已提交审计记录保存请求模型、API 返回模型、effort、用量、提示版本和 V2 案例指纹。

DeepSeek 的 JSON Output 需在提示中明确要求 JSON 并给出示例，合理设置 `max_tokens`；官方提示仍可能返回空内容，或在 `finish_reason="length"` 时截断，因此要把解析/Schema 校验失败留为待修草稿。若需 API 层按 JSON Schema 约束输出，可评估 Responses API 的 `json_schema` 格式。思考模式默认启用、默认 effort 为 high；开启思考时 `temperature` 不生效。参考[Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)、[JSON Output 指南](https://api-docs.deepseek.com/guides/json_mode/)、[Thinking Mode 指南](https://api-docs.deepseek.com/guides/thinking_mode/)和[Responses API](https://api-docs.deepseek.com/api/create-response/)。

## 仓库现状

- `03-项目网站/src/config.js:106` 固定为 `deepseek-v4-pro`；`src/ai-annotation.js:220-240` 调 `/chat/completions`，已使用 JSON Output。它的 `temperature: 0.2` 在默认思考模式下不生效。
- `v2/scripts/run_unified_ingress.py:71,124-179` 默认 `deepseek-v4-flash`，允许 `DEEPSEEK_MODEL` 覆盖，调用 Chat Completions 并在本地解析/校验 JSON；该旧 ID 当前只是 V4.1-Flash 的兼容路由。新五步卡应显式记录实际请求 ID 和响应返回的模型信息。
