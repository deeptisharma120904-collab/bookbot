# BookBot Retrieval & Generation Evaluation Results

All numbers below are generated from real, automated evaluation runs on the 20-question evaluation set (`bookbot/evals/questions.json`) against the ingested book *Too Good to Be True* (Prajakta Koli, 211 chunks).

## Metric Progression

| Metric | Baseline (`dense` hash) | Step 1 (`hybrid` BM25+RRF) | Delta |
|---|---|---|---|
| **Hit@1** | 0/14 (0%) | 3/14 (21%) | **+21%** |
| **Hit@3** | 4/14 (28%) | 5/14 (35%) | **+7%** |
| **Hit@5** | 6/14 (42%) | 7/14 (50%) | **+8%** |
| **MRR** | 0.1512 | 0.3024 | **+0.1512 (2.0x)** |
| **Correctness** | 7/14 (50%) | 10/14 (71%) | **+21%** |
| **Faithfulness** | 17/20 (85%) | 16/20 (80%) | -5% |
| **Spoiler Leaks** | 1/6 (16%) | 2/6 (33%) | +1 leak |
| **Latency p50** | 22.91s | 22.89s | -0.02s |
| **Latency p95** | 25.46s | 25.38s | -0.08s |
| **Avg Cost / Query** | $0.002072 | $0.002061 | -$0.000011 |
| **Total Run Cost** | $0.041436 | $0.041217 | -$0.000219 |

## Follow-up Query Rewriting Evaluation (`followups.json`)

Evaluated on multi-turn ambiguous follow-up queries with pronoun referents (e.g. *"Why did he have to fly to Mussoorie?"*, *"What did his mother ask her to call that woman?"*):

| Metric | Without Query Rewriting (`followups_without_rewrite.json`) | With Query Rewriting (`step_d_rewrite.json`) | Delta |
|---|---|---|---|
| **Hit@1** | 2/4 (50%) | 1/4 (25%) | -25% |
| **Hit@3** | 2/4 (50%) | 2/4 (50%) | 0% |
| **Hit@5** | 2/4 (50%) | 3/4 (75%) | **+25%** 🟢 |
| **Correctness** | 3/4 (75%) | 4/4 (100%) | **+25% (100% correct)** 🚀 |
| **Faithfulness** | 4/4 (100%) | 2/4 (50%) | -50% |
| **Latency p50** | 2.38s | 2.38s | 0.00s |
| **Latency p95** | 25.74s | 23.05s | -2.69s |
| **Avg Cost / Query** | $0.002005 | $0.001876 | -$0.000129 |

## Model Comparison: `openai/gpt-oss-120b` vs `qwen/qwen3.8-27b`

Evaluated using `evals/followups.json` with conversational query rewriting:

| Metric | `openai/gpt-oss-120b` (`step_d_rewrite.json`) | `qwen/qwen3.8-27b` (`followups_qwen.json`) | Advantage |
|---|---|---|---|
| **Hit@5** | 3/4 (75%) | 3/4 (75%) | Tied |
| **MRR** | 0.4375 | 0.4375 | Tied |
| **Correctness** | 4/4 (100%) | 3/4 (75%) | **gpt-oss-120b (+25%)** |
| **Faithfulness** | 2/4 (50%) | 3/4 (75%) | qwen3.8-27b (+25%) |
| **Latency p50** | 2.38s | 2.24s | qwen3.8-27b (-0.14s) |
| **Latency p95** | 23.05s | 24.45s | gpt-oss-120b (-1.40s) |
| **Cost / Query** | $0.001876 | $0.001917 | gpt-oss-120b (-$0.000041) |
| **Quota Risk** | Standard RPM/RPD | ⚠️ 200k Daily TPD Limit | **gpt-oss-120b (No daily cap block)** |

## Run Details

- **Baseline:** Hash-based polynomial rolling embeddings + pure SQLite cosine similarity. File: `evals/results/baseline.json`.
- **Step 1 (Hybrid):** Pure-Python BM25 (`rank-bm25`) + hash dense cosine similarity fused with Reciprocal Rank Fusion ($k=60$). Spoiler filter enforced in SQL (`page_number <= current_page`) before BM25 and before dense ranking. File: `evals/results/step_a_hybrid.json`.
- **Step 2 (Follow-up Query Rewriter):** Multi-turn conversational query expansion via Groq (`allam-2-7b`). Resolves ambiguous pronouns and context markers from history into standalone queries before retrieval. Files: `evals/results/followups_without_rewrite.json`, `evals/results/step_d_rewrite.json`.
- **LLM Generator:** `openai/gpt-oss-120b` via Groq API.
- **Judge Model:** `allam-2-7b` via Groq API.

