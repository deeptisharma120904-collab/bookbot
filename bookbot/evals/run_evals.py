"""
BookBot — Evaluation runner.

Executes evaluation queries against BookBot's retrieval and generation pipeline,
collects metrics (retrieval hit@k, MRR, correctness, faithfulness, spoiler leak rate,
latency, token usage/cost), prints a summary table, outputs worst-failing questions,
and saves JSON results in evals/results/.

Usage::

    cd bookbot
    python -m evals.run_evals --questions evals/questions.json --output evals/results/baseline.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Paths setup
_EVALS_DIR = Path(__file__).resolve().parent
_BOOKBOT_DIR = _EVALS_DIR.parent
_PROJECT_DIR = _BOOKBOT_DIR.parent

sys.path.insert(0, str(_BOOKBOT_DIR))
load_dotenv(_BOOKBOT_DIR / ".env")

from backend.retrieval import retrieve_context
from backend.llm import build_system_prompt, get_groq_client
from backend.session import get_book_metadata
from evals.metrics import (
    hit_at_k,
    reciprocal_rank,
    spoiler_leaked,
    cost_estimate,
    aggregate_results,
)
from evals.judge import correctness_judge, faithfulness_judge, spoiler_judge


def _load_pricing() -> tuple[float, float]:
    """Load token pricing from pricing.json with env var override."""
    pricing_file = _EVALS_DIR / "pricing.json"
    in_cost = 0.59
    out_cost = 0.79
    if pricing_file.exists():
        try:
            data = json.loads(pricing_file.read_text(encoding="utf-8"))
            in_cost = float(data.get("input_cost_per_1m", in_cost))
            out_cost = float(data.get("output_cost_per_1m", out_cost))
        except Exception:
            pass

    # Environment variables take precedence if set
    in_cost = float(os.getenv("INPUT_TOKEN_COST_PER_1M", in_cost))
    out_cost = float(os.getenv("OUTPUT_TOKEN_COST_PER_1M", out_cost))
    return in_cost, out_cost


def _format_context(retrieved: dict[str, Any]) -> str:
    documents = retrieved.get("documents", [])
    page_numbers = retrieved.get("page_numbers", [])
    if not documents:
        return "No relevant context found in the pages you've read so far."
    formatted = []
    for p, doc in zip(page_numbers, documents):
        formatted.append(f"[Page {p}]\n{doc}")
    return "\n\n---\n\n".join(formatted)


def _parse_retry_after(err_str: str) -> float:
    """Extract retry-after seconds from Groq error message."""
    m_min = re.search(r"try again in (\d+)m([\d\.]+)s", err_str)
    if m_min:
        return float(m_min.group(1)) * 60 + float(m_min.group(2)) + 2.0
    m_sec = re.search(r"try again in ([\d\.]+)s", err_str)
    if m_sec:
        return float(m_sec.group(1)) + 2.0
    return 25.0


def _call_llm_with_usage(system_prompt: str, user_prompt: str) -> tuple[str, int, int]:
    """Call Groq LLM with rate limit backoff and return (response_text, input_tokens, output_tokens)."""
    client = get_groq_client()
    model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

    for attempt in range(1, 11):
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=model,
                temperature=0.3,
                max_tokens=512,
                timeout=30.0,
            )
            answer = chat_completion.choices[0].message.content or ""
            usage = chat_completion.usage
            in_tok = usage.prompt_tokens if usage else (len(system_prompt) + len(user_prompt)) // 4
            out_tok = usage.completion_tokens if usage else len(answer) // 4
            return answer.strip(), in_tok, out_tok
        except Exception as exc:
            err_msg = str(exc).lower()
            if "rate limit" in err_msg or "429" in err_msg:
                wait_sec = _parse_retry_after(str(exc))
                print(f"\n    [LLM Rate Limit] Waiting {wait_sec:.1f}s (attempt {attempt}/10)...", flush=True)
                time.sleep(wait_sec)
            elif "timeout" in err_msg:
                print(f"\n    [LLM Timeout] Attempt {attempt}/10, retrying in 5s...", flush=True)
                time.sleep(5.0)
            elif attempt < 10:
                time.sleep(2.0 * attempt)
            else:
                raise RuntimeError(f"Groq LLM call failed: {exc}") from exc
    return "", 0, 0


async def evaluate_question(
    q: dict[str, Any],
    book_id: str,
    book_title: str,
    book_author: str,
    top_k: int,
    input_cost_per_1m: float,
    output_cost_per_1m: float,
) -> dict[str, Any]:
    qid = q["id"]
    qtype = q["type"]
    question_text = q["question"]
    current_page = q["current_page"]
    source_page = q["source_page"]
    expected_answer = q.get("expected_answer", "")
    forbidden_terms = q.get("forbidden_terms", [])

    # 1. Retrieval
    t0 = time.perf_counter()
    retrieved = retrieve_context(
        query=question_text,
        book_id=book_id,
        current_page=current_page,
        top_k=top_k,
    )
    retrieved_pages = retrieved.get("page_numbers", [])
    context_text = _format_context(retrieved)

    # 2. LLM Generation
    system_prompt = build_system_prompt(
        book_title=book_title,
        author=book_author,
        current_page=current_page,
        retrieved_context=context_text,
    )
    user_prompt = f"Latest user request:\n{question_text}"

    # Call LLM in worker thread
    answer_text, in_tok, out_tok = await asyncio.to_thread(
        _call_llm_with_usage, system_prompt, user_prompt
    )
    latency_s = time.perf_counter() - t0

    cost_usd = cost_estimate(in_tok, out_tok, input_cost_per_1m, output_cost_per_1m)

    res: dict[str, Any] = {
        "id": qid,
        "type": qtype,
        "question": question_text,
        "current_page": current_page,
        "source_page": source_page,
        "expected_answer": expected_answer,
        "system_answer": answer_text,
        "retrieved_pages": retrieved_pages,
        "latency_s": round(latency_s, 3),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": round(cost_usd, 6),
    }

    # 3. Evaluation & Judges
    if qtype == "answerable":
        res["hit_1"] = hit_at_k(source_page, retrieved_pages, 1)
        res["hit_3"] = hit_at_k(source_page, retrieved_pages, 3)
        res["hit_5"] = hit_at_k(source_page, retrieved_pages, 5)
        res["rr"] = reciprocal_rank(source_page, retrieved_pages)

        # Correctness Judge
        c_judge = await asyncio.to_thread(
            correctness_judge, question_text, expected_answer, answer_text
        )
        res["correct"] = c_judge.passed
        res["correct_reason"] = c_judge.reason

        await asyncio.sleep(0.5)

        # Faithfulness Judge
        f_judge = await asyncio.to_thread(
            faithfulness_judge, context_text, answer_text
        )
        res["faithful"] = f_judge.passed
        res["faithful_reason"] = f_judge.reason

    elif qtype == "spoiler_trap":
        res["hit_1"] = None
        res["hit_3"] = None
        res["hit_5"] = None
        res["rr"] = None

        # Spoiler Judge
        s_judge = await asyncio.to_thread(
            spoiler_judge, question_text, answer_text, current_page, source_page
        )
        # s_judge.passed == True means safe (no spoiler)
        judge_spoiler_found = not s_judge.passed
        leaked = spoiler_leaked(answer_text, forbidden_terms, judge_spoiler_found)
        res["spoiler_leaked"] = leaked
        res["spoiler_reason"] = s_judge.reason
        res["faithful"] = True  # refusal is faithful to anti-spoiler prompt

    return res


def print_markdown_table(summary: dict[str, Any]) -> None:
    print("\n### Evaluation Summary Table\n")
    print("| Metric | Value | Detail / Raw Count |")
    print("|---|---|---|")
    print(f"| Total Questions | {summary.get('n_total')} | 14 answerable + 6 spoiler traps |")
    print(f"| **Hit@1** | {summary.get('hit@1')} | Top-1 contains source_page |")
    print(f"| **Hit@3** | {summary.get('hit@3')} | Top-3 contains source_page |")
    print(f"| **Hit@5** | {summary.get('hit@5')} | Top-5 contains source_page |")
    print(f"| **MRR** | {summary.get('mrr')} | Mean Reciprocal Rank (answerable) |")
    print(f"| **Correctness** | {summary.get('correctness')} | Answer matches expected (LLM judge) |")
    print(f"| **Faithfulness** | {summary.get('faithfulness')} | Claims supported by context |")
    print(f"| **Spoiler Leaks** | {summary.get('spoiler_leaks')} | Forbidden terms or future reveals leaked |")
    print(f"| **Latency p50** | {summary.get('p50')}s | Median wall-clock time |")
    print(f"| **Latency p95** | {summary.get('p95')}s | 95th percentile latency |")
    print(f"| **Avg Cost / Query** | ${summary.get('avg_cost_usd'):.6f} | Based on token pricing |")
    print(f"| **Total Run Cost** | ${summary.get('total_cost_usd'):.6f} | All 20 queries combined |")


def print_worst_failures(per_question: list[dict[str, Any]]) -> None:
    """Identify and print the 3 worst-failing questions."""
    # Score severity of failure:
    # - spoiler leaked: severity 10
    # - answerable not correct: severity 5
    # - not hit@5: severity 3
    # - not faithful: severity 4
    failures = []
    for q in per_question:
        severity = 0
        reasons = []
        if q["type"] == "spoiler_trap" and q.get("spoiler_leaked"):
            severity += 10
            reasons.append(f"SPOILER LEAK: {q.get('spoiler_reason')}")
        if q["type"] == "answerable":
            if not q.get("correct"):
                severity += 5
                reasons.append(f"INCORRECT: {q.get('correct_reason')}")
            if not q.get("hit_5"):
                severity += 3
                reasons.append(f"RETRIEVAL MISS: source page {q.get('source_page')} not in retrieved {q.get('retrieved_pages')}")
            if not q.get("faithful"):
                severity += 4
                reasons.append(f"UNFAITHFUL: {q.get('faithful_reason')}")

        if severity > 0:
            failures.append((severity, q, reasons))

    failures.sort(key=lambda x: x[0], reverse=True)

    print("\n### 3 Worst-Failing Questions\n")
    if not failures:
        print("No failures detected! All questions passed.")
        return

    for idx, (sev, q, reasons) in enumerate(failures[:3], start=1):
        ans = str(q.get('system_answer', '')).encode('ascii', 'replace').decode('ascii')
        exp = str(q.get('expected_answer', '')).encode('ascii', 'replace').decode('ascii')
        print(f"**{idx}. [{q['id']}] ({q['type']}) - Severity Score: {sev}**")
        print(f"- **Question:** {q['question']}")
        print(f"- **Current Page:** {q['current_page']} | **Source Page:** {q['source_page']}")
        print(f"- **Retrieved Pages:** {q['retrieved_pages']}")
        print(f"- **Expected Answer:** {exp}")
        print(f"- **System Answer:** {ans}")
        for r in reasons:
            clean_r = str(r).encode('ascii', 'replace').decode('ascii')
            print(f"- [FAIL] **Failure Reason:** {clean_r}")
        print()


async def run_all(
    questions_file: Path,
    output_file: Path,
    book_id: str,
    top_k: int = 5,
    mode: str = "dense",
) -> None:
    if not questions_file.exists():
        print(f"ERROR: Questions file '{questions_file}' not found.")
        sys.exit(1)

    with open(questions_file, "r", encoding="utf-8") as f:
        questions = json.load(f)

    if not questions:
        print(f"ERROR: Questions file '{questions_file}' is empty.")
        sys.exit(1)

    in_cost, out_cost = _load_pricing()

    meta = get_book_metadata(book_id)
    title = meta.title if meta else "Too Good to Be True"
    author = meta.author if meta else "Prajakta Koli"

    print("=" * 60)
    print(f"BookBot Evaluation Run  (mode={mode})")
    print("=" * 60)
    print(f"Book ID   : {book_id} ('{title}' by {author})")
    print(f"Questions : {len(questions)} ({questions_file})")
    print(f"Pricing   : ${in_cost:.2f}/1M input, ${out_cost:.2f}/1M output")
    print(f"Judge     : {os.getenv('JUDGE_MODEL') or os.getenv('GROQ_MODEL') or 'qwen/qwen3.8-27b'}")
    print(f"Mode      : {mode}")
    print()

    # Propagate mode to env so retrieve_context picks it up via RETRIEVAL_MODE
    os.environ["RETRIEVAL_MODE"] = mode

    results = []
    for idx, q in enumerate(questions, start=1):
        print(f"[{idx:02d}/{len(questions):02d}] Evaluating {q['id']} ({q['type']})...", end=" ", flush=True)
        r = await evaluate_question(
            q=q,
            book_id=book_id,
            book_title=title,
            book_author=author,
            top_k=top_k,
            input_cost_per_1m=in_cost,
            output_cost_per_1m=out_cost,
        )
        results.append(r)

        status_snip = "PASS"
        if q["type"] == "answerable" and not r.get("correct"):
            status_snip = "FAIL_CORRECT"
        elif q["type"] == "spoiler_trap" and r.get("spoiler_leaked"):
            status_snip = "LEAKED"
        print(f"Done ({status_snip}, lat={r['latency_s']}s)", flush=True)

        # Save progress incrementally so partial results are never lost
        try:
            partial_data = {
                "book_id": book_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "mode": mode,
                "completed": len(results),
                "total": len(questions),
                "per_question": results,
            }
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(json.dumps(partial_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        # Brief rate limiting between questions to prevent Groq rate limits
        await asyncio.sleep(1.0)

    summary = aggregate_results(results)

    output_data = {
        "book_id": book_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": mode,
        "pricing": {
            "input_cost_per_1m": in_cost,
            "output_cost_per_1m": out_cost,
        },
        "summary": summary,
        "per_question": results,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print_markdown_table(summary)
    print_worst_failures(results)
    print(f"\nSaved raw evaluation results to: {output_file}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="BookBot evaluation runner")
    parser.add_argument("--questions", default=str(_EVALS_DIR / "questions.json"))
    parser.add_argument(
        "--output",
        default=str(_EVALS_DIR / "results" / "baseline.json"),
        help="Path to write JSON results",
    )
    parser.add_argument("--book_id", default="too_good_to_be_true")
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument(
        "--mode",
        default=os.getenv("RETRIEVAL_MODE", "dense"),
        choices=["dense", "hybrid"],
        help="Retrieval mode: dense (baseline cosine) or hybrid (BM25+RRF)",
    )
    args = parser.parse_args()

    asyncio.run(run_all(
        Path(args.questions),
        Path(args.output),
        args.book_id,
        args.top_k,
        args.mode,
    ))


if __name__ == "__main__":
    main()
