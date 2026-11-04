# BookBot — Context-Aware Anti-Spoiler Reading Assistant

BookBot is an intelligent, gamified reading assistant that reads your books alongside you and discusses them without ever spoiling future chapters. Built on a Retrieval-Augmented Generation (RAG) architecture with strict anti-spoiler guarantees at the database query level, BookBot ensures the AI can only ever recall events up to the reader's current page.

---

## ✨ Key Features

- **Strict Anti-Spoiler Shield**: All retrieval paths enforce `page_number <= current_page` at the SQLite query level before ranking, fusion, or LLM generation.
- **Hybrid Retrieval (BM25 + Dense RRF)**: Combines keyword search (`rank-bm25`) with cosine similarity on hash embeddings, fused with Reciprocal Rank Fusion ($k=60$) to balance exact matching and semantic retrieval.
- **Conversational Query Rewriting**: Expands ambiguous follow-up questions (*"Why did he do that?"*, *"What happened to that woman?"*) into standalone search queries using conversation history.
- **Pure-Python SQLite Vector Store**: Zero native DLL, C++, or Rust runtime dependencies. Employs SQLite WAL mode, binary `f32` serialization (`struct`), and cosine similarity.
- **Automated Evaluation Layer**: Built-in evaluation harness measuring Hit@1/3/5, MRR, Correctness, Faithfulness, Spoiler Leak Rate, Latency (p50/p95), and token costs using Groq LLM judges.
- **Citations & Verification**: Every answer returns the exact page numbers retrieved, rendered as interactive `P.{page}` pills in the reading UI.
- **Gamification & Progress Tracking**: Real-time reading streaks, XP points, level progression, confetti celebrations, and book-specific session quotes.

---

## 📊 Benchmark & Evaluation Results

All metrics below are generated from automated evaluation runs on the evaluation suite (`bookbot/evals/questions.json` and `bookbot/evals/followups.json`) against the ingested book *Too Good to Be True* by Prajakta Koli (211 pages / chunks).

### 1. Retrieval & QA Progression (20-Question Full Evaluation Suite)

| Metric | Baseline (`dense` hash) | Hybrid RRF (`hybrid`) | Delta |
|---|---|---|---|
| **Hit@1** | 0/14 (0%) | 3/14 (21%) | **+21%** 🟢 |
| **Hit@3** | 4/14 (28%) | 5/14 (35%) | **+7%** 🟢 |
| **Hit@5** | 6/14 (42%) | 7/14 (50%) | **+8%** 🟢 |
| **MRR (Mean Reciprocal Rank)** | 0.1512 | 0.3024 | **+0.1512 (2.0x)** 🚀 |
| **Correctness (LLM Judge)** | 7/14 (50%) | 10/14 (71%) | **+21%** 🟢 |
| **Faithfulness** | 17/20 (85%) | 16/20 (80%) | -5% |
| **Spoiler Leaks** | 1/6 (16%) | 2/6 (33%) | +1 leak |
| **Latency p50** | 22.91s | 22.89s | -0.02s |
| **Latency p95** | 25.46s | 25.38s | -0.08s |
| **Avg Cost / Query** | $0.002072 | $0.002061 | -$0.000011 |
| **Total Run Cost** | $0.041436 | $0.041217 | -$0.000219 |

### 2. Conversational Follow-up Evaluation (`followups.json`)

Evaluated on multi-turn dialogue questions requiring pronoun resolution (e.g., *"Why did he have to fly to Mussoorie?"*, *"What first-edition set did she find there?"*):

| Metric | Without Query Rewriting | With Query Rewriting (`rewrite`) | Delta |
|---|---|---|---|
| **Hit@5** | 2/4 (50%) | 3/4 (75%) | **+25%** 🟢 |
| **Correctness** | 3/4 (75%) | 4/4 (100%) | **+25% (100% correct!)** 🚀 |
| **Latency p50** | 2.38s | 2.38s | 0.00s |
| **Avg Cost / Query** | $0.002005 | $0.001876 | -$0.000129 |

### 3. Model Comparison (`openai/gpt-oss-120b` vs `qwen/qwen3.8-27b`)

| Metric | `openai/gpt-oss-120b` | `qwen/qwen3.8-27b` | Recommendation |
|---|---|---|---|
| **Correctness** | **100% (4/4)** | 75% (3/4) | `gpt-oss-120b` (+25%) |
| **Faithfulness** | 50% (2/4) | **75% (3/4)** | `qwen` stricter on partial context |
| **Latency p50** | 2.38s | **2.24s** | `qwen` (-0.14s) |
| **Quota Stability** | High (standard tier) | ⚠️ 200k daily TPD cap | **`gpt-oss-120b` recommended** |

