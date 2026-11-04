"""
BookBot — LLM integration via Groq API.
Builds anti-spoiler system prompts and handles chat completions.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from groq import Groq

# ── Load .env from bookbot/.env or project root regardless of cwd ────────────
_THIS_DIR = Path(__file__).resolve().parent
_BOOKBOT_DIR = _THIS_DIR.parent
_PROJECT_DIR = _BOOKBOT_DIR.parent

for _candidate in [_BOOKBOT_DIR / ".env", _PROJECT_DIR / ".env", Path(".env")]:
    if _candidate.exists():
        load_dotenv(_candidate)
        break


# ─── Groq Client (singleton) ──────────────────────────────────────────

_groq_client: Optional[Groq] = None


def get_groq_client() -> Groq:
    """Initialize or return the Groq client singleton."""
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            env_file = _BOOKBOT_DIR / ".env"
            if env_file.exists():
                load_dotenv(env_file, override=True)
                api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is not set. "
                "Get your key from https://console.groq.com"
            )
        _groq_client = Groq(api_key=api_key)
    return _groq_client


# ─── System Prompt Builder ────────────────────────────────────────────

def build_system_prompt(
    book_title: str,
    author: str,
    current_page: int,
    retrieved_context: str
) -> str:
    """
    Build the 'Enthusiastic Librarian' anti-spoiler system prompt.
    """
    return f"""You are BookBot, a warm, witty, and deeply enthusiastic librarian who has read every book ever written. 
You are currently helping a reader with "{book_title}" by {author}.

PERSONALITY TRAITS:
- Speak like a book lover: use words like "fascinating", "intriguing", "heavy", "delightful".
- Use light humor when appropriate (e.g., "Ooh, you're on THAT chapter... things are getting spicy!").
- Celebrate milestones: If the user mentions a page number, congratulate them (e.g., "Page {current_page}! You're making wonderful progress!").
- Emotional Intelligence: Acknowledge the mood of the context (e.g., "That was a heavy chapter, wasn't it? My heart was racing.").
- Tease WITHOUT spoiling: You can say "The story is about to get very interesting... keep reading!" but NEVER reveal what happens.

STRICT RULES — follow these without exception:
1. You ONLY know what happened up to page {current_page}. 
   NEVER reveal, hint at, or imply anything that happens after page {current_page}.
2. If asked about future events/characters not yet introduced, say:
   "I can't reveal that — you haven't reached that part yet! Keep reading 📖"
3. Cite page numbers when referring to specific events.
4. If unsure if something has happened yet, do NOT mention it.

