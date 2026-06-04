"""
BookBot — User session management.
Stores reading progress per user per book in-memory (V1).
Can be upgraded to Redis or a database in production.
"""

from datetime import datetime
from typing import Dict, Optional, List
from .models import UserSession, BookMetadata, UserStats
from datetime import timedelta


# ─── In-Memory Stores ─────────────────────────────────────────────────

# Key: "{user_id}:{book_id}" → UserSession
_sessions: Dict[str, UserSession] = {}

# Key: user_id → UserStats
_user_stats: Dict[str, UserStats] = {}

# Key: book_id → BookMetadata
_books: Dict[str, BookMetadata] = {}


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
    now = datetime.utcnow()
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
    
    return new_session


def _add_badge(stats: UserStats, badge_name: str):
    if badge_name not in stats.badges:
        stats.badges.append(badge_name)
        print(f"[BookBot] Achievement Unlocked: {badge_name}!")


# ─── Book Metadata Management ─────────────────────────────────────────

def store_book_metadata(book_id: str, title: str, author: str, total_pages: int) -> BookMetadata:
    """Store metadata about an ingested book."""
    metadata = BookMetadata(
        book_id=book_id,
        title=title,
        author=author,
        total_pages=total_pages
    )
    _books[book_id] = metadata
    return metadata


def get_book_metadata(book_id: str) -> Optional[BookMetadata]:
    """Retrieve metadata for a book."""
    return _books.get(book_id)


def list_books() -> List[BookMetadata]:
    """List all ingested books."""
    return list(_books.values())

# ─── State Persistence ────────────────────────────────────────────────

import json
import os

PERSISTENCE_FILE = os.path.join(os.path.dirname(__file__), '..', 'bookbot_state.json')

def save_state_to_disk():
    """Serialize the current in-memory state to a JSON file."""
    print("\n[BookBot] Persisting state to disk...")
    try:
        state = {
            "sessions": {k: v.dict() for k, v in _sessions.items()},
            "user_stats": {k: v.dict() for k, v in _user_stats.items()},
            "books": {k: v.dict() for k, v in _books.items()},
        }
        with open(PERSISTENCE_FILE, 'w') as f:
            json.dump(state, f, indent=2, default=str) # default=str for datetime
        print(f"[BookBot] Successfully saved state for {_books.__len__()} books to {PERSISTENCE_FILE}")
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
