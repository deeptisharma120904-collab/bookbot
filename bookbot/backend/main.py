"""
BookBot — FastAPI application.
Main entry point with all API endpoints for book ingestion, chat, and session management.
"""

import os
import re
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from .models import (
    IngestRequestJSON, ChatRequest, ChatResponse,
    SessionSyncRequest, SessionResponse, BookListItem,
    IngestResponse, SuggestionsResponse
)
from .embeddings import chunk_text, chunk_pdf, store_chunks
from .retrieval import retrieve_context, get_page_chunk, retrieve_page_range
from .llm import (
    build_system_prompt, chat_with_groq,
    build_summary_prompt, build_page_explain_prompt,
    build_catchup_prompt, build_character_prompt,
    generate_suggestions, generate_quote
)
from .session import (
    get_session, update_session,
    store_book_metadata, get_book_metadata, list_books,
    get_user_stats,
    load_state_from_disk, save_state_to_disk
)


# ─── App Lifecycle ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("=" * 60)
    print("BookBot - Context-Aware Reading Assistant")
    print("=" * 60)
    print("[BookBot] Starting up...")
    load_state_from_disk()
    yield
    print("\n[BookBot] Shutting down...")
    save_state_to_disk()


# ─── FastAPI App ──────────────────────────────────────────────────────