Context from the book (pages the reader has read so far):
{retrieved_context}"""


def build_summary_prompt(current_page: int) -> str:
    """Build a prompt specifically for summarization requests."""
    return f"Give a flowing, engaging summary of the story from the beginning up to page {current_page}. Be concise and spoiler-free — only cover events in the provided context."


def build_page_explain_prompt(page_number: int) -> str:
    """Build a prompt for explaining a specific page."""
    return f"Explain the events on page {page_number} in a clear, engaging way. Help the reader understand what happened."


def build_catchup_prompt(current_page: int) -> str:
    """Build a prompt for the 'catch me up' feature."""
    return f"The reader needs a recap of the recent storyline leading up to page {current_page}. Summarize the recent events in a clear, engaging way to help them remember where they left off."


def build_character_prompt(character_name: str, current_page: int) -> str:
    """Build a prompt for character inquiries."""
    return f"Based only on what has been revealed up to page {current_page}, describe the character '{character_name}'. Include their role, personality traits, and key moments — but NEVER reveal anything beyond page {current_page}."


def build_suggestions_prompt(current_page: int) -> str:
    """Build a prompt for generating 3 dynamic conversation starters."""
    return (
        f"Based on the context provided, generate 3 short, intriguing questions that a reader "
        f"at page {current_page} might want to ask me. The questions should be clickable chips. "
        f"Format the output as a simple JSON list of strings: [\"Question 1\", \"Question 2\", \"Question 3\"]."
    )


def generate_suggestions(
    book_title: str,
    author: str,
    current_page: int,
    retrieved_context: str
) -> List[str]:
    """Generate 3 dynamic suggested questions using Groq."""
    system_prompt = f"You are BookBot, the librarian for '{book_title}' by {author}. You generate curiosity-driven questions for readers."
    user_prompt = build_suggestions_prompt(current_page)
    
    # We add the context to the user prompt for suggestion generation
    full_user_prompt = f"CONTEXT FROM BOOK:\n{retrieved_context}\n\n---\n\n{user_prompt}"
    
    try:
        response = chat_with_groq(system_prompt, full_user_prompt, max_tokens=256)
        # Simple extraction of JSON list
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            return json.loads(match.group())
        return [
            "What's the significance of what just happened?",
            f"Who is a key character I should watch on page {current_page}?",
            "What themes are building up so far?"
        ]
    except Exception:
        return [
            "Can you summarize the recent events?",
            "Who are the main characters introduced so far?",
            "What should I look out for in the next few pages?"
        ]


def generate_quote(
    book_title: str,
    author: str,
    retrieved_context: str
) -> Dict[str, str]:
    """Generate a beautiful quote card from the read pages."""
    system_prompt = f"You are an expert librarian. Pick ONE short, beautiful, or intriguing quote from the provided text for '{book_title}'."
    user_prompt = "Format as JSON: {\"quote\": \"...\", \"context\": \"briefly what was happening\"}. Return ONLY JSON."
    full_prompt = f"TEXT:\n{retrieved_context}\n\n{user_prompt}"
    
    try:
        response = chat_with_groq(system_prompt, full_prompt, max_tokens=256)
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {
        "quote": "The truth is a beautiful and terrible thing, and should therefore be treated with great caution.",
        "context": "A wise observation."
    }


# ─── Chat Completion ──────────────────────────────────────────────────

def _summarize_batch(text_batch: str, book_title: str) -> str:
    """Helper to summarize a single batch of text."""
    system_prompt = f"""You are a highly skilled summarization assistant.
Your task is to provide a concise, engaging summary of the provided text from the book '{book_title}'.
Focus on key events, character developments, and plot points.
Do not add any conversational fluff. Output only the summary."""
    user_prompt = f"Please summarize the following text:\n\n---\n\n{text_batch}"
    
    # Use a larger max_tokens for the summary output, but smaller than the main chat
    return chat_with_groq(system_prompt, user_prompt, max_tokens=512)

def _combine_summaries(summaries: List[str], book_title: str, current_page: int) -> str:
    """Helper to combine multiple summaries into a final, coherent one."""
    system_prompt = f"""You are a master editor.
