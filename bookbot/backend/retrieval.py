"""
BookBot — Anti-spoiler retrieval module.

Queries the SQLite vector store with STRICT page_number filtering to prevent
spoilers. Every retrieval path enforces page_number <= current_page BEFORE
any ranking or LLM interaction.

Retrieval modes (set via RETRIEVAL_MODE env var or per-request param):
  dense   — cosine similarity on hash embeddings (original baseline)
  hybrid  — Reciprocal Rank Fusion of BM25 (sparse) + dense (cosine)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from .embeddings import embed_query
from .vector_store import (
    count_chunks,
    get_all_read_chunks,
    get_page_content,
    get_page_range,
    query_similar,
    _connect,
    _unpack,
    _cosine,
)

# ── Retrieval mode ────────────────────────────────────────────────────────────

_DEFAULT_MODE = "dense"


def _get_mode(override: Optional[str] = None) -> str:
    """Return the active retrieval mode (request param > env var > default)."""
    if override:
        return override.lower()
    return os.getenv("RETRIEVAL_MODE", _DEFAULT_MODE).lower()


# ── BM25 helpers ──────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """Simple whitespace+punctuation tokenizer for BM25."""
    return re.findall(r"\w+", text.lower())


def _fetch_read_rows(book_id: str, current_page: int) -> List[tuple]:
    """
    Fetch (page_number, content, embedding_blob) for all chunks with
    page_number <= current_page.  Spoiler filter applied at the SQL level.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT page_number, content, embedding "
            "FROM chunks "
            "WHERE book_id = ? AND page_number <= ?",
            (book_id, current_page),
        ).fetchall()
        return [(r["page_number"], r["content"], bytes(r["embedding"])) for r in rows]
    finally:
        conn.close()


def _rrf_fusion(
    bm25_ranked: List[tuple],   # [(score, page_number, content), ...]
    dense_ranked: List[tuple],  # [(sim, page_number, content), ...]
    k: int = 60,
) -> List[tuple]:
    """
    Reciprocal Rank Fusion.

    RRF(d) = sum_r 1 / (k + rank_r(d))

    Args:
        bm25_ranked:  Items sorted by BM25 score descending.
        dense_ranked: Items sorted by cosine similarity descending.
        k:            RRF constant (default 60, standard from Cormack 2009).

    Returns:
        List of (rrf_score, page_number, content) sorted by rrf_score descending.
    """
    scores: Dict[int, float] = {}  # page_number -> rrf score
    page_content: Dict[int, str] = {}

    for rank, (_, pn, content) in enumerate(bm25_ranked, start=1):
        scores[pn] = scores.get(pn, 0.0) + 1.0 / (k + rank)
        page_content[pn] = content

    for rank, (_, pn, content) in enumerate(dense_ranked, start=1):
        scores[pn] = scores.get(pn, 0.0) + 1.0 / (k + rank)
        page_content[pn] = content

    merged = [(score, pn, page_content[pn]) for pn, score in scores.items()]
    merged.sort(key=lambda x: x[0], reverse=True)
    return merged


