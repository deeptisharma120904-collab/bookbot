"""
BookBot FastAPI application.
Main entry point with all API endpoints for book ingestion, chat, and session management.
"""

import asyncio
import re
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from .embeddings import chunk_pdf, chunk_text, store_chunks, delete_book_collection, delete_all_collections, get_pdf_page_count
from .llm import (
    build_catchup_prompt,
    build_character_prompt,
    build_page_explain_prompt,
    build_summary_prompt,
    build_system_prompt,
    async_chat_with_groq,
    chat_with_groq,
    generate_quote,
    generate_suggestions,
)
from .models import (
    BookListItem,
    ChatRequest,
    ChatResponse,
    IngestRequestJSON,
    IngestResponse,
    IngestionStatusResponse,
    SessionResponse,
    SessionSyncRequest,
    SuggestionsResponse,
)
from .retrieval import get_page_chunk, retrieve_context, retrieve_page_range
from .session import (
    clear_all_books_data,
    delete_book_data,
    get_book_metadata,
    get_ingestion_status,
    get_session,
    get_user_stats,
    list_books,
    load_state_from_disk,
    record_chat_interaction,
    save_state_to_disk,
    set_ingestion_status,
    store_book_metadata,
    update_session,
)

# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("=" * 60)
    print("BookBot - Context-Aware Reading Assistant")
    print("=" * 60)
    print("[BookBot] Starting up...")
    # Initialise the SQLite vector store (creates tables if not present)
    from .vector_store import init_db
    init_db()
    load_state_from_disk()
    yield
    print("\n[BookBot] Shutting down...")
    save_state_to_disk()


