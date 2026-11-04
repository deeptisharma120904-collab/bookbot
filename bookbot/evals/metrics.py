"""
BookBot — Evaluation metrics.

Implements:
  - hit@k         : is source_page among the top-k retrieved pages?
  - mrr           : mean reciprocal rank of source_page in retrieved pages
  - spoiler_leak  : does answer contain forbidden_terms or reveal future content?
  - latency_stats : p50 and p95 from a list of latency values (seconds)
  - cost_estimate : token usage → USD cost given per-1M-token prices

All functions are pure (no I/O) so they are easy to unit-test.
"""

from __future__ import annotations

import math
from typing import Any


# ── Retrieval metrics ─────────────────────────────────────────────────────────

def hit_at_k(source_page: int, retrieved_pages: list[int], k: int) -> bool:
    """
    Return True if *source_page* appears in the first *k* retrieved pages.

    Args:
        source_page:     The ground-truth page that contains the answer.
        retrieved_pages: Ordered list of page numbers returned by retrieval
                         (best first).
        k:               Cut-off rank.
    """
    return source_page in retrieved_pages[:k]


def reciprocal_rank(source_page: int, retrieved_pages: list[int]) -> float:
    """
    Return the reciprocal rank of *source_page* in *retrieved_pages*.
    Returns 0.0 if the page is not found.
    """
    for rank, page in enumerate(retrieved_pages, start=1):
        if page == source_page:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(rr_values: list[float]) -> float:
    """Return the mean of a list of reciprocal-rank values."""
    if not rr_values:
        return 0.0
    return sum(rr_values) / len(rr_values)


# ── Spoiler detection ─────────────────────────────────────────────────────────

def contains_forbidden_terms(answer: str, forbidden_terms: list[str]) -> bool:
    """
    Return True if *answer* contains any of *forbidden_terms*
    (case-insensitive substring match).
    """
    lower = answer.lower()
    return any(term.lower() in lower for term in forbidden_terms if term)


def spoiler_leaked(
    answer: str,
    forbidden_terms: list[str],
    judge_verdict: bool | None = None,
) -> bool:
    """
    A spoiler leak is detected if EITHER:
      - The answer contains forbidden_terms (lexical check), OR
      - The LLM judge says the answer reveals future content (judge_verdict=True).

    Args:
        answer:          The BookBot answer text.
        forbidden_terms: Key words/names of the future reveal.
        judge_verdict:   True if the judge found a spoiler, False if not,
                         None if the judge was not run.
    """
    if contains_forbidden_terms(answer, forbidden_terms):
        return True
    if judge_verdict is True:
        return True
    return False


# ── Latency ───────────────────────────────────────────────────────────────────

def percentile(values: list[float], p: float) -> float:
    """
    Return the p-th percentile of *values* (0 ≤ p ≤ 100).
    Uses nearest-rank method.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, math.ceil(p / 100.0 * len(sorted_vals)) - 1)
    return sorted_vals[idx]


def latency_stats(latencies_s: list[float]) -> dict[str, float]:
    """
    Return p50 and p95 latency in seconds.

    Args:
        latencies_s: List of per-query wall-clock times in seconds.

    Returns:
        {"p50": float, "p95": float}
    """
    return {
        "p50": round(percentile(latencies_s, 50), 3),
        "p95": round(percentile(latencies_s, 95), 3),
    }


# ── Cost estimation ───────────────────────────────────────────────────────────

def cost_estimate(
    input_tokens: int,
    output_tokens: int,
    input_cost_per_1m: float,
    output_cost_per_1m: float,
) -> float:
    """
    Return estimated USD cost for one query.

    Args:
        input_tokens:        Number of prompt tokens.
        output_tokens:       Number of completion tokens.
        input_cost_per_1m:   Cost per 1 000 000 input tokens (USD).
        output_cost_per_1m:  Cost per 1 000 000 output tokens (USD).
    """
    return (
        input_tokens  / 1_000_000 * input_cost_per_1m
        + output_tokens / 1_000_000 * output_cost_per_1m
    )


# ── Aggregate helpers ─────────────────────────────────────────────────────────

def aggregate_results(per_question: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute aggregate metrics from a list of per-question result dicts.

    Each dict is expected to contain:
        type, hit_1, hit_3, hit_5, rr, correct, faithful,
        spoiler_leaked (spoiler_trap only), latency_s,
        input_tokens, output_tokens, cost_usd

    Returns a summary dict with counts and percentages.
    """
    answerable  = [q for q in per_question if q["type"] == "answerable"]
    spoiler     = [q for q in per_question if q["type"] == "spoiler_trap"]

    n_ans   = len(answerable)
    n_spo   = len(spoiler)
    n_total = len(per_question)

    def _pct(num: int, den: int) -> str:
        if den == 0:
            return "N/A"
        return f"{num}/{den} ({100*num//den}%)"

    # Retrieval (answerable only)
    h1 = sum(1 for q in answerable if q.get("hit_1"))
    h3 = sum(1 for q in answerable if q.get("hit_3"))
    h5 = sum(1 for q in answerable if q.get("hit_5"))
    rr_vals = [q.get("rr", 0.0) for q in answerable]

    # Correctness / faithfulness (answerable)
    correct    = sum(1 for q in answerable if q.get("correct"))
    faithful   = sum(1 for q in per_question if q.get("faithful"))

    # Spoiler leaks
    leaks = sum(1 for q in spoiler if q.get("spoiler_leaked"))

    # Latency / cost
    lats  = [q.get("latency_s", 0.0) for q in per_question]
    costs = [q.get("cost_usd",  0.0) for q in per_question]

    return {
        "n_total":          n_total,
        "n_answerable":     n_ans,
        "n_spoiler":        n_spo,
        # Retrieval
        "hit@1":            _pct(h1, n_ans),
        "hit@3":            _pct(h3, n_ans),
        "hit@5":            _pct(h5, n_ans),
        "mrr":              round(mean_reciprocal_rank(rr_vals), 4),
        # Answer quality
        "correctness":      _pct(correct, n_ans),
        "faithfulness":     _pct(faithful, n_total),
        # Spoiler safety
        "spoiler_leaks":    _pct(leaks, n_spo),
        # Latency / cost
        **latency_stats(lats),
        "avg_cost_usd":     round(sum(costs) / max(n_total, 1), 6),
        "total_cost_usd":   round(sum(costs), 6),
    }

