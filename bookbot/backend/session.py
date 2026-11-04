"""
BookBot — User session management.
Stores reading progress per user per book in-memory (V1).
Can be upgraded to Redis or a database in production.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from .models import UserSession, BookMetadata, UserStats


# ─── In-Memory Stores ─────────────────────────────────────────────────

# Key: "{user_id}:{book_id}" → UserSession
_sessions: Dict[str, UserSession] = {}

# Key: user_id → UserStats
_user_stats: Dict[str, UserStats] = {}

# Key: book_id → BookMetadata
_books: Dict[str, BookMetadata] = {}

# Key: book_id → dict of ingestion status
_ingestion_status: Dict[str, Dict] = {}


def set_ingestion_status(
    book_id: str,
    status: str,
    processed_pages: int,
    total_pages: int,
    error: Optional[str] = None
):
    """Update background ingestion progress for a book."""
    total = max(1, total_pages)
    percentage = round(min(100.0, (processed_pages / total) * 100.0), 1)
    _ingestion_status[book_id] = {
        "book_id": book_id,
        "status": status,
        "processed_pages": processed_pages,
        "total_pages": total_pages,
        "progress_percentage": percentage,
        "error": error
    }


def get_ingestion_status(book_id: str) -> Optional[Dict]:
    """Retrieve the ingestion status of a book."""
    if book_id in _ingestion_status:
        return _ingestion_status[book_id]

    # If the book already exists in metadata, it has finished ingestion
    book = _books.get(book_id)
    if book:
        return {
            "book_id": book_id,
            "status": "completed",
            "processed_pages": book.total_pages,
            "total_pages": book.total_pages,
            "progress_percentage": 100.0,
            "error": None
        }
    return None



# ─── Session Management ───────────────────────────────────────────────

def get_session(user_id: str, book_id: str) -> Optional[UserSession]:
    """Retrieve a user's reading session for a specific book."""
    key = f"{user_id}:{book_id}"
    return _sessions.get(key)


def get_user_stats(user_id: str) -> UserStats:
    """Retrieve or initialize user stats."""
    if user_id not in _user_stats:
        _user_stats[user_id] = UserStats()
    return _user_stats[user_id]


