"""
BookBot — Anti-spoiler retrieval module.

Queries the SQLite vector store with STRICT page_number filtering to prevent
spoilers. Every retrieval path enforces page_number <= current_page BEFORE
any ranking or LLM interaction.
"""

from typing import Any, Dict, List, Optional

from .embeddings import embed_query
from .vector_store import (
    count_chunks,
    get_all_read_chunks,
    get_page_content,
    get_page_range,
    query_similar,
)


def retrieve_context(
    query: str,
    book_id: str,
    current_page: int,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Retrieve relevant book chunks for a query, filtered to only include
    pages the user has already read (page_number <= current_page).

    HARD FILTER: Never retrieves chunks from pages > current_page.
    The spoiler filter is applied inside query_similar() at the SQL level,
    before any scoring or ranking.

    Args:
        query:        Natural-language question from the user.
        book_id:      Book identifier.
        current_page: Highest page the user has read (inclusive upper bound).
        top_k:        Number of chunks to return after ranking.

    Returns:
        {
            "documents":    List[str],
            "page_numbers": List[int],
            "distances":    List[float],  # 1 - cosine_similarity
        }
    """
    try:
        total = count_chunks(book_id)
        if total == 0:
            return {"documents": [], "page_numbers": [], "distances": []}

        query_embedding = embed_query(query)
        return query_similar(
            book_id=book_id,
            query_embedding=query_embedding,
            current_page=current_page,
            top_k=top_k,
        )
    except Exception as exc:
        print(f"[BookBot] Context retrieval error: {exc}")
        return {"documents": [], "page_numbers": [], "distances": []}


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
        end_page:   Last page of the range (inclusive).
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