app = FastAPI(
    title="BookBot API",
    description="Context-aware reading assistant that never spoils your book.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health Check ─────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "BookBot API is running!", "version": "1.0.0"}


# ─── Book Ingestion ───────────────────────────────────────────────────

@app.post("/api/books/ingest", response_model=IngestResponse)
async def ingest_book_json(request: IngestRequestJSON):
    """
    Ingest a book from plain text (JSON body).
    Chunks the text, generates embeddings, and stores in ChromaDB.
    """
    try:
        # Chunk the text
        chunks = chunk_text(request.content)

        if not chunks:
            raise HTTPException(status_code=400, detail="No content could be extracted from the book.")

        # Store embeddings in ChromaDB
        num_stored = store_chunks(request.book_id, chunks)

        # Store book metadata
        store_book_metadata(
            book_id=request.book_id,
            title=request.title,
            author=request.author,
            total_pages=len(chunks)
        )

        return IngestResponse(
            book_id=request.book_id,
            title=request.title,
            total_pages=len(chunks),
            message=f"Successfully ingested {num_stored} pages."
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.post("/api/books/ingest/pdf", response_model=IngestResponse)
async def ingest_book_pdf(
    file: UploadFile = File(...),
    book_id: str = Form(...),
    title: str = Form(...),
    author: str = Form(...)
):
    """
    Ingest a book from a PDF file upload.
    Extracts text per page, generates embeddings, and stores in ChromaDB.
    """
    if file.content_type and file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")

    try:
        # Read PDF bytes
        await file.seek(0)
        pdf_bytes = await file.read()
        print(f"[BookBot] Received PDF '{file.filename}' of size {len(pdf_bytes)} bytes")
        
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="The uploaded file is empty (0 bytes received).")

        # Chunk the PDF (one chunk per page)
        chunks = chunk_pdf(pdf_bytes)

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No text could be extracted from the PDF. It may be a scanned document."
            )

        # Store embeddings in ChromaDB
        num_stored = store_chunks(book_id, chunks)

        # Store book metadata
        store_book_metadata(
            book_id=book_id,
            title=title,
            author=author,
            total_pages=len(chunks)
        )

        return IngestResponse(
            book_id=book_id,
            title=title,
            total_pages=len(chunks),
            message=f"Successfully ingested {num_stored} pages from PDF."
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF ingestion failed: {str(e)}")


# ─── Chat Endpoint ────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint with anti-spoiler logic.
    Detects special query patterns and uses appropriate retrieval strategy.
    """
    # Get book metadata
    book = get_book_metadata(request.book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book '{request.book_id}' not found. Please ingest it first.")

    # Update session
    update_session(request.user_id, request.book_id, request.current_page)

    message_lower = request.message.lower().strip()

    try:
        # ─── Special Query: Summarize ─────────────────────────
        if any(kw in message_lower for kw in ["summarize", "summary", "what happened so far", "recap everything"]):
            context_data = retrieve_page_range(
                book_id=request.book_id,
                start_page=1,
                end_page=request.current_page,
                max_chunks=5
            )
            
            context_text = _format_context(context_data)
            system_prompt = build_system_prompt(
                book.title, book.author, request.current_page, context_text
            )
            user_prompt = build_summary_prompt(request.current_page)
            reply = chat_with_groq(system_prompt, user_prompt)
            
            return ChatResponse(reply=reply, sources=context_data.get("page_numbers", []))

        # ─── Special Query: Specific Page ─────────────────────
        page_match = re.search(r'(?:page|pg\.?)\s*(\d+)', message_lower)
        if page_match and any(kw in message_lower for kw in ["what happened", "explain", "tell me about page", "page"]):
            target_page = int(page_match.group(1))
            if target_page > request.current_page:
                return ChatResponse(
                    reply="I can't reveal that — you haven't reached that part yet! Keep reading 📖",
                    sources=[]
                )
            page_content = get_page_chunk(request.book_id, target_page)
            if page_content:
                context_text = f"[Page {target_page}]\n{page_content}"
                system_prompt = build_system_prompt(
                    book.title, book.author, request.current_page, context_text
                )
                user_prompt = build_page_explain_prompt(target_page)
                reply = chat_with_groq(system_prompt, user_prompt)
                return ChatResponse(reply=reply, sources=[target_page])
            else:
                return ChatResponse(
                    reply=f"I couldn't find content for page {target_page}. It might not exist in the ingested book.",
                    sources=[]
                )

        # ─── Special Query: Catch Me Up ───────────────────────
        if any(kw in message_lower for kw in ["catch me up", "forgot", "where was i", "remind me"]):
            start = max(1, request.current_page - 20)
            context_data = retrieve_page_range(
                book_id=request.book_id,
                start_page=start,
                end_page=request.current_page,
                max_chunks=5
            )
            context_text = _format_context(context_data)
            system_prompt = build_system_prompt(
                book.title, book.author, request.current_page, context_text
            )
            user_prompt = build_catchup_prompt(request.current_page)
            reply = chat_with_groq(system_prompt, user_prompt)
            return ChatResponse(reply=reply, sources=context_data.get("page_numbers", []))

        # ─── Special Query: Character ─────────────────────────
        who_match = re.search(r'who\s+is\s+(.+?)[\?\.]?$', message_lower)
        if who_match:
            character_name = who_match.group(1).strip()
            context_data = retrieve_context(
                query=f"character {character_name}",
                book_id=request.book_id,
                current_page=request.current_page,
                top_k=4
            )
            context_text = _format_context(context_data)
            system_prompt = build_system_prompt(
                book.title, book.author, request.current_page, context_text
            )
            user_prompt = build_character_prompt(character_name, request.current_page)
            reply = chat_with_groq(system_prompt, user_prompt)
            return ChatResponse(reply=reply, sources=context_data.get("page_numbers", []))

        # ─── Default: Semantic Search ─────────────────────────
        context_data = retrieve_context(
            query=request.message,
            book_id=request.book_id,
            current_page=request.current_page,
            top_k=5
        )
        context_text = _format_context(context_data)
        system_prompt = build_system_prompt(
            book.title, book.author, request.current_page, context_text
        )
        reply = chat_with_groq(system_prompt, request.message)
        
        # Generate dynamic suggestions for follow-up
        suggestions = generate_suggestions(
            book.title, book.author, request.current_page, context_text
        )
        
        return ChatResponse(
            reply=reply, 
            sources=context_data.get("page_numbers", []),
            suggestions=suggestions
        )

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


# ─── Session Endpoints ────────────────────────────────────────────────

@app.get("/api/session/{user_id}/{book_id}", response_model=SessionResponse)
async def get_reading_session(user_id: str, book_id: str):
    """Get the current reading progress and stats for a user and book."""
    session = get_session(user_id, book_id)
    stats = get_user_stats(user_id)
    
    if not session:
        # Create a default session if it doesn't exist but book is known
        book = get_book_metadata(book_id)
        if book:
            session = update_session(user_id, book_id, 1)
        else:
            raise HTTPException(status_code=404, detail="Book not found.")

    return SessionResponse(
        user_id=session.user_id,
        book_id=session.book_id,
        current_page=session.current_page,
        last_updated=session.last_updated,
        stats=stats
    )


@app.post("/api/session/sync", response_model=SessionResponse)
async def sync_session(request: SessionSyncRequest):
    """
    Webhook endpoint for reading platforms.
    Updates the user's current page and awards XP.
    """
    session = update_session(
        user_id=request.user_id,
        book_id=request.book_id,
        current_page=request.current_page
    )
    stats = get_user_stats(request.user_id)

    return SessionResponse(
        user_id=session.user_id,
        book_id=session.book_id,
        current_page=session.current_page,
        last_updated=session.last_updated,
        stats=stats
    )


# ─── Advanced Features ────────────────────────────────────────────────

@app.get("/api/books/suggestions/{book_id}/{current_page}", response_model=SuggestionsResponse)
async def get_smart_suggestions(book_id: str, current_page: int):
    """Generate 3 smart conversation starters based on the current page."""
    book = get_book_metadata(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
        
    context_data = retrieve_page_range(book_id, max(1, current_page-5), current_page, max_chunks=5)
    context_text = _format_context(context_data)
    
    suggestions = generate_suggestions(book.title, book.author, current_page, context_text)
    return SuggestionsResponse(suggestions=suggestions)


@app.get("/api/books/quote/{book_id}/{current_page}")
async def get_book_quote(book_id: str, current_page: int):
    """Retrieve a random beautiful quote from the pages read so far."""
    book = get_book_metadata(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
        
    # Sample a smaller range for better quote selection while respecting token limits
    context_data = retrieve_page_range(book_id, 1, current_page, max_chunks=6)
    context_text = _format_context(context_data)
    
    quote_data = generate_quote(book.title, book.author, context_text)
    return quote_data

@app.get("/api/books/page/{book_id}/{page_number}")
async def get_book_page(book_id: str, page_number: int):
    """Retrieve the text content for a specific page."""
    book = get_book_metadata(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
    
    if page_number < 1 or page_number > book.total_pages:
        raise HTTPException(status_code=404, detail="Page out of range.")
        
    content = get_page_chunk(book_id, page_number)
    if not content:
        raise HTTPException(status_code=404, detail="Page content not found.")
        
    return {"content": content}


# ─── Book Listing ─────────────────────────────────────────────────────

@app.get("/api/books", response_model=list[BookListItem])
async def get_books():
    """List all ingested books."""
    books = list_books()
    return [
        BookListItem(
            book_id=b.book_id,
            title=b.title,
            author=b.author,
            total_pages=b.total_pages
        )
        for b in books
    ]


# ─── Helpers ──────────────────────────────────────────────────────────

def _format_context(context_data: dict) -> str:
    """Format retrieved chunks into a readable context string for the LLM."""
    documents = context_data.get("documents", [])
    page_numbers = context_data.get("page_numbers", [])

    if not documents:
        return "No relevant context found in the pages you've read so far."

    formatted = []
    for page_num, doc in zip(page_numbers, documents):
        formatted.append(f"[Page {page_num}]\n{doc}")

    return "\n\n---\n\n".join(formatted)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
