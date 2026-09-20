# case2query2retrieve benchmark

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