def update_session(user_id: str, book_id: str, current_page: int) -> UserSession:
    """Update or create a user's reading progress and award XP."""
    key = f"{user_id}:{book_id}"
    old_session = _sessions.get(key)
    
    new_session = UserSession(
        user_id=user_id,
        book_id=book_id,
        current_page=current_page,
        last_updated=datetime.utcnow()
    )
    _sessions[key] = new_session
    
    # Update Stats
    stats = get_user_stats(user_id)
    
    # Award XP for progress (10 XP per page)
    if old_session:
        pages_gained = max(0, current_page - old_session.current_page)
        if pages_gained > 0:
            stats.xp += pages_gained * 10
            stats.total_pages_read += pages_gained
            
            # Check for Speed Reader badge
            if pages_gained >= 50:
                _add_badge(stats, "Speed Reader")
    
    # Streak Logic
    now = datetime.now(timezone.utc)
    last_active = old_session.last_updated if old_session else None
    
    if last_active:
        diff = now.date() - last_active.date()
        if diff == timedelta(days=1):
            stats.streak += 1
        elif diff > timedelta(days=1):
            stats.streak = 1
    else:
        stats.streak = 1
        
    # Check for Night Owl badge
    if 0 <= now.hour <= 4:
        _add_badge(stats, "Night Owl")
        
    # Check for Milestone badges
    if current_page >= 10:
        _add_badge(stats, "First Chapter")
    
    book = _books.get(book_id)
    if book:
        if current_page >= book.total_pages / 2:
            _add_badge(stats, "Halfway Hero")
        if current_page >= book.total_pages:
            _add_badge(stats, "Bookworm")
            
    # Level up logic (1000 XP per level)
    stats.level = (stats.xp // 1000) + 1
    
    # Persist session and stats updates immediately
    save_state_to_disk()
    return new_session


def _add_badge(stats: UserStats, badge_name: str):
    if badge_name not in stats.badges:
        stats.badges.append(badge_name)
        print(f"[BookBot] Achievement Unlocked: {badge_name}!")


# Track last chat XP award per user to rate-limit XP farming
_last_chat_xp: Dict[str, datetime] = {}
_CHAT_XP_COOLDOWN_SECONDS = 60  # 1 award per minute max


def record_chat_interaction(user_id: str):
    """Award XP for chatting with the librarian and unlock Curious Mind badge.

    XP is rate-limited to once per minute per user to prevent farming.
    """
    stats = get_user_stats(user_id)
    now = datetime.now(timezone.utc)
    last = _last_chat_xp.get(user_id)
    if last is None or (now - last).total_seconds() >= _CHAT_XP_COOLDOWN_SECONDS:
        stats.xp += 5
        stats.level = (stats.xp // 1000) + 1
        _last_chat_xp[user_id] = now
    _add_badge(stats, "Curious Mind")
    save_state_to_disk()


# ─── Book Metadata Management ─────────────────────────────────────────

def store_book_metadata(book_id: str, title: str, author: str, total_pages: int) -> BookMetadata:
    """Store metadata about an ingested book and immediately persist to disk."""
    metadata = BookMetadata(
        book_id=book_id,
        title=title,
        author=author,
        total_pages=total_pages
    )
    _books[book_id] = metadata
    # Persist immediately so the book survives server restarts and --reload cycles.
    # uvicorn --reload only watches .py files, so writing .json does NOT trigger a reload.
    save_state_to_disk()
    return metadata


def get_book_metadata(book_id: str) -> Optional[BookMetadata]:
    """Retrieve metadata for a book."""
    return _books.get(book_id)


def list_books() -> List[BookMetadata]:
    """List all ingested books."""
    return list(_books.values())


def delete_book_data(book_id: str) -> bool:
    """Delete metadata and session records for a specific book."""
    global _books, _sessions, _ingestion_status
    found = False
    if book_id in _books:
        del _books[book_id]
        found = True

    _ingestion_status.pop(book_id, None)

    keys_to_delete = [k for k in _sessions.keys() if k.endswith(f":{book_id}")]
    for k in keys_to_delete:
        del _sessions[k]
        found = True

    if found:
        save_state_to_disk()
    return found


def clear_all_books_data() -> bool:
    """Clear all book metadata and session records."""
    global _books, _sessions, _ingestion_status
    _books.clear()
    _sessions.clear()
    _ingestion_status.clear()
    save_state_to_disk()
    return True


# ─── State Persistence ────────────────────────────────────────────────

PERSISTENCE_FILE = os.path.join(os.path.dirname(__file__), '..', 'bookbot_state.json')

def save_state_to_disk():
    """Serialize the current in-memory state to a JSON file."""
    print("\n[BookBot] Persisting state to disk...")
    try:
        state = {
            "sessions": {k: v.model_dump() if hasattr(v, 'model_dump') else v.dict() for k, v in _sessions.items()},
            "user_stats": {k: v.model_dump() if hasattr(v, 'model_dump') else v.dict() for k, v in _user_stats.items()},
            "books": {k: v.model_dump() if hasattr(v, 'model_dump') else v.dict() for k, v in _books.items()},
        }
        with open(PERSISTENCE_FILE, 'w') as f:
            json.dump(state, f, indent=2, default=str) # default=str for datetime
        print(f"[BookBot] Successfully saved state for {len(_books)} books to {PERSISTENCE_FILE}")
    except Exception as e:
        print(f"[BookBot] Error saving state: {e}")

def load_state_from_disk():
    """Load state from the JSON file into memory on startup."""
    global _sessions, _user_stats, _books
    if not os.path.exists(PERSISTENCE_FILE):
        print(f"[BookBot] No persistence file found at {PERSISTENCE_FILE}. Starting fresh.")
        return

    print(f"[BookBot] Loading state from {PERSISTENCE_FILE}...")
    try:
        with open(PERSISTENCE_FILE, 'r') as f:
            data = json.load(f)

        _sessions.update({k: UserSession(**v) for k, v in data.get("sessions", {}).items()})
        _user_stats.update({k: UserStats(**v) for k, v in data.get("user_stats", {}).items()})
        _books.update({k: BookMetadata(**v) for k, v in data.get("books", {}).items()})
        
        print(f"[BookBot] Successfully loaded state for {len(_books)} books.")

    except (json.JSONDecodeError, TypeError) as e:
        print(f"[BookBot] Error loading state file: {e}. Starting fresh.")
    except Exception as e:
        print(f"[BookBot] An unexpected error occurred while loading state: {e}")