def retrieve_hybrid(
    query: str,
    book_id: str,
    current_page: int,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Hybrid BM25 + dense cosine retrieval fused with Reciprocal Rank Fusion.

    Steps:
      1. Fetch all chunks with page_number <= current_page (anti-spoiler SQL filter).
      2. Run BM25 on the filtered corpus.
      3. Run cosine similarity (dense) on the same filtered corpus.
      4. Fuse rankings via RRF.
      5. Return top_k results.

    Returns:
        {
            "documents":    List[str],
            "page_numbers": List[int],
            "distances":    List[float],  # 1 - rrf_score (normalised)
            "mode":         "hybrid",
        }
    """
    try:
        from rank_bm25 import BM25Okapi  # type: ignore
    except ImportError:
        # Graceful fallback if rank_bm25 not installed
        print("[BookBot] rank_bm25 not found — falling back to dense retrieval")
        result = retrieve_dense(query, book_id, current_page, top_k)
        result["mode"] = "hybrid_fallback"
        return result

    rows = _fetch_read_rows(book_id, current_page)
    if not rows:
        return {"documents": [], "page_numbers": [], "distances": [], "mode": "hybrid"}

    page_numbers = [r[0] for r in rows]
    contents     = [r[1] for r in rows]
    blobs        = [r[2] for r in rows]

    # ── BM25 ──────────────────────────────────────────────────────────
    tokenized_corpus = [_tokenize(c) for c in contents]
    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = _tokenize(query)
    bm25_scores = bm25.get_scores(query_tokens)
    bm25_ranked = sorted(
        [(bm25_scores[i], page_numbers[i], contents[i]) for i in range(len(rows))],
        key=lambda x: x[0],
        reverse=True,
    )

    # ── Dense ─────────────────────────────────────────────────────────
    query_emb = embed_query(query)
    dense_ranked = sorted(
        [(_cosine(query_emb, _unpack(b)), page_numbers[i], contents[i])
         for i, b in enumerate(blobs)],
        key=lambda x: x[0],
        reverse=True,
    )

    # ── RRF fusion ────────────────────────────────────────────────────
    merged = _rrf_fusion(bm25_ranked, dense_ranked)
    top = merged[:top_k]

    max_rrf = top[0][0] if top else 1.0
    return {
        "documents":    [x[2] for x in top],
        "page_numbers": [x[1] for x in top],
        "distances":    [1.0 - (x[0] / max_rrf) for x in top],  # normalised distance
        "mode":         "hybrid",
    }


# ── Dense (original) retrieval ────────────────────────────────────────────────

def retrieve_dense(
    query: str,
    book_id: str,
    current_page: int,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Original cosine-similarity retrieval against hash embeddings.

    Returns:
        {"documents": List[str], "page_numbers": List[int], "distances": List[float], "mode": "dense"}
    """
    query_embedding = embed_query(query)
    result = query_similar(
        book_id=book_id,
        query_embedding=query_embedding,
        current_page=current_page,
        top_k=top_k,
    )
    result["mode"] = "dense"
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve_context(
    query: str,
    book_id: str,
    current_page: int,
    top_k: int = 5,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve relevant book chunks for a query, filtered to only include
    pages the user has already read (page_number <= current_page).

    HARD FILTER: Never retrieves chunks from pages > current_page.
    The spoiler filter is applied at the SQL level, before any scoring.

    Args:
        query:        Natural-language question from the user.
        book_id:      Book identifier.
        current_page: Highest page the user has read (inclusive upper bound).
        top_k:        Number of chunks to return after ranking.
        mode:         Override RETRIEVAL_MODE env var ('dense' or 'hybrid').

    Returns:
        {
            "documents":    List[str],
            "page_numbers": List[int],
            "distances":    List[float],
            "mode":         str,
        }
    """
    try:
        total = count_chunks(book_id)
        if total == 0:
            return {"documents": [], "page_numbers": [], "distances": [], "mode": "none"}

        active_mode = _get_mode(mode)

        if active_mode == "hybrid":
            return retrieve_hybrid(query, book_id, current_page, top_k)
        else:
            return retrieve_dense(query, book_id, current_page, top_k)

    except Exception as exc:
        print(f"[BookBot] Context retrieval error: {exc}")
        return {"documents": [], "page_numbers": [], "distances": [], "mode": "error"}


def get_page_chunk(book_id: str, page_number: int) -> Optional[str]:
    """
    Directly fetch the content of a specific page.
    Used for 'What happened on page X?' queries.

    Args:
        book_id:     Book identifier.
        page_number: Exact page to fetch.

    Returns:
        Page text, or None if the page is not stored.
    """
    return get_page_content(book_id, page_number)


def retrieve_page_range(
    book_id: str,
    start_page: int,
    end_page: int,
    max_chunks: int = 20,
) -> Dict[str, Any]:
    """
    Retrieve all chunks within a page range (inclusive).
    Used for summaries and 'catch me up' requests.

    Args:
        book_id:    Book identifier.
        start_page: First page of the range (inclusive).
        end_page:   Last page of the range (inclusive)  .
        max_chunks: Hard cap on the number of chunks returned.

    Returns:
        {"documents": List[str], "page_numbers": List[int]}
    """
    try:
        return get_page_range(book_id, start_page, end_page, max_chunks)
    except Exception as exc:
        print(f"[BookBot] Range retrieval error: {exc}")
        return {"documents": [], "page_numbers": []}


def retrieve_all_read_chunks(
    book_id: str,
    current_page: int,
) -> Dict[str, Any]:
    """
    Retrieve ALL chunks from page 1 up to current_page (inclusive).
    Used for the full summarisation feature.

    Args:
        book_id:      Book identifier.
        current_page: Highest page the user has read (inclusive upper bound).

    Returns:
        {"documents": List[str], "page_numbers": List[int]}
    """
    try:
        return get_all_read_chunks(book_id, current_page)
    except Exception as exc:
        print(f"[BookBot] All read chunks retrieval error: {exc}")
        return {"documents": [], "page_numbers": []}
