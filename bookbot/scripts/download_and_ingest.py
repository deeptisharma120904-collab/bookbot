"""
BookBot — Quick-start helper.
Downloads a free public-domain book from Project Gutenberg and ingests it.

Usage (from project root, with venv active):
    python -m bookbot.scripts.download_and_ingest

This uses Alice's Adventures in Wonderland by Lewis Carroll — a short book
(~160 chunks) that is ideal for the Phase 1 eval set because:
  • It has clear events tied to specific pages
  • It is well-known, so you can verify answers without re-reading
  • It is short enough to review all 20 eval questions quickly
"""

import os
import sys
import re
import urllib.request

# Fix Windows console UTF-8 encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Add project root to path ──────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from bookbot.backend.embeddings import chunk_text, store_chunks
from bookbot.backend.session import store_book_metadata

BOOK_ID    = "alice_in_wonderland"
TITLE      = "Alice's Adventures in Wonderland"
AUTHOR     = "Lewis Carroll"
GUTENBERG_URL = (
    "https://www.gutenberg.org/files/11/11-0.txt"
)


def download_text(url: str) -> str:
    """Download raw UTF-8 text from a URL."""
    import ssl
    print(f"[Download] Fetching from Project Gutenberg...")
    print(f"   {url}")
    # Create an unverified SSL context — acceptable for public Gutenberg URLs
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(url, timeout=30, context=ctx) as resp:
        raw = resp.read()
    # Gutenberg files are UTF-8 with BOM sometimes
    return raw.decode("utf-8-sig")


def strip_gutenberg_header_footer(text: str) -> str:
    """Remove the standard Gutenberg boilerplate from start and end."""
    # Find the actual book start (after the licence header)
    start_markers = [
        "*** START OF THE PROJECT GUTENBERG EBOOK",
        "***START OF THE PROJECT GUTENBERG EBOOK",
        "CHAPTER I",
        "CHAPTER 1",
    ]
    start_pos = 0
    for marker in start_markers:
        idx = text.find(marker)
        if idx != -1:
            # Skip past the marker line
            start_pos = text.find("\n", idx) + 1
            break

    # Find the end (before the licence footer)
    end_markers = [
        "*** END OF THE PROJECT GUTENBERG EBOOK",
        "***END OF THE PROJECT GUTENBERG EBOOK",
        "End of the Project Gutenberg",
        "End of Project Gutenberg",
    ]
    end_pos = len(text)
    for marker in end_markers:
        idx = text.rfind(marker)
        if idx != -1:
            end_pos = idx
            break

    return text[start_pos:end_pos].strip()


def main() -> None:
    print("=" * 60)
    print(f"[BookBot] Quick Ingest: {TITLE}")
    print("=" * 60)

    # ── 1. Download ───────────────────────────────────────────────
    try:
        raw_text = download_text(GUTENBERG_URL)
        print(f"   Downloaded {len(raw_text):,} characters.")
    except Exception as exc:
        print(f"\nERROR: Download failed: {exc}")
        print(
            "\nFallback: download the file manually from:\n"
            f"  {GUTENBERG_URL}\n"
            "then run:\n"
            "  python -m bookbot.scripts.ingest_book "
            "--file alice.txt "
            f'--title "{TITLE}" '
            f'--author "{AUTHOR}" '
            f"--book-id {BOOK_ID}"
        )
        sys.exit(1)

    # ── 2. Strip boilerplate ───────────────────────────────────────
    book_text = strip_gutenberg_header_footer(raw_text)
    print(f"   After stripping Gutenberg header/footer: {len(book_text):,} chars.")

    # ── 3. Chunk ───────────────────────────────────────────────────
    print("\n[Chunking] Splitting into pages...")
    chunks, total_pages = chunk_text(book_text)
    print(f"   Created {len(chunks)} chunks / {total_pages} total pages.")

    if not chunks:
        print("ERROR: No chunks produced -- check the downloaded file.")
        sys.exit(1)

    # ── 4. Store in ChromaDB ───────────────────────────────────────
    print("\n[Embedding] Storing in ChromaDB...")
    num_stored = store_chunks(BOOK_ID, chunks)

    # ── 5. Store metadata ──────────────────────────────────────────
    store_book_metadata(
        book_id=BOOK_ID,
        title=TITLE,
        author=AUTHOR,
        total_pages=total_pages,
    )

    print(f"\n{'=' * 60}")
    print(f"SUCCESS: Ingested '{TITLE}'!")
    print(f"   book_id      : {BOOK_ID}")
    print(f"   total_pages  : {total_pages}")
    print(f"   chunks stored: {num_stored}")
    print(f"{'=' * 60}")
    print(
        f"\nNext step -- build the Phase 1 eval draft:\n"
        f"  python -m bookbot.evals.build_eval_draft --book_id {BOOK_ID}"
    )


if __name__ == "__main__":
    main()