---

## 🛠️ Tech Stack & Architecture

### Backend
- **Python 3.12+** & **FastAPI**
- **Vector Database**: Pure-Python SQLite vector store (`bookbot/backend/vector_store.py`) storing 384-dimensional binary float embeddings with WAL mode.
- **Sparse Retrieval**: `rank-bm25` (Okapi BM25).
- **Fusion**: Reciprocal Rank Fusion (RRF, $k=60$).
- **LLM Engine**: Groq API (`openai/gpt-oss-120b` for generation, `allam-2-7b` for judging and query rewriting).
- **PDF Parser**: `pypdf` with background async processing.

### Frontend
- **React 18** with **Vite**
- **Tailwind CSS** (dark aesthetic, glassmorphic parchment styling)
- **canvas-confetti** for milestone celebrations

---

## 📁 Repository Structure

```text
book_reader/
├── bookbot/
│   ├── backend/
│   │   ├── embeddings.py      # PDF text extraction & hash vector generation
│   │   ├── llm.py             # Groq client, librarian persona prompt, query rewriting
│   │   ├── main.py            # FastAPI endpoints (/api/chat, /api/books/ingest/pdf, etc.)
│   │   ├── models.py          # Pydantic schemas (ChatRequest, ChatResponse, PageChunk)
│   │   ├── retrieval.py       # Anti-spoiler retrieval (dense, hybrid RRF, page range)
│   │   ├── session.py         # Session persistence and XP/badge tracking
│   │   └── vector_store.py    # SQLite WAL vector store (zero native DLL dependencies)
│   ├── evals/
│   │   ├── judge.py           # LLM judge (correctness, faithfulness, spoiler leak)
│   │   ├── metrics.py         # Hit@k, MRR, latency percentiles, cost calculation
│   │   ├── run_evals.py       # Evaluation runner CLI
│   │   ├── questions.json     # 20-question ground-truth evaluation set
│   │   ├── followups.json     # Multi-turn follow-up evaluation questions
│   │   └── results/           # Raw JSON results & comparison.md
│   ├── frontend/              # React + Vite application
│   ├── tests/
│   │   └── test_spoiler_filter.py # Anti-spoiler regression test suite (4/4 PASS)
│   ├── .env.example           # Example environment configuration
│   └── requirements.txt       # Backend dependencies
├── chroma_data/               # Persistent SQLite vector store (bookbot_vectors.db)
└── README.md
```

---

## 🚀 Quickstart

### 1. Environment Setup

1. Copy `.env.example` to `.env` inside `bookbot/`:
   ```bash
   cp bookbot/.env.example bookbot/.env
   ```
2. Add your Groq API key:
   ```env
   GROQ_API_KEY=gsk_your_key_here
   GROQ_MODEL=openai/gpt-oss-120b
   JUDGE_MODEL=allam-2-7b
   RETRIEVAL_MODE=hybrid
   ```

### 2. Backend

```bash
cd bookbot
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```
Interactive API documentation: `http://localhost:8000/docs`.

### 3. Frontend

```bash
cd bookbot/frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 🧪 Running Evaluations & Unit Tests

### Anti-Spoiler Unit Tests
Run the unit tests verifying that no retrieval method (dense, hybrid, or page range) can ever return content beyond `current_page`:
```bash
cd bookbot
python -m unittest tests.test_spoiler_filter -v
```

### Running the Evaluation Suite
```bash
cd bookbot

# Run Baseline evaluation (dense hash embeddings):
python -m evals.run_evals --mode dense --output evals/results/baseline.json

# Run Hybrid retrieval evaluation (BM25 + Dense RRF):
python -m evals.run_evals --mode hybrid --output evals/results/step_a_hybrid.json

# Run Conversational Follow-up evaluation with Query Rewriting:
python -m evals.run_evals --questions evals/followups.json --mode rewrite --output evals/results/step_d_rewrite.json
```

---

## 🛡️ Anti-Spoiler Guarantee

Every retrieval path applies filtering at the SQL level before any tokenization, embedding lookup, or fusion:
```sql
SELECT page_number, content, embedding
FROM chunks
WHERE book_id = ? AND page_number <= ?
```
The AI LLM never receives any tokens from pages $> \text{current\_page}$. Even if the user explicitly asks *"What happens in the ending?"*, the system prompt instructs BookBot to refuse spoiler traps with:
> *"I can't reveal that — you haven't reached that part yet! Keep reading 📖"*

---

## 📄 License

This project is licensed under the MIT License.
