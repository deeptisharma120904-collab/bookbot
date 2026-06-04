"""
BookBot — Anti-spoiler retrieval module.
Queries ChromaDB with STRICT page_number filtering to prevent spoilers.
"""

from typing import List, Dict, Any, Optional
from .embeddings import get_collection, embed_query


def retrieve_context(
    query: str,
    book_id: str,
    current_page: int,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Retrieve relevant book chunks for a query, filtered to only include
    pages the user has already read (page_number <= current_page).

    ⚠️ HARD FILTER: Never retrieves chunks from pages > current_page.

    Returns:
        {
            "documents": List[str],
            "page_numbers": List[int],
            "distances": List[float]
        }
    """
    collection = get_collection(book_id)

    # Embed the user's query
    query_embedding = embed_query(query)

    # Query ChromaDB with anti-spoiler filter
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={
            "$and": [
                {"book_id": {"$eq": book_id}},
                {"page_number": {"$lte": current_page}}
            ]
        },
        include=["documents", "metadatas", "distances"]
    )

    # Parse results
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    page_numbers = [m.get("page_number", 0) for m in metadatas]

    return {
        "documents": documents,
        "page_numbers": page_numbers,
        "distances": distances
    }


def get_page_chunk(book_id: str, page_number: int) -> Optional[str]:
    """
    Directly fetch the content of a specific page.
    Used for "What happened on page X?" queries.
    """
    collection = get_collection(book_id)

    # Direct ID lookup
    chunk_id = f"{book_id}_page_{page_number}"

    try:
        result = collection.get(
            ids=[chunk_id],
            include=["documents"]
        )
        if result and result["documents"]:
            return result["documents"][0]
    except Exception:
        pass

    # Fallback: query by exact page_number metadata
    try:
        results = collection.get(
            where={
                "$and": [
                    {"book_id": {"$eq": book_id}},
                    {"page_number": {"$eq": page_number}}
                ]
            },
            include=["documents"]
        )
        if results and results["documents"]:
            return results["documents"][0]
    except Exception:
        pass

    return None


def retrieve_page_range(
    book_id: str,
    start_page: int,
    end_page: int,
    max_chunks: int = 20
) -> Dict[str, Any]:
    """
    Retrieve all chunks within a page range.
    Used for summaries and "catch me up" requests.
    """
    collection = get_collection(book_id)

    results = collection.get(
        where={
            "$and": [
                {"book_id": {"$eq": book_id}},
                {"page_number": {"$gte": start_page}},
                {"page_number": {"$lte": end_page}}
            ]
        },
        include=["documents", "metadatas"],
        limit=max_chunks
    )

    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])
    page_numbers = [m.get("page_number", 0) for m in metadatas]

    # Sort by page number for chronological order
    paired = sorted(zip(page_numbers, documents), key=lambda x: x[0])
    if paired:
        page_numbers, documents = zip(*paired)
        page_numbers = list(page_numbers)
        documents = list(documents)

    return {
        "documents": documents,
        "page_numbers": page_numbers
    }

def retrieve_all_read_chunks(book_id: str, current_page: int) -> Dict[str, Any]:
    """
    Retrieve ALL chunks from page 1 up to the current_page.
    Used for the full summarization feature.
    """
    collection = get_collection(book_id)

    # The `get` method with no limit retrieves all matching items.
    results = collection.get(
        where={
            "$and": [
                {"book_id": {"$eq": book_id}},
                {"page_number": {"$lte": current_page}}
            ]
        },
        include=["documents", "metadatas"]
    )

    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])
    page_numbers = [m.get("page_number", 0) for m in metadatas]

    # Sort by page number for chronological order
    paired = sorted(zip(page_numbers, documents), key=lambda x: x[0])
    if paired:
        page_numbers, documents = zip(*paired)
        page_numbers = list(page_numbers)
        documents = list(documents)

    return {
        "documents": documents,
        "page_numbers": page_numbers
    }