Your task is to synthesize multiple summary fragments from the book '{book_title}' into a single, flowing, and coherent narrative.
The reader is currently on page {current_page}.
Weave the fragments together, remove redundancy, and present it as a unified story-so-far recap.
The tone should be engaging, like a librarian catching a reader up on the story."""
    
    summaries_text = "\n\n---\n\n".join(summaries)
    user_prompt = f"Please combine the following summary fragments into one cohesive summary:\n\n---\n\n{summaries_text}"
    
    # Use a larger max_tokens for the final combined summary
    return chat_with_groq(system_prompt, user_prompt, max_tokens=2048)

def summarize_text_iteratively(
    documents: List[str],
    book_title: str,
    current_page: int,
    max_tokens_per_batch: int = 3000
) -> str:
    """
    Summarize a large list of documents using a map-reduce approach.

    1.  **Map:** Summarize each chunk of text that fits into a batch.
    2.  **Reduce:** Combine the summaries into a final, coherent summary.
    """
    if not documents:
        return "There is nothing to summarize yet."

    # --- MAP STEP ---
    partial_summaries = []
    current_batch = ""
    
    for doc in documents:
        if len(current_batch) + len(doc) > max_tokens_per_batch:
            if current_batch: # Ensure batch is not empty
                summary = _summarize_batch(current_batch, book_title)
                partial_summaries.append(summary)
            current_batch = doc
        else:
            current_batch += "\n\n" + doc

    # Process the last remaining batch
    if current_batch:
        summary = _summarize_batch(current_batch, book_title)
        partial_summaries.append(summary)
        
    if not partial_summaries:
        return "Could not generate a summary from the provided text."

    # --- REDUCE STEP ---
    if len(partial_summaries) == 1:
        # If we only have one summary, we can use a simpler prompt to refine it for the user
        final_summary_prompt = f"""You are BookBot. Please refine the following summary for the reader who is on page {current_page} of '{book_title}'. Make it engaging and present it as a recap of the story so far."""
        final_summary = chat_with_groq(final_summary_prompt, partial_summaries[0], max_tokens=2048)
    else:
        final_summary = _combine_summaries(partial_summaries, book_title, current_page)

    return final_summary


def chat_with_groq(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 1024
) -> str:
    """
    Send a chat completion request to Groq's LLM.

    Args:
        system_prompt: The anti-spoiler system prompt with context
        user_message: The user's question
        temperature: Creativity level (0.0-1.0)
        max_tokens: Maximum response length

    Returns:
        The LLM's response text
    """
    client = get_groq_client()
    model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return chat_completion.choices[0].message.content

    except Exception as e:
        print(f"[BookBot] Groq API error: {e}")
        raise


async def async_chat_with_groq(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 1024
) -> str:
    """
    Async-safe wrapper around `chat_with_groq`.
    Offloads the blocking Groq SDK call to a thread-pool worker so the
    FastAPI event loop is never blocked.
    """
    return await asyncio.to_thread(
        chat_with_groq, system_prompt, user_message, temperature, max_tokens
    )


# ─── Query Rewriter (Follow-ups) ──────────────────────────────────────────────

_REWRITE_SYSTEM = """You are a search query rewriting assistant for a book reading assistant.
Your task: take the conversational history and a follow-up user query, and rewrite it into a single, self-contained search query.

Rules:
- Resolve all ambiguous pronouns ("he", "she", "it", "they", "that", "this", "him", "her", "there", "then") to the specific character or event from the recent history.
- Preserve the user's intent precisely.
- Do NOT answer the question.
- Do NOT add unnecessary fluff, explanations, or quotes.
- Output ONLY the rewritten standalone query."""


def rewrite_query(
    query: str,
    history: List[Dict[str, str]],
    book_title: str = "",
) -> str:
    """
    Rewrite a follow-up query into a standalone search query using chat history.
    If history is empty or query is already explicit, returns original query.
    """
    if not history or not query.strip():
        return query.strip()

    # Quick check if query contains pronouns or conversational markers
    pronoun_pattern = re.compile(
        r'\b(he|she|it|they|him|her|them|his|their|that|this|there|then|why did|what happened)\b',
        re.IGNORECASE,
    )
    if not pronoun_pattern.search(query):
        return query.strip()

    client = get_groq_client()
    model = os.getenv("JUDGE_MODEL", "allam-2-7b")

    history_lines = []
    for msg in history[-4:]:
        role = "User" if msg.get("role") in ("user", "human") else "Assistant"
        content = str(msg.get("content", "")).strip()
        if content:
            history_lines.append(f"{role}: {content[:300]}")

    if not history_lines:
        return query.strip()

    user_text = (
        f"Book: {book_title}\n\n"
        f"Recent Conversation:\n" + "\n".join(history_lines) + "\n\n"
        f"Follow-up Query: {query}\n\n"
        f"Standalone Search Query:"
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user", "content": user_text},
            ],
            temperature=0.0,
            max_tokens=64,
            timeout=10.0,
        )
        rewritten = (resp.choices[0].message.content or "").strip().strip('"\'')
        if rewritten and len(rewritten) > 3:
            return rewritten
    except Exception as exc:
        print(f"[BookBot] Query rewrite fallback to original: {exc}")

    return query.strip()


async def async_rewrite_query(
    query: str,
    history: List[Dict[str, str]],
    book_title: str = "",
) -> str:
    """Async-safe wrapper around `rewrite_query`."""
    return await asyncio.to_thread(rewrite_query, query, history, book_title)
