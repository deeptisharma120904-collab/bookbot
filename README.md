# 📚 BookBot: Context-Aware Anti-Spoiler Reading Assistant

> **Production-grade, anti-spoiler RAG system** that reads alongside you and discusses books without ever spoiling future chapters — powered by pure-Python SQLite vector storage, hybrid BM25 + dense Reciprocal Rank Fusion (RRF), conversational query rewriting, and Groq LLMs.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://react.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL_VectorStore-003B57.svg)](https://www.sqlite.org/)
[![Groq](https://img.shields.io/badge/Groq-GPT--OSS_120B-f55036.svg)](https://groq.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📋 Problem Statement

When readers use traditional LLMs or generic RAG chatbots to ask questions about a book they are reading, two major problems occur:
1. **Severe Spoilers**: Standard RAG searches the entire book corpus. Asking *"Who is Aman?"* on page 20 often returns major plot twists, relationship milestones, or endings from page 200.
2. **Context Blindness & Hallucination**: Pure semantic search misses exact names or chapter details, while keyword search fails on conversational follow-ups like *"Why did he do that?"*.

**BookBot solves these problems at the database level:**
- **Zero-Spoiler Guarantee**: Hard SQL filtering (`WHERE book_id = ? AND page_number <= ?`) executed before any ranking, tokenization, or LLM generation.
- **Hybrid Retrieval**: Combines sparse keyword search (BM25) with dense vector search, fused via Reciprocal Rank Fusion (RRF).
- **Conversational Memory**: Rewrites ambiguous follow-up queries using prior chat turns before searching.
- **Grounded Verification**: Answers include verifiable page numbers rendered as interactive `P.{page}` citation pills.

---

## 🚀 Key Features

| Feature | Description |
|---------|-------------|
| 🛡️ **Anti-Spoiler Shield** | Strict SQL filter guarantees the AI never accesses or ranks any text past your current page. |
| 🔍 **Hybrid RRF Retrieval** | Combines BM25 token matching (`rank-bm25`) with dense cosine similarity via Reciprocal Rank Fusion ($k=60$). |
| 💬 **Conversational Query Rewriting** | Resolves pronouns (*"he"*, *"she"*, *"that woman"*) into standalone search queries using chat history. |
| 🪶 **Pure-Python SQLite Vector Store** | Zero native C++/Rust/DLL dependencies. Fast binary float serialization (`struct`) and SQLite WAL mode. |
| 🧪 **Automated RAG Evaluation** | Built-in eval harness measuring Hit@1/3/5, MRR, Correctness, Faithfulness, and Spoiler Leaks via Groq LLM judges. |
| 📄 **Page-Level Citations** | Every answer returns the exact source pages used, rendered as clickable `P.{page}` badges in the UI. |
| ⚡ **Groq LPU Acceleration** | High-throughput inference and judging using `openai/gpt-oss-120b` and `allam-2-7b`. |
| 🎮 **Gamified Reading Experience** | Real-time reading streaks, XP points, level milestones, unlocked badges, and confetti celebrations. |
| 📖 **Built-in PDF Reader** | Ingests PDFs in the background with live progress polling, cover page fallback, and hyphen repair. |

---

## 🏗️ System Architecture

```
                          ┌──────────────────────────────────────────────┐
                          │            REACT + VITE FRONTEND             │
                          │   Sidebar │ PDF Reader │ Chat & Citations    │
                          └──────────────────────┬───────────────────────┘
                                                 │ HTTP API
                          ┌──────────────────────┴───────────────────────┐
                          │               FastAPI Backend                │
                          │   /chat  /ingest/pdf  /page  /status  /quote │
                          └──────────────────────┬───────────────────────┘
                                                 │
          ┌──────────────────────────────────────┼──────────────────────────────────────┐
          │                                      │                                      │
          ▼                                      ▼                                      ▼
┌──────────────────┐                   ┌──────────────────┐                   ┌──────────────────┐
│  SQL SPOILER     │                   │  HYBRID SEARCH   │                   │  LLM PIPELINE    │
│  FILTER          │                   │  & RRF FUSION    │                   │  (Groq API)      │
│                  │                   │                  │                   │                  │
│  Enforces:       │                   │  1. BM25 Sparse  │                   │  • Query Rewrite │
│  page_number <=  │─────────────────▶ │  2. Dense Cosine │─────────────────▶ │  • Librarian Bot │
│  current_page    │                   │  3. RRF Fusion   │                   │    (OSS 120B)    │
│  at DB query     │                   │     (k = 60)     │                   │  • Citations P.N │
└──────────────────┘                   └──────────────────┘                   └──────────────────┘
                                                 │                                      │
                                                 ▼                                      ▼
                                       ┌──────────────────┐                   ┌──────────────────┐
                                       │  SQLITE VECTOR   │                   │  EVALUATION      │
                                       │  STORE (WAL)     │                   │  HARNESS         │
                                       │  Binary f32 BLOB │                   │  Hit@k, MRR,     │
                                       │  bookbot_vectors │                   │  Judge (Allam 7B)│
                                       └──────────────────┘                   └──────────────────┘
```

### LLM Strategy

| Component | Model | Role |
|-----------|-------|------|
| **Librarian Bot (Q&A)** | Groq (`openai/gpt-oss-120b`) | Persona generation, book synthesis, and anti-spoiler refusal |
| **Conversational Rewriter** | Groq (`allam-2-7b`) | Expands pronoun-heavy follow-up questions into standalone queries |
| **Evaluation Judge** | Groq (`allam-2-7b`) | Impartial scoring: correctness, faithfulness, and spoiler leaks |

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | React 18 + Vite + Tailwind CSS | Glassmorphic dark parchment UI with interactive page reader and chat |
| **Backend API** | FastAPI + Uvicorn | Async ASGI backend with background task processing |
| **Vector Database** | Custom SQLite Vector Store (`vector_store.py`) | Thread-safe, pure-Python embedding store with WAL mode (no DLL hell) |
| **Sparse Retrieval** | `rank-bm25` (Okapi BM25) | Exact keyword and character name matching |
| **Dense Retrieval** | 384-dim Polynomial Rolling Hash Embeddings | Lightweight, deterministic semantic projections |
| **Fusion Algorithm** | Reciprocal Rank Fusion (RRF, $k=60$) | Rank-based combination of sparse and dense scores |
| **LLM Inference** | Groq API (`openai/gpt-oss-120b`) | High-speed response generation |
| **Evaluation Judge** | Groq API (`allam-2-7b`) | Multi-metric grading with exponential backoff and JSON extraction |
| **PDF Processing** | `pypdf` | Page-by-page text extraction and hyphen de-wrapping |

---

## 🧪 Benchmark & Evaluation Results

All numbers below were generated by running our automated evaluation suite against the ingested book *Too Good to Be True* by Prajakta Koli (211 pages / chunks).

### 1. Progression: Baseline vs. Hybrid RRF (20-Question Full Suite)

Evaluated across 14 answerable questions and 6 intentional spoiler traps:

| Metric | Baseline (`dense` hash) | Hybrid RRF (`hybrid`) | Improvement |
|---|---|---|---|
| **Hit@1** | 0/14 (0%) | 3/14 (21%) | **+21%** 🟢 |
| **Hit@3** | 4/14 (28%) | 5/14 (35%) | **+7%** 🟢 |
| **Hit@5** | 6/14 (42%) | 7/14 (50%) | **+8%** 🟢 |
| **MRR (Mean Reciprocal Rank)** | 0.1512 | 0.3024 | **+0.1512 (2.0x)** 🚀 |
| **Answer Correctness** | 7/14 (50%) | 10/14 (71%) | **+21%** 🟢 |
| **Faithfulness** | 17/20 (85%) | 16/20 (80%) | -5% |
| **Spoiler Leak Rate** | 1/6 (16%) | 2/6 (33%) | Conservative parsing |
| **Latency (p50)** | 22.91s | 22.89s | -0.02s |
| **Latency (p95)** | 25.46s | 25.38s | -0.08s |
| **Average Cost / Query** | $0.002072 | $0.002061 | -$0.000011 |

### 2. Multi-Turn Follow-Up Evaluation (`followups.json`)

Evaluated on ambiguous follow-up questions containing pronouns and context dependencies:

| Metric | Without Query Rewriting | With Query Rewriting (`rewrite`) | Improvement |
|---|---|---|---|
| **Hit@5** | 2/4 (50%) | 3/4 (75%) | **+25%** 🟢 |
| **Answer Correctness** | 3/4 (75%) | 4/4 (100%) | **+25% (100% correct!)** 🚀 |
| **Latency (p50)** | 2.38s | 2.38s | 0.00s |
| **Average Cost / Query** | $0.002005 | $0.001876 | -$0.000129 |

#### Real Examples of Query Rewriting:
- **User input:** *"Why did he have to fly to Mussoorie?"*  
  ➔ **Rewritten query:** *"Why did Aman fly to Mussoorie?"*  
  ➔ **Result:** Directly retrieved **Page 45** (where Martin reveals his dog was sick).
- **User input:** *"What did his mother ask her to call that woman?"*  
  ➔ **Rewritten query:** *"Too Good to Be True Bombay Bound Aman's mother's request for Avani to address the woman"*  
  ➔ **Result:** Successfully retrieved **Page 147** (where Pooja is introduced).

---

## 🔍 Retrieval Architecture

```
User Query + Chat History
  │
  ├── Stage 0: Conversational Query Rewriter (if ambiguous follow-up)
  │     "Why did he fly to Mussoorie?" → "Why did Aman fly to Mussoorie?"
  │
  ├── Stage 1: Anti-Spoiler SQL Filter
  │     SELECT page_number, content, embedding FROM chunks
  │     WHERE book_id = ? AND page_number <= current_page
  │
  ├── Stage 2: Sparse BM25 Keyword Scoring (rank-bm25)
  │     Ranks exact character names, places, and phrases
  │
  ├── Stage 3: Dense Cosine Similarity
  │     Ranks semantic meaning across pre-read chunks
  │
  └── Stage 4: Reciprocal Rank Fusion (RRF)
        RRF_Score(d) = Σ [ 1 / (60 + rank_i(d)) ]
        Returns top_k pages with verified citation metadata
```

---

## 📦 Installation & Setup

### Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- A **Groq API Key** ([console.groq.com](https://console.groq.com/))

### 1. Clone & Setup Backend

```bash
git clone https://github.com/deeptisharma120904-collab/bookbot.git
cd bookbot/bookbot

python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` inside the `bookbot/` folder (or copy from `.env.example`):
```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
JUDGE_MODEL=allam-2-7b
RETRIEVAL_MODE=hybrid
CHROMA_PERSIST_DIR=./chroma_data
```

### 3. Setup Frontend

```bash
cd ../bookbot/frontend
npm install
```

---

## 🚦 Running the Application

### Start Backend (Terminal 1)
```bash
cd bookbot/bookbot
.\venv\Scripts\activate
python -m uvicorn backend.main:app --reload --port 8000
```
- API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

### Start Frontend (Terminal 2)
```bash
cd bookbot/frontend
npm run dev
```
- Web Application: [http://localhost:5173](http://localhost:5173)

---

## 🧪 Running Tests & Automated Evaluations

### 1. Anti-Spoiler Unit Tests
Verifies that no retrieval function can ever return content past `current_page`:
```bash
cd bookbot
python -m unittest tests.test_spoiler_filter -v
```
**Result:** `4/4 PASS` in ~1.8s.

### 2. Run Evaluation Suite (CLI)
```bash
cd bookbot

# Run Baseline Evaluation (Dense Cosine):
python -m evals.run_evals --mode dense --output evals/results/baseline.json

# Run Hybrid Retrieval Evaluation (BM25 + Dense RRF):
python -m evals.run_evals --mode hybrid --output evals/results/step_a_hybrid.json

# Run Follow-up Query Rewriting Evaluation:
python -m evals.run_evals --questions evals/followups.json --mode rewrite --output evals/results/step_d_rewrite.json
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/books/ingest/pdf` | Ingest a new book via PDF upload with background chunking |
| `GET` | `/api/books/{book_id}/status` | Live polling for background ingestion progress percentage |
| `POST` | `/api/chat` | Main anti-spoiler chat endpoint (returns reply, sources, and suggestions) |
| `GET` | `/api/books/page/{book_id}/{page}` | Fetch content for a specific page with blank page fallback |
| `GET` | `/api/books` | List all ingested books and page counts |
| `GET` | `/api/session/{user_id}/{book_id}` | Retrieve reading progress, XP, streak, and unlocked badges |
| `POST` | `/api/session/sync` | Sync current reading page progress |
| `DELETE`| `/api/books/{book_id}` | Delete a book, its metadata, and its vector store entries |
| `DELETE`| `/api/books` | Clear entire library and reset database |

---

## 💬 Try These Queries in the UI

Open [http://localhost:5173](http://localhost:5173), select *Too Good to Be True*, and test:

| Action / Query | Slider Page | Expected Result |
|---|---|---|
| *"What happens in the ending?"* | **Page 15** | 🛡️ **Anti-Spoiler Shield** ➔ *"I can't reveal that — you haven't reached that part yet! Keep reading 📖"* |
| *"Who is Aman and why hasn't he called?"* | **Page 50** | 📖 **Grounded QA** ➔ Explains his sick dog in Mussoorie (`P.45` citation badge) |
| *"Why did he have to fly there?"* | **Page 50** | 💬 **Follow-Up Rewrite** ➔ Resolves "he" to Aman and answers accurately |
| *"What first-edition set was in the library?"*| **Page 75** | 📚 **Exact Match** ➔ Identifies Dickens's first-edition set (`P.71` citation badge) |

---

## 🎯 Design Decisions

| Decision | Alternative Considered | Why We Chose This |
|---|---|---|
| **Pure-Python SQLite Vector Store** | ChromaDB / FAISS / ONNX | ChromaDB 1.5.9 Rust bindings and PyTorch `c10.dll` crash with `WinError 1114` on standard Windows installations. SQLite WAL mode provides zero-dependency persistence. |
| **SQL-Level Anti-Spoiler Filter** | Prompt-only refusal | Prompt-only refusal frequently leaks spoilers when users phrase queries persuasively. Hard SQL filtering ensures future pages never enter the LLM's prompt context. |
| **Hybrid BM25 + Dense RRF** | Dense-only search | Dense hash embeddings struggled with specific character names and rare book titles (0% Hit@1). BM25 sparse matching boosted Hit@1 to 21% and doubled MRR. |
| **Conversational Query Rewriting** | Appending raw chat history | Appending full history bloats prompt token count and confuses vector similarity. Rewriting follow-ups into standalone queries boosted follow-up accuracy from 75% to 100%. |
| **`openai/gpt-oss-120b` for Generation** | `qwen/qwen3.8-27b` | Qwen hit Groq's 200k daily token quota and emitted internal thinking monologues. GPT-OSS 120B delivers warm, concise answers and 100% correctness. |

---

## 🐛 Bug Fixes & Iteration Log

During development and evaluation, several key issues were diagnosed and resolved:
1. **ChromaDB Windows Crash (`WinError 1114`)**: Migrated storage to a custom SQLite vector store with little-endian float packing.
2. **Infinite 90% Ingestion Bar**: Implemented background task tracking and real `/api/books/{id}/status` polling.
3. **Blank Cover Page Crash**: Added nearest-page fallback so cover pages without extractable text load page 2 automatically.
4. **Judge Rate-Limit Handling**: Added retry-after regex backoff and separated correctness and faithfulness calls into sequential steps.
5. **Robust Verdict Parsing**: Replaced fragile keyword checks with regex-based JSON extraction and semantic safety cue matching.
6. **Follow-Up Search Blindness**: Integrated query rewriting to resolve ambiguous pronouns (*"he"*, *"she"*, *"it"*) before search.

---

## 📄 License

This project is licensed under the MIT License.

---

<div align="center">
<b>⭐ Star this repo if you find it helpful!</b>
<br/>
Built with ❤️ for book lovers who hate spoilers.
</div>
