"""
BookBot — Embedding pipeline.
Handles book chunking (text & PDF), embedding generation, and ChromaDB storage.
"""

import os
import re
from io import BytesIO
from typing import List, Tuple

from sentence_transformers import SentenceTransformer
from pypdf import PdfReader
import chromadb

from .models import PageChunk

# ─── Globals (lazy-loaded singletons) ─────────────────────────────────

_embedding_model: SentenceTransformer = None
_chroma_client: chromadb.ClientAPI = None


def get_embedding_model() -> SentenceTransformer:
    """Load the sentence-transformers model (singleton)."""
    global _embedding_model
    if _embedding_model is None:
        model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        print(f"[BookBot] Loading embedding model: {model_name}")
        _embedding_model = SentenceTransformer(model_name)
        print(f"[BookBot] Embedding model loaded successfully.")
    return _embedding_model


def get_chroma_client() -> chromadb.ClientAPI:
    """Get or create the ChromaDB persistent client (singleton)."""
    global _chroma_client
    if _chroma_client is None:
        persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
        print(f"[BookBot] Initializing ChromaDB at: {persist_dir}")
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


def get_collection(book_id: str):
    """Get or create a ChromaDB collection for a specific book."""
    client = get_chroma_client()
    # Sanitize book_id for collection name (ChromaDB requirements)
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', book_id)
    if len(safe_name) < 3:
        safe_name = safe_name + "_book"
    return client.get_or_create_collection(
        name=safe_name,
        metadata={"hnsw:space": "cosine"}
    )


# ─── Chunking ─────────────────────────────────────────────────────────

def chunk_text(text: str) -> List[PageChunk]:
    """
    Split plain text into page-sized chunks.
    Supports explicit page markers like '--- PAGE 1 ---' or falls back to
    splitting by double newlines / fixed character count.
    """
    # Try explicit page markers first
    page_pattern = r'---\s*PAGE\s+(\d+)\s*---'
    markers = list(re.finditer(page_pattern, text, re.IGNORECASE))

    if len(markers) >= 2:
        chunks = []
        for i, marker in enumerate(markers):
            page_num = int(marker.group(1))
            start = marker.end()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
            content = text[start:end].strip()
            if content:
                chunks.append(PageChunk(page_number=page_num, content=content))
        return chunks

    # Fallback: split by double newlines into ~paragraph blocks, then group into pages
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    if not paragraphs:
        return [PageChunk(page_number=1, content=text.strip())]

    # Group paragraphs into pages (~2000 chars each to simulate book pages)
    chunks = []
    page_num = 1
    current_content = []
    current_length = 0
    PAGE_SIZE = 2000

    for para in paragraphs:
        current_content.append(para)
        current_length += len(para)

        if current_length >= PAGE_SIZE:
            chunks.append(PageChunk(
                page_number=page_num,
                content="\n\n".join(current_content)
            ))
            page_num += 1
            current_content = []
            current_length = 0

    # Don't forget the last chunk
    if current_content:
        chunks.append(PageChunk(
            page_number=page_num,
            content="\n\n".join(current_content)
        ))

    return chunks


def chunk_pdf(pdf_bytes: bytes) -> List[PageChunk]:
    """Extract text from a PDF file, one chunk per page."""
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        print(f"[BookBot] Processing PDF with {num_pages} pages...")
        
        chunks = []
        empty_pages = 0

        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
                if text and text.strip():
                    chunks.append(PageChunk(
                        page_number=i + 1,
                        content=text.strip()
                    ))
                else:
                    empty_pages += 1
            except Exception as e:
                print(f"[BookBot] ⚠️ Error extracting text from page {i+1}: {e}")
                empty_pages += 1

        print(f"[BookBot] Extraction complete: {len(chunks)} pages with text, {empty_pages} empty pages.")
        
        if len(chunks) == 0 and num_pages > 0:
            print("[BookBot] ❌ CRITICAL: No text could be extracted from any page. This PDF might be a scanned image or encrypted.")
            
        return chunks
    except Exception as e:
        print(f"[BookBot] ❌ Error reading PDF: {e}")
        return []


# ─── Embedding & Storage ──────────────────────────────────────────────

def embed_texts(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts."""
    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=True)
    return embeddings.tolist()


def embed_query(query: str) -> List[float]:
    """Generate embedding for a single query string."""
    model = get_embedding_model()
    embedding = model.encode(query)
    return embedding.tolist()


def store_chunks(book_id: str, chunks: List[PageChunk]) -> int:
    """
    Embed all chunks and store them in ChromaDB with page_number metadata.
    Returns the number of chunks stored.
    """
    if not chunks:
        return 0

    collection = get_collection(book_id)

    # Prepare data for ChromaDB
    texts = [chunk.content for chunk in chunks]
    embeddings = embed_texts(texts)

    ids = [f"{book_id}_page_{chunk.page_number}" for chunk in chunks]
    metadatas = [
        {"book_id": book_id, "page_number": chunk.page_number}
        for chunk in chunks
    ]

    # Upsert into ChromaDB (handles duplicates gracefully)
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas
    )

    print(f"[BookBot] Stored {len(chunks)} chunks for book '{book_id}'")
    return len(chunks)
