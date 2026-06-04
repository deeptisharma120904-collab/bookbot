"""
BookBot — CLI script to ingest a book from a local file.

Usage:
  python -m bookbot.scripts.ingest_book --file book.pdf --title "The Great Gatsby" --author "F. Scott Fitzgerald"
  python -m bookbot.scripts.ingest_book --file book.txt --title "My Book" --author "Author Name" --book-id my_book
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dotenv import load_dotenv
load_dotenv()

from bookbot.backend.embeddings import chunk_text, chunk_pdf, store_chunks
from bookbot.backend.session import store_book_metadata


def main():
    parser = argparse.ArgumentParser(description="Ingest a book into BookBot")
    parser.add_argument("--file", required=True, help="Path to the book file (PDF or TXT)")
    parser.add_argument("--title", required=True, help="Book title")
    parser.add_argument("--author", required=True, help="Book author")
    parser.add_argument("--book-id", default=None, help="Book ID (defaults to sanitized title)")

    args = parser.parse_args()

    # Generate book_id from title if not provided
    book_id = args.book_id or args.title.lower().replace(" ", "_").replace("'", "")

    file_path = args.file
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    print(f"📚 Ingesting: {args.title} by {args.author}")
    print(f"   Book ID: {book_id}")
    print(f"   File: {file_path}")
    print()

    # Determine file type and chunk accordingly
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        print("📄 Reading PDF file...")
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
        chunks = chunk_pdf(pdf_bytes)
    elif ext in [".txt", ".md", ".text"]:
        print("📝 Reading text file...")
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        chunks = chunk_text(text)
    else:
        print(f"❌ Unsupported file type: {ext}")
        print("   Supported: .pdf, .txt, .md")
        sys.exit(1)

    if not chunks:
        print("❌ No content could be extracted from the file.")
        sys.exit(1)

    print(f"✂️  Split into {len(chunks)} pages/chunks")
    print()

    # Generate embeddings and store
    print("🧠 Generating embeddings and storing in ChromaDB...")
    num_stored = store_chunks(book_id, chunks)

    # Store metadata
    store_book_metadata(
        book_id=book_id,
        title=args.title,
        author=args.author,
        total_pages=len(chunks)
    )

    print()
    print(f"✅ Successfully ingested '{args.title}'!")
    print(f"   Pages: {len(chunks)}")
    print(f"   Chunks stored: {num_stored}")
    print(f"   Book ID: {book_id}")


if __name__ == "__main__":
    main()
