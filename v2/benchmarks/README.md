# 检索层 benchmark

> 当前版本：2026-09-29
>
> 本目录保存当前可重复的 retrieval-layer 评价定义。它不是端到端考据 benchmark，也不表示相关案例已经全部人工审校。

## 1. 当前 benchmark

主要 manifest 是 v2/benchmarks/case2query2retrieve.v1.json，包含 20 个主案例和 4 个诊断控制样本，按四部 canonical works 平衡抽样。

它评价：

- case-to-query 构造后的原文定位；
- canonical passage 的排序；
- Recall@k 和 MRR；
- hard negative；
- source 或 scope violation；
- 简繁转换、无命中和无效 query 等诊断边界。

v1 使用确定性的 normalized substring ranker、标题权重和 match-window excerpt，不把 AI rerank 混入基础召回指标。未来加入 AI rerank 时，必须在同一 manifest 上单独报告。

## 2. 这个 benchmark 不代表什么

- 不代表 7,581 个 V2 cases 已完成人工审校。
- 不代表案例已经成为 V2 gold。
- 不评价完整五步论证、答案正确率或证据归因。
- 不评价 generic search agent 与 domain-specific harness 的差异。
- 不把页面视觉结果当作检索指标。

端到端考据 benchmark 需要另行定义任务问题、结构化答案、证据角色、难度、hard negatives、unresolved 规则、数据划分和人工复核协议。只有这些字段冻结后，案例才可称为 benchmark-ready。

## 3. 人工标注库搜索 benchmark

人工标注库使用 /api/annotation。这条 benchmark 只检查 query 返回的案例 ID 集合：

    关键词 -> 案例 ID 集合

Manifest 是 v2/benchmarks/annotation-search.v1.json，包含精确案例、方法、字词、证据出处、简繁转换、待补内容和元数据排除控制样例。

指标包括 exact set accuracy、missing、extra、duplicate、micro precision、micro recall、roundtrip time 和 server time。结果顺序不计分。

## 4. 运行

本地或 Railway 运行人工标注库搜索 benchmark：

    python v2/scripts/run_annotation_search_benchmark.py --base-url http://localhost:3311 --output tmp/annotation-search-local.json
    python v2/scripts/run_annotation_search_benchmark.py --base-url https://gaoyou-demo.up.railway.app --output tmp/annotation-search-railway.json

对 V2 retrieval benchmark，先使用只读 V2 数据库启动网站，再运行：

    python v2/scripts/run_retrieval_benchmark.py --base-url http://localhost:3311 --output tmp/benchmark-local.json

网站和 benchmark 使用同一只读检索接口，不另造一套排序逻辑。

## 5. 后续扩展

后续扩展必须从人工确认案例开始，先建立 benchmark-ready manifest，再比较 LLM-only、普通检索/RAG、generic search agent 和 domain-specific harness。每种系统必须固定模型、材料、工具、预算和输出协议，并分别报告检索、答案、证据归因、错误来源、拒答和人工修改量。
