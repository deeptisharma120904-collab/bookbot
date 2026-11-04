"""
BookBot — Pure-Python SQLite vector store.

Replaces ChromaDB entirely. Zero native DLL / Rust / ONNX dependencies.
Uses Python's built-in sqlite3 + struct for embedding storage and plain
cosine-similarity search (no numpy required, though numpy is used when
available for a ~5x speedup on the dot product).

Thread-safety: a single module-level lock serialises all writes;
reads use their own short-lived connections (SQLite WAL mode).
"""

from __future__ import annotations

import math
import os
import sqlite3
import struct
import threading
from typing import Any, Dict, List, Optional

# ── Optional numpy fast-path ─────────────────────────────────────────
try:
    import numpy as np  # type: ignore
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

# ── Module-level state ───────────────────────────────────────────────

_WRITE_LOCK: threading.Lock = threading.Lock()
_DB_PATH_CACHE: Optional[str] = None

# ── Path resolution ──────────────────────────────────────────────────

def _resolve_db_path() -> str:
    """Return the absolute path to our SQLite database, respecting .env."""
    global _DB_PATH_CACHE
    if _DB_PATH_CACHE:
        return _DB_PATH_CACHE

    this_dir = os.path.dirname(os.path.abspath(__file__))   # backend/
    bookbot_dir = os.path.dirname(this_dir)                 # bookbot/
    project_root = os.path.dirname(bookbot_dir)             # book_reader/

    chroma_dir = os.getenv("CHROMA_PERSIST_DIR", os.path.join(project_root, "chroma_data"))
    if not os.path.isabs(chroma_dir):
        chroma_dir = os.path.normpath(os.path.join(project_root, chroma_dir))

    _DB_PATH_CACHE = os.path.join(chroma_dir, "bookbot_vectors.db")
    return _DB_PATH_CACHE


def _connect(read_only: bool = False) -> sqlite3.Connection:
    """Open a connection; use WAL mode so readers don't block writers."""
    db_path = _resolve_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ── Schema bootstrap ─────────────────────────────────────────────────

def init_db() -> None:
    """Create tables and indices if they don't already exist."""
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id    TEXT    PRIMARY KEY,
                    book_id     TEXT    NOT NULL,
                    page_number INTEGER NOT NULL,
                    content     TEXT    NOT NULL,
                    embedding   BLOB    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_book
                    ON chunks (book_id);
                CREATE INDEX IF NOT EXISTS idx_chunks_book_page
                    ON chunks (book_id, page_number);
            """)
            conn.commit()
            print(f"[BookBot] Vector store ready at: {_resolve_db_path()}")
        finally:
            conn.close()


# ── Serialisation helpers ─────────────────────────────────────────────

def _pack(embedding: List[float]) -> bytes:
    """Pack a list of floats into a compact binary blob (little-endian f32)."""
    return struct.pack(f"<{len(embedding)}f", *embedding)


def _unpack(blob: bytes) -> List[float]:
    """Unpack a binary blob back into a list of floats."""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


# ── Similarity ────────────────────────────────────────────────────────

def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors, range [−1, 1]."""
    if _HAS_NUMPY:
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        norm_a = np.linalg.norm(va)
        norm_b = np.linalg.norm(vb)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(va, vb) / (norm_a * norm_b))

    # Pure-Python fallback
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a)) or 1.0
    nb   = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


# ── Write operations ──────────────────────────────────────────────────

def upsert_chunk(
    chunk_id:    str,
    book_id:     str,
    page_number: int,
    content:     str,
    embedding:   List[float],
) -> None:
    """Insert or replace a single chunk."""
    blob = _pack(embedding)
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO chunks "
                "(chunk_id, book_id, page_number, content, embedding) "
                "VALUES (?, ?, ?, ?, ?)",
                (chunk_id, book_id, page_number, content, blob),
            )
            conn.commit()
        finally:
            conn.close()


def upsert_chunks_batch(
    rows: List[tuple],  # (chunk_id, book_id, page_number, content, embedding_blob)
) -> None:
    """Bulk-insert many chunks in a single transaction (much faster)."""
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO chunks "
                "(chunk_id, book_id, page_number, content, embedding) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()


def delete_book(book_id: str) -> bool:
    """Delete all chunks for a given book."""
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM chunks WHERE book_id = ?", (book_id,))
            conn.commit()
            return True
        except Exception as exc:
            print(f"[BookBot] delete_book error: {exc}")
            return False
        finally:
            conn.close()


def delete_all_books() -> bool:
    """Wipe every chunk from the store."""
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM chunks")
            conn.commit()
            return True
        except Exception as exc:
            print(f"[BookBot] delete_all_books error: {exc}")
            return False
        finally:
            conn.close()


# ── Read operations ───────────────────────────────────────────────────

def count_chunks(book_id: str) -> int:
    """Return the number of stored chunks for a book."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM chunks WHERE book_id = ?", (book_id,)
        ).fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def query_similar(
    book_id:         str,
    query_embedding: List[float],
    current_page:    int,
    top_k:           int = 5,
) -> Dict[str, Any]:
    """
    Retrieve the top-k most similar chunks for a query, filtered to
    page_number <= current_page (anti-spoiler hard filter).

    Returns:
        {"documents": [...], "page_numbers": [...], "distances": [...]}
        where distance = 1 − cosine_similarity.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT page_number, content, embedding "
            "FROM chunks "
            "WHERE book_id = ? AND page_number <= ?",
            (book_id, current_page),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"documents": [], "page_numbers": [], "distances": []}

    scored: List[tuple] = []
    for row in rows:
        emb  = _unpack(bytes(row["embedding"]))
        sim  = _cosine(query_embedding, emb)
        scored.append((sim, row["page_number"], row["content"]))

    # Sort by similarity descending, take top-k
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    return {
        "documents":    [x[2] for x in top],
        "page_numbers": [x[1] for x in top],
        "distances":    [1.0 - x[0] for x in top],
    }


def get_page_content(book_id: str, page_number: int) -> Optional[str]:
    """Fetch the content of a specific page (exact match)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT content FROM chunks "
            "WHERE book_id = ? AND page_number = ? LIMIT 1",
            (book_id, page_number),
        ).fetchone()
        return row["content"] if row else None
    finally:
        conn.close()


def get_page_range(
    book_id:    str,
    start_page: int,
    end_page:   int,
    max_chunks: int = 20,
) -> Dict[str, Any]:
    """Return chunks in the given inclusive page range, ordered by page."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT page_number, content FROM chunks "
            "WHERE book_id = ? AND page_number >= ? AND page_number <= ? "
            "ORDER BY page_number "
            "LIMIT ?",
            (book_id, start_page, end_page, max_chunks),
        ).fetchall()
    finally:
        conn.close()

    return {
        "documents":    [r["content"]     for r in rows],
        "page_numbers": [r["page_number"] for r in rows],
    }


def get_all_read_chunks(book_id: str, current_page: int) -> Dict[str, Any]:
    """Return ALL chunks from page 1 up to current_page, ordered by page."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT page_number, content FROM chunks "
            "WHERE book_id = ? AND page_number <= ? "
            "ORDER BY page_number",
            (book_id, current_page),
        ).fetchall()
    finally:
        conn.close()

    return {
        "documents":    [r["content"]     for r in rows],
        "page_numbers": [r["page_number"] for r in rows],
    }


def list_book_ids() -> List[str]:
    """Return every distinct book_id currently in the store."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT book_id FROM chunks"
        ).fetchall()
        return [r["book_id"] for r in rows]
    finally:
        conn.close()