app = FastAPI(
    title="BookBot API",
    description="Context-aware reading assistant that never spoils your book.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Serve the built React frontend ─────────────────────────────
# Path to the Vite build output (frontend/dist)
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIR.is_dir():
    # Serve JS/CSS/images from /assets
    app.mount(
        "/assets",
        StaticFiles(directory=_FRONTEND_DIR / "assets"),
        name="static-assets",
    )

    @app.get("/")
    async def serve_spa_root():
        """Serve the React app for the root URL."""
        return FileResponse(_FRONTEND_DIR / "index.html")
else:
    @app.get("/")
    async def root():
        return {"message": "BookBot API is running! (frontend not built — run 'npm run build' in frontend/)", "version": "1.0.0"}


@app.post("/api/books/ingest", response_model=IngestResponse)
async def ingest_book_json(request: IngestRequestJSON):
    """
    Ingest a book from plain text (JSON body).
    Chunks the text, generates embeddings, and stores in ChromaDB.
    """
    try:
        chunks, total_pages = chunk_text(request.content)

        if not chunks:
            raise HTTPException(status_code=400, detail="No content could be extracted from the book.")

        num_stored = store_chunks(request.book_id, chunks)

        store_book_metadata(
            book_id=request.book_id,
            title=request.title,
            author=request.author,
            total_pages=total_pages,
        )

        set_ingestion_status(
            book_id=request.book_id,
            status="completed",
            processed_pages=total_pages,
            total_pages=total_pages,
        )

        return IngestResponse(
            book_id=request.book_id,
            title=request.title,
            total_pages=total_pages,
            message=f"Successfully ingested {num_stored} pages.",
        )

    except HTTPException:
        raise
    except Exception as exc:
        set_ingestion_status(
            book_id=request.book_id,
            status="failed",
            processed_pages=0,
            total_pages=1,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")


@app.post("/api/books/ingest/pdf", response_model=IngestResponse)
async def ingest_book_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    book_id: str = Form(...),
    title: str = Form(...),
    author: str = Form(...),
):
    """
    Ingest a book from a PDF file upload.
    Extracts text per page, generates embeddings, and stores in SQLite
    vector store. Runs in the background to prevent long requests from
    timing out.
    """
    # Validate by both content-type and file extension
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only .pdf files are accepted.")
    if file.content_type and file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")

    try:
        await file.seek(0)
        pdf_bytes = await file.read()
        print(f"[BookBot] Received PDF '{file.filename}' of size {len(pdf_bytes)} bytes")

        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="The uploaded file is empty (0 bytes received).")

        # Get total pages instantly without parsing all text
        total_pages = get_pdf_page_count(pdf_bytes)
        if total_pages == 0:
            raise HTTPException(status_code=400, detail="Could not read PDF structure. File may be corrupted.")

        # Store metadata immediately so the UI knows the book exists
        store_book_metadata(
            book_id=book_id,
            title=title,
            author=author,
            total_pages=total_pages,
        )

        # Initialize ingestion tracking
        set_ingestion_status(
            book_id=book_id,
            status="processing",
            processed_pages=0,
            total_pages=total_pages,
        )

        # Background worker for the heavy CPU tasks
        async def process_pdf_in_background():
            try:
                print(f"[BookBot] Background ingestion started for '{book_id}'...")
                loop = asyncio.get_event_loop()
                
                # Chunking takes a few seconds (GIL held, but acceptable)
                chunks, extracted_pages = await loop.run_in_executor(None, chunk_pdf, pdf_bytes)
                
                if chunks:
                    # Store in batches of 10 to allow the event loop to breathe and serve requests
                    stored_count = 0
                    for i in range(0, len(chunks), 10):
                        batch = chunks[i:i+10]
                        await loop.run_in_executor(None, partial(store_chunks, book_id, batch))
                        stored_count += len(batch)
                        set_ingestion_status(
                            book_id=book_id,
                            status="processing",
                            processed_pages=min(stored_count, total_pages),
                            total_pages=total_pages,
                        )
                        await asyncio.sleep(0.05)  # Yield to event loop
                        
                    set_ingestion_status(
                        book_id=book_id,
                        status="completed",
                        processed_pages=total_pages,
                        total_pages=total_pages,
                    )
                    print(f"[BookBot] Background ingestion completed for '{book_id}'.")
                else:
                    set_ingestion_status(
                        book_id=book_id,
                        status="failed",
                        processed_pages=0,
                        total_pages=total_pages,
                        error="No readable text could be extracted from this PDF.",
                    )
                    print(f"[BookBot] ❌ No text extracted for '{book_id}'.")
            except Exception as e:
                set_ingestion_status(
                    book_id=book_id,
                    status="failed",
                    processed_pages=0,
                    total_pages=total_pages,
                    error=str(e),
                )
                print(f"[BookBot] ❌ Background ingestion failed for '{book_id}': {e}")

        background_tasks.add_task(process_pdf_in_background)

        return IngestResponse(
            book_id=book_id,
            title=title,
            total_pages=total_pages,
            message=f"Upload complete. Processing {total_pages} pages in the background...",
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF ingestion failed: {exc}")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint with anti-spoiler logic.
    Detects special query patterns and uses appropriate retrieval strategy.
    """
    book = get_book_metadata(request.book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book '{request.book_id}' not found. Please ingest it first.")

    update_session(request.user_id, request.book_id, request.current_page)
    record_chat_interaction(request.user_id)

    message_lower = request.message.lower().strip()
    recent_history = _format_recent_history(request.history)

    try:
        page_summary_request = _resolve_page_summary_request(message_lower, request.current_page)
        if page_summary_request is not None:
            target_page, page_label = page_summary_request
            if target_page > request.current_page:
                return ChatResponse(
                    reply="I can't reveal that - you haven't reached that part yet! Keep reading 📖",
                    sources=[],
                )
            page_content = get_page_chunk(request.book_id, target_page)
            if page_content:
                context_text = f"[Page {target_page}]\n{page_content}"
                system_prompt = build_system_prompt(
                    book.title, book.author, request.current_page, context_text
                )
                user_prompt = _combine_user_prompt(
                    recent_history,
                    (
                        f"Summarize only {page_label} (page {target_page}) in a concise, spoiler-free way. "
                        "Do not summarize the whole book so far."
                    ),
                )
                reply = await async_chat_with_groq(system_prompt, user_prompt)
                return ChatResponse(reply=reply, sources=[target_page])

        if any(kw in message_lower for kw in ["summarize", "summary", "what happened so far", "recap everything"]):
            context_data = retrieve_page_range(
                book_id=request.book_id,
                start_page=1,
                end_page=request.current_page,
                max_chunks=5,
            )

            context_text = _format_context(context_data)
            system_prompt = build_system_prompt(
                book.title, book.author, request.current_page, context_text
            )
            user_prompt = _combine_user_prompt(recent_history, build_summary_prompt(request.current_page))
            reply = await async_chat_with_groq(system_prompt, user_prompt)

            return ChatResponse(reply=reply, sources=context_data.get("page_numbers", []))

        target_page_info = _resolve_requested_page(message_lower, request.current_page)
        if target_page_info and _is_page_specific_question(message_lower):
            target_page, page_label = target_page_info
            page_content = get_page_chunk(request.book_id, target_page)
            if target_page > request.current_page:
                return ChatResponse(
                    reply="I can't reveal that - you haven't reached that part yet! Keep reading.",
                    sources=[],
                )
            if page_content:
                context_text = f"[Page {target_page}]\n{page_content}"
                system_prompt = build_system_prompt(
                    book.title, book.author, request.current_page, context_text
                )
                user_prompt = _combine_user_prompt(
                    recent_history,
                    f"{build_page_explain_prompt(target_page)} Focus only on {page_label}.",
                )
                reply = await async_chat_with_groq(system_prompt, user_prompt)
                return ChatResponse(reply=reply, sources=[target_page])

            return ChatResponse(
                reply=f"I couldn't find content for page {target_page}. It might not exist in the ingested book.",
                sources=[],
            )

        if any(kw in message_lower for kw in ["catch me up", "forgot", "where was i", "remind me"]):
            start = max(1, request.current_page - 20)
            context_data = retrieve_page_range(
                book_id=request.book_id,
                start_page=start,
                end_page=request.current_page,
                max_chunks=5,
            )
            context_text = _format_context(context_data)
            system_prompt = build_system_prompt(
                book.title, book.author, request.current_page, context_text
            )
            user_prompt = _combine_user_prompt(recent_history, build_catchup_prompt(request.current_page))
            reply = await async_chat_with_groq(system_prompt, user_prompt)
            return ChatResponse(reply=reply, sources=context_data.get("page_numbers", []))

        who_match = re.search(r"who\s+is\s+(.+?)[\?\.]?$", message_lower)
        if who_match:
            character_name = who_match.group(1).strip()
            context_data = retrieve_context(
                query=f"character {character_name}",
                book_id=request.book_id,
                current_page=request.current_page,
                top_k=4,
            )
            context_text = _format_context(context_data)
            system_prompt = build_system_prompt(
                book.title, book.author, request.current_page, context_text
            )
            user_prompt = _combine_user_prompt(
                recent_history,
                build_character_prompt(character_name, request.current_page),
            )
            reply = await async_chat_with_groq(system_prompt, user_prompt)
            return ChatResponse(reply=reply, sources=context_data.get("page_numbers", []))

        retrieval_query = request.message
        context_data = retrieve_context(
            query=retrieval_query,
            book_id=request.book_id,
            current_page=request.current_page,
            top_k=5,
        )
        context_text = _format_context(context_data)
        system_prompt = build_system_prompt(
            book.title, book.author, request.current_page, context_text
        )

        user_prompt = _combine_user_prompt(recent_history, request.message)

        # Issue 17+18: Fire answer and suggestions concurrently — halves latency
        reply, suggestions = await asyncio.gather(
            async_chat_with_groq(system_prompt, user_prompt),
            asyncio.to_thread(
                generate_suggestions,
                book.title, book.author, request.current_page, context_text
            ),
        )

        return ChatResponse(
            reply=reply,
            sources=context_data.get("page_numbers", []),
            suggestions=suggestions,
        )

    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat error: {exc}")


@app.get("/api/session/{user_id}/{book_id}", response_model=SessionResponse)
def get_reading_session(user_id: str, book_id: str):
    """Get the current reading progress and stats for a user and book."""
    session = get_session(user_id, book_id)
    stats = get_user_stats(user_id)

    if not session:
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
        stats=stats,
    )


@app.post("/api/session/sync", response_model=SessionResponse)
def sync_session(request: SessionSyncRequest):
    """
    Webhook endpoint for reading platforms.
    Updates the user's current page and awards XP.
    """
    session = update_session(
        user_id=request.user_id,
        book_id=request.book_id,
        current_page=request.current_page,
    )
    stats = get_user_stats(request.user_id)

    return SessionResponse(
        user_id=session.user_id,
        book_id=session.book_id,
        current_page=session.current_page,
        last_updated=session.last_updated,
        stats=stats,
    )


@app.get("/api/books/suggestions/{book_id}/{current_page}", response_model=SuggestionsResponse)
def get_smart_suggestions(book_id: str, current_page: int):
    """Generate 3 smart conversation starters based on the current page."""
    book = get_book_metadata(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")

    context_data = retrieve_page_range(book_id, max(1, current_page - 5), current_page, max_chunks=5)
    context_text = _format_context(context_data)

    suggestions = generate_suggestions(book.title, book.author, current_page, context_text)
    return SuggestionsResponse(suggestions=suggestions)


@app.get("/api/books/quote/{book_id}/{current_page}")
def get_book_quote(book_id: str, current_page: int):
    """Retrieve a random beautiful quote from the pages read so far."""
    book = get_book_metadata(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")

    context_data = retrieve_page_range(book_id, 1, current_page, max_chunks=6)
    context_text = _format_context(context_data)

    quote_data = generate_quote(book.title, book.author, context_text)
    return quote_data


@app.get("/api/books/page/{book_id}/{page_number}")
def get_book_page(book_id: str, page_number: int):
    """Retrieve the text content for a specific page."""
    book = get_book_metadata(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")

    if page_number < 1 or page_number > book.total_pages:
        raise HTTPException(status_code=404, detail="Page out of range.")

    content = get_page_chunk(book_id, page_number)

    # If the exact page has no text (blank / image-only PDF page), search
    # nearby pages so the reader never sees a perpetual "processing" spinner.
    if not content:
        from .vector_store import _connect, init_db
        init_db()
        conn = _connect()
        try:
            # Find the nearest stored page (search within ±5 pages)
            row = conn.execute(
                "SELECT page_number, content FROM chunks "
                "WHERE book_id = ? AND page_number >= ? "
                "ORDER BY page_number LIMIT 1",
                (book_id, page_number),
            ).fetchone()
            if row:
                content = row["content"]
                page_number = row["page_number"]
        finally:
            conn.close()

    if not content:
        return {
            "page_number": page_number,
            "page_type": "processing",
            "content": None,
            "title": book.title,
            "author": book.author,
            "message": "This page has no extractable text (it may be a cover or image-only page).",
        }

    return {
        "page_number": page_number,
        "page_type": "text",
        "content": content,
        "title": book.title,
        "author": book.author,
        "message": "",
    }


@app.get("/api/books", response_model=list[BookListItem])
def get_books():
    """List all ingested books."""
    books = list_books()
    return [
        BookListItem(
            book_id=book.book_id,
            title=book.title,
            author=book.author,
            total_pages=book.total_pages,
        )
        for book in books
    ]


@app.get("/api/books/{book_id}/status", response_model=IngestionStatusResponse)
def get_book_status(book_id: str):
    """Check the background processing and embedding status of a book."""
    status = get_ingestion_status(book_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found.")
    return IngestionStatusResponse(**status)


@app.delete("/api/books/{book_id}")
def delete_book_endpoint(book_id: str):
    """
    Delete a book and all its associated content embeddings and session data.
    """
    book = get_book_metadata(book_id)
    if not book:
        # If metadata not found, attempt vector cleanup anyway
        delete_book_collection(book_id)
        delete_book_data(book_id)
        return {"message": f"Cleaned up data for book '{book_id}'."}

    delete_book_collection(book_id)
    delete_book_data(book_id)

    return {"message": f"Successfully removed book '{book.title}' and all associated content data."}


@app.delete("/api/books")
def clear_all_books_endpoint():
    """
    Delete all books, content embeddings, and session data.
    """
    delete_all_collections()
    clear_all_books_data()

    return {"message": "Successfully cleared all books and content data from BookBot."}



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


def _format_recent_history(history: list) -> str:
    """Format recent chat turns to help with follow-up questions."""
    if not history:
        return ""

    formatted = []
    for item in history[-6:]:
        role = "User" if item.role == "user" else "Assistant"
        content = item.content.strip()
        if content:
            formatted.append(f"{role}: {content}")

    return "\n".join(formatted)


def _combine_user_prompt(recent_history: str, latest_message: str) -> str:
    """Attach recent conversation without overriding retrieved book context."""
    if not recent_history:
        return latest_message

    return (
        "Recent conversation for reference:\n"
        f"{recent_history}\n\n"
        "Use this recent conversation only to resolve follow-up references such as pronouns "
        "or implied subjects. If it conflicts with the retrieved book context, trust the "
        "retrieved book context.\n\n"
        f"Latest user request:\n{latest_message}"
    )


def _resolve_page_summary_request(message_lower: str, current_page: int):
    """Detect requests for a summary of the current, previous, or named page."""
    wants_summary = any(
        phrase in message_lower
        for phrase in ["summary", "summarize", "recap", "what happened on"]
    )
    if not wants_summary:
        return None

    return _resolve_requested_page(message_lower, current_page)


def _resolve_requested_page(message_lower: str, current_page: int):
    """Resolve phrases like 'last page', 'previous page', or 'page no. 9'."""
    if any(phrase in message_lower for phrase in ["previous page", "prev page", "last page before this"]):
        return (max(1, current_page - 1), "the previous page")

    if any(phrase in message_lower for phrase in ["this page", "current page", "latest page"]):
        return (current_page, "the current page")

    if "last page" in message_lower:
        return (max(1, current_page - 1), "the previous page")

    page_match = re.search(r"(?:page|pg\.?)\s*(?:number|no\.?)?\s*(\d+)", message_lower)
    if page_match:
        target_page = int(page_match.group(1))
        return (target_page, f"page {target_page}")

    return None


def _is_page_specific_question(message_lower: str) -> bool:
    """Detect requests that should be answered from one exact page."""
    page_keywords = [
        "what happened",
        "tell me about",
        "explain",
        "summary",
        "summarize",
        "recap",
        "who is",
        "what is",
        "why",
        "how",
    ]
    return any(keyword in message_lower for keyword in page_keywords)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
