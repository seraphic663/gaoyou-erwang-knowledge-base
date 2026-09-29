# case2query2retrieve benchmark

## 人工标注库关键词检索 benchmark

人工标注库使用另一条接口 /api/annotation。这条 benchmark 不评价相关性排序，也不把 AI 排序混进来；每个 query 只检查返回的案例 ID 集合是否与 gold 完全一致：

    关键词 -> 案例 ID 集合

指标包括：

- exact set accuracy：返回集合是否不多不少；
- missing / extra / duplicate：分别记录漏召回、多召回和重复；
- micro precision / recall：跨 query 汇总；
- roundtrip time：客户端从发起 API 请求到收到 JSON 的时间；
- server time：API 内部处理时间，由 X-API-Time-Ms 响应头提供。

Manifest 位于 v2/benchmarks/annotation-search.v1.json，包含精确案例、方法、字词、证据出处、简繁转换、待补内容和元数据排除控制样例。

本地或 Railway 运行：

    python v2/scripts/run_annotation_search_benchmark.py --base-url http://localhost:3311 --output tmp/annotation-search-local.json
    python v2/scripts/run_annotation_search_benchmark.py --base-url https://gaoyou-demo.up.railway.app --output tmp/annotation-search-railway.json

默认每条 query 先 warm-up 1 次，再测 5 次；结果顺序不计分，页面接口固定按案例 id 升序返回。

This benchmark evaluates the retrieval layer only:

```text
case -> query -> canonical passage candidates -> rank
```

The v1 primary set contains 20 existing V2 cases, balanced across the four canonical works. The gold passage is the reviewed `source_passage_id` already attached to the case. Hard negatives are explicitly listed for repeated titles and long passages. Diagnostic controls cover simplified/traditional input, markup removal, no-match abstention, and cases whose fields contain only an internal candidate ID.

The primary ranker is deterministic lexical retrieval: normalized substring matching, simplified/traditional variants, title weighting, and a match-window excerpt. AI reranking is deliberately disabled in v1. If an AI reranker is added later, it must be reported as a separate ranker against the same manifest.

Start a separate local benchmark server against the full read-only V2 database:

```powershell
$env:PORT = 3311
$env:V2_DB_FILE = "D:\26大创\v2\data\real_runs\annotation_v2.db"
$env:V2_CORPUS_DB_FILE = "D:\26大创\v2\data\real_runs\annotation_v2.db"
npm start --prefix "D:\26大创\03-项目网站"
```

Then run the benchmark in another terminal:

```powershell
& $python v2/scripts/run_retrieval_benchmark.py --base-url http://localhost:3311 --output tmp/benchmark-local.json
```

Run the same manifest against Railway:

```powershell
& $python v2/scripts/run_retrieval_benchmark.py --base-url https://gaoyou-demo.up.railway.app --output tmp/benchmark-railway.json
```

`Recall@k` and `MRR` are calculated only over `primary_recall`. Controls are reported separately so unsupported case fields do not silently become recall failures.

网站实际使用同一个只读接口，不另造一套搜索逻辑：打开 V2 工作库，在“正文检索”中粘贴正文片段；页面请求 `/api/v2/retrieve?q=...&include_cases=1`，先展示排序后的 canonical 正文，再列出该段落已经关联的 V2 case。直接调用接口时也可以这样查看关联案例：

```text
GET /api/v2/retrieve?q=平原之隰，奚有於高&work_key=dushu_zazhi&include_cases=1
```

因此 benchmark 测的是页面背后的检索/排序层，而不是页面的视觉结果；页面中的第 1、2、3 条就是同一 ranker 的返回顺序。当前 v1 不含 AI rerank，后续若加入，必须在同一 manifest 上单独报告 base ranker 与 AI reranker 的差异。
