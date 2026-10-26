# Railway 部署验收（2026-10-26）

- 生产入口：[校读实验](https://gaoyou-demo.up.railway.app/reading-lab)。部署 61663375-b1f4-43db-8328-6066fd4f77e8 状态 **SUCCESS**；镜像 digest 为 sha256:aa3e81b2dd4dbfd43feb777f35018a53e6e8b8bfe90e10f00e8c9ccaf5a79b63。构建日志核对外典 bundle SHA-256 1c8e21fe58b6ab82c6a2f5b82f11c44f61602b8f486dc32b316d1b68de4dd84f（74,425,528 字节），并在镜像内解包为 284 个来源、193,314 个文本块。
- 页面检查：/、/reading-lab、/corpus、/audit，以及 reading-lab 和 corpus 的 CSS / JS 均 HTTP 200；校读页标题、主标题和对照操作控件存在。
- API 检查：/api/health、/api/v2/summary、/api/reading-harness/summary 均 HTTP 200。外典汇总为 284 个来源、193,314 个文本块；high 30 / 24,148，mid 42 / 31,763，low 212 / 137,403。
- POST /api/corpus/unified-search：显式空分档返回 HTTP 400，message 为 no_collection_selected；原典书名模式以“读书杂志”检索返回 HTTP 200、8 条书名命中；分别从 high / mid / low 档实测正文检索，均 HTTP 200，返回 4 / 5 / 6 条，结果均属于所选档、类型为 external_chunk、范围为正文命中。
- 父任务另行完成一次云端 v2 真实生成：HTTP 200、ok=true、提示版本 reading-harness.collation.v3，得到 5 步、5 份材料、6 条引文，用时 69.4 秒；完整响应保存在 online-v2-response.json。本代理的验收未调用模型或生成接口。
- 完整线上浏览器交互未验收：浏览器 tab 创建工具超时；本地 UI 的多档检索、材料折叠和定位高亮检查通过。此次部署与只读检索验收未写生产数据库或 volume。