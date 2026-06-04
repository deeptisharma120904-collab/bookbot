"""
BookBot — Pydantic data models for API requests, responses, and internal data structures.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# ─── Internal Data Models ─────────────────────────────────────────────

class PageChunk(BaseModel):
    """Represents a single page/chunk of a book."""
    page_number: int
    content: str


class BookMetadata(BaseModel):
    """Metadata about an ingested book."""
    book_id: str
    title: str
    author: str
    total_pages: int


class UserSession(BaseModel):
    """Tracks a user's reading progress for a specific book."""
    user_id: str
    book_id: str
    current_page: int = 1
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class UserStats(BaseModel):
    """User gamification statistics."""
    xp: int = 0
    streak: int = 0
    badges: List[str] = []
    total_pages_read: int = 0
    level: int = 1


# ─── API Request Schemas ──────────────────────────────────────────────

class IngestRequestJSON(BaseModel):
    """Request body for ingesting a book via JSON (plain text)."""
    book_id: str
    title: str
    author: str
    content: str  # Full book text — pages separated by page markers or newlines


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""
    user_id: str
    book_id: str
    current_page: int
    message: str


class SessionSyncRequest(BaseModel):
    """Request body for syncing reading progress (webhook)."""
    user_id: str
    book_id: str
    current_page: int


# ─── API Response Schemas ─────────────────────────────────────────────

class ChatResponse(BaseModel):
    """Response from the chat endpoint."""
    reply: str
    sources: List[int] = []  # Page numbers used as context
    suggestions: List[str] = []  # Dynamic follow-up questions


class SuggestionsResponse(BaseModel):
    """Response for dynamic conversation starters."""
    suggestions: List[str]


class SessionResponse(BaseModel):
    """Response for session queries."""
    user_id: str
    book_id: str
    current_page: int
    last_updated: datetime
    stats: UserStats


class BookListItem(BaseModel):
    """A book in the books list."""
    book_id: str
    title: str
    author: str
    total_pages: int


class IngestResponse(BaseModel):
    """Response after book ingestion."""
    book_id: str
    title: str
    total_pages: int
    message: str
