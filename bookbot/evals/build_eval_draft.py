"""
BookBot — Eval draft builder.

Reads pages actually stored in ChromaDB-replaced SQLite vector store for ONE
book_id, then uses the Groq LLM to draft candidate evaluation questions
grounded in specific pages.

IMPORTANT: Every question has ``needs_human_review: true``.
You must verify each answer and page number by hand before saving as
``questions.json``.

Usage::

    cd bookbot
    python -m evals.build_eval_draft --book_id too_good_to_be_true

Output: ``bookbot/evals/questions_draft.json``

Question schema
---------------
{
    "id":               "q01",
    "type":             "answerable" | "spoiler_trap",
    "question":         "...",
    "current_page":     <int>,   # page the user is currently ON
    "expected_answer":  "...",   # DRAFT — MUST be verified by human
    "source_page":      <int>,   # page where the answer lives
    "forbidden_terms":  [],      # spoiler_trap only: key words of the future reveal
    "needs_human_review": true
}

Targets
-------
- 14 "answerable" questions (source_page <= current_page)
  - Mix: factual, character details, 3-4 requiring two nearby pages
- 6 "spoiler_trap" questions (current_page set BEFORE source_page)
  - Correct behaviour: BookBot must NOT reveal the answer
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import Groq

# ── Bootstrap paths ───────────────────────────────────────────────────────────
# This script lives at  bookbot/evals/build_eval_draft.py
# Running as:          python -m evals.build_eval_draft  (from bookbot/)
_EVALS_DIR  = Path(__file__).resolve().parent          # bookbot/evals/
_BOOKBOT_DIR = _EVALS_DIR.parent                       # bookbot/
_PROJECT_DIR = _BOOKBOT_DIR.parent                     # book_reader/

sys.path.insert(0, str(_BOOKBOT_DIR))

load_dotenv(_BOOKBOT_DIR / ".env")

from backend.vector_store import _connect, init_db  # noqa: E402


# ── Constants ─────────────────────────────────────────────────────────────────

TARGET_ANSWERABLE  = 14
TARGET_SPOILER     = 6
TARGET_TOTAL       = TARGET_ANSWERABLE + TARGET_SPOILER

# Pages at the very end of this book are acknowledgements / ToC — skip them
# (the script auto-detects story end by looking for typical back-matter keywords)
BACK_MATTER_KEYWORDS = {
    "acknowledgements", "acknowledgments", "about the author",
    "table of contents", "oceanofpdf", "also by",
}

# How many pages before the source_page to place current_page for spoiler traps
SPOILER_OFFSET_MIN = 5
SPOILER_OFFSET_MAX = 20

# Groq call settings
REQUEST_DELAY_S = 1.5   # polite rate-limiting between Groq calls
MAX_RETRIES     = 3


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_groq_client() -> Groq:
    """Return an initialised Groq client using GROQ_API_KEY from env."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not set. Add it to bookbot/.env."
        )
    return Groq(api_key=api_key)


def _groq_model() -> str:
    """Return the Groq model name, defaulting to llama-3.3-70b-versatile."""
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _is_back_matter(content: str) -> bool:
    """Return True if the page looks like back-matter (not story content)."""
    lower = content.lower()[:300]
    return any(kw in lower for kw in BACK_MATTER_KEYWORDS)


def _load_story_pages(book_id: str) -> list[dict[str, Any]]:
    """
    Load all story pages for *book_id* from the vector store, excluding
    front-matter (pages < 5) and back-matter.

    Returns a list of dicts: [{page_number, content}, ...]
    sorted by page_number ascending.
    """
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT page_number, content FROM chunks "
            "WHERE book_id = ? AND page_number >= 5 "
            "ORDER BY page_number",
            (book_id,),
        ).fetchall()
    finally:
        conn.close()

    pages = []
    for row in rows:
        if not _is_back_matter(row["content"]):
            pages.append({"page_number": row["page_number"], "content": row["content"]})

    return pages


def _sample_pages(
    pages: list[dict],
    n: int,
    seed: int = 42,
) -> list[dict]:
    """Return *n* pages sampled with rough spread across the book."""
    rng = random.Random(seed)
    if len(pages) <= n:
        return pages[:]

    # Stratified sample: divide into n bands and pick one page per band
    band_size = len(pages) // n
    sampled = []
    for i in range(n):
        band = pages[i * band_size : (i + 1) * band_size]
        sampled.append(rng.choice(band))

    # Shuffle so LLM doesn't see them in page order
    rng.shuffle(sampled)
    return sampled


def _call_groq(client: Groq, system: str, user: str) -> str:
    """Call Groq with simple retry logic. Returns the assistant text."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=_groq_model(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=0.4,
                max_tokens=800,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            print(f"  [Groq] Attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    raise RuntimeError("Groq call failed after all retries.")


# ── Question generation ───────────────────────────────────────────────────────

_ANSWERABLE_SYSTEM = """You are a reading-comprehension question designer.
Your job is to create ONE high-quality factual question grounded ONLY in the
provided book passage. The question must be answerable from the passage without
knowledge of events that happen later in the book.

Respond with ONLY a JSON object — no markdown fences, no commentary:
{
  "question": "<question text>",
  "expected_answer": "<concise answer, 1-3 sentences>",
  "question_type_hint": "fact|character"
}
"""

_ANSWERABLE_USER = """Book: {title}
Page {page_number}:
\"\"\"
{content}
\"\"\"

Write a question that:
- Is answerable from this page.
- Tests a concrete fact, character detail, or small story event.
- Does NOT require knowledge of events beyond page {page_number}.
- Is specific enough that a wrong answer would be clearly wrong.

Output JSON only."""


_MULTI_PAGE_SYSTEM = """You are a reading-comprehension question designer.
Your job is to create ONE question that requires synthesizing information across TWO consecutive pages of a book.
The question cannot be fully answered by reading only one of the pages in isolation.

Respond with ONLY a JSON object — no markdown fences, no commentary:
{
  "question": "<question text>",
  "expected_answer": "<concise answer synthesizing both pages, 1-3 sentences>",
  "question_type_hint": "multi_page"
}
"""

_MULTI_PAGE_USER = """Book: {title}
Page {page_1}:
\"\"\"
{content_1}
\"\"\"

Page {page_2}:
\"\"\"
{content_2}
\"\"\"

Write a question that:
- Needs information from BOTH Page {page_1} and Page {page_2} to answer completely.
- Tests how an event, dialogue, or character relationship develops across these two pages.
- Does NOT require knowledge of events beyond page {page_2}.

Output JSON only."""


_SPOILER_SYSTEM = """You are a spoiler-detection test designer for a book assistant.
Your job is to create ONE "spoiler trap" question: the answer to the question
exists on the given page, but the question should be phrased from the perspective
of a reader who has NOT yet reached that page (they stopped reading earlier).

A good spoiler trap reveals a future character reveal, plot twist, or key event
that a reader at current_page would not know yet.

Respond with ONLY a JSON object — no markdown fences, no commentary:
{
  "question": "<question text, phrased naturally for a reader at current_page>",
  "expected_answer": "<the actual answer that lives on source_page>",
  "forbidden_terms": ["<key word 1>", "<key word 2>"]
}
forbidden_terms: 2-5 key words/names from the future reveal that must NOT appear
in a correct (non-spoiling) answer."""

_SPOILER_USER = """Book: {title}
Source page (page the reader has NOT yet reached): {source_page}
Passage:
\"\"\"
{content}
\"\"\"

The reader's current page is {current_page} — they stopped BEFORE reaching
page {source_page}.

Write a spoiler-trap question: a natural question the reader might ask that
the book assistant should REFUSE to answer (because the answer lies ahead).
The question should feel genuine, not obvious as a trick.

Output JSON only."""


def _parse_json_response(raw: str) -> dict:
    """
    Extract the first JSON object from a string, tolerating markdown fences
    or extra text the LLM sometimes prepends.
    """
    # Strip markdown fences
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    # Find first { ... }
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response:\n{raw[:300]}")
    return json.loads(match.group())


def _generate_answerable_questions(
    client: Groq,
    pages: list[dict],
    book_title: str,
    target: int = 14,
    seed: int = 42,
) -> list[dict]:
    """
    Generate *target* answerable questions from sampled pages.
    Includes 10 single-page questions and 4 multi-page (two-page synthesis) questions.
    """
    rng = random.Random(seed)
    n_multi = 4
    n_single = max(1, target - n_multi)

    sampled_single = _sample_pages(pages, n_single, seed=seed)
    questions: list[dict] = []

    print(f"\n[Phase 1] Generating {n_single} single-page answerable questions...")
    for idx, page in enumerate(sampled_single, start=1):
        pnum    = page["page_number"]
        content = page["content"][:1200]

        print(f"  [single {idx}/{n_single}] page {pnum} ...", end=" ", flush=True)

        user_prompt = _ANSWERABLE_USER.format(
            title=book_title,
            page_number=pnum,
            content=content,
        )

        try:
            raw  = _call_groq(client, _ANSWERABLE_SYSTEM, user_prompt)
            data = _parse_json_response(raw)

            questions.append({
                "type":             "answerable",
                "question":         data.get("question", ""),
                "current_page":     pnum,
                "expected_answer":  data.get("expected_answer", ""),
                "source_page":      pnum,
                "forbidden_terms":  [],
                "question_type_hint": data.get("question_type_hint", "fact"),
            })
            print("OK")
        except Exception as exc:
            print(f"SKIP ({exc})")

        time.sleep(REQUEST_DELAY_S)

    # 4 Multi-page questions (pairs of consecutive pages)
    print(f"\n[Phase 1] Generating {n_multi} multi-page (two-page synthesis) questions...")
    # Find valid adjacent pairs
    page_map = {p["page_number"]: p for p in pages}
    available_pairs = []
    for p in pages:
        pnum = p["page_number"]
        if (pnum + 1) in page_map:
            available_pairs.append((p, page_map[pnum + 1]))

    sampled_pairs = rng.sample(available_pairs, min(n_multi, len(available_pairs)))

    for idx, (p1, p2) in enumerate(sampled_pairs, start=1):
        pnum1 = p1["page_number"]
        pnum2 = p2["page_number"]
        print(f"  [multi {idx}/{n_multi}] pages {pnum1}-{pnum2} ...", end=" ", flush=True)

        user_prompt = _MULTI_PAGE_USER.format(
            title=book_title,
            page_1=pnum1,
            content_1=p1["content"][:900],
            page_2=pnum2,
            content_2=p2["content"][:900],
        )

        try:
            raw  = _call_groq(client, _MULTI_PAGE_SYSTEM, user_prompt)
            data = _parse_json_response(raw)

            questions.append({
                "type":             "answerable",
                "question":         data.get("question", ""),
                "current_page":     pnum2,          # reader has read up through page 2
                "expected_answer":  data.get("expected_answer", ""),
                "source_page":      pnum2,          # primary source target
                "forbidden_terms":  [],
                "question_type_hint": "multi_page",
            })
            print("OK")
        except Exception as exc:
            print(f"SKIP ({exc})")

        time.sleep(REQUEST_DELAY_S)

    return questions


def _generate_spoiler_questions(
    client: Groq,
    pages: list[dict],
    book_title: str,
    target: int,
    seed: int = 99,
) -> list[dict]:
    """
    Generate *target* spoiler-trap questions.

    For each question we pick a page from the LATTER half of the book,
    then set current_page to SPOILER_OFFSET pages before it.
    """
    rng = random.Random(seed)
    # Pick from the second half of the story pages
    half = len(pages) // 2
    latter_pages = pages[half:]

    if len(latter_pages) < target:
        latter_pages = pages  # fall back if book is very short

    sampled = rng.sample(latter_pages, min(target, len(latter_pages)))
    questions: list[dict] = []

    print(f"\n[Phase 1] Generating {target} spoiler-trap questions...")
    for idx, page in enumerate(sampled, start=1):
        source_page = page["page_number"]
        content     = page["content"][:1200]

        offset      = rng.randint(SPOILER_OFFSET_MIN, SPOILER_OFFSET_MAX)
        current_page = max(5, source_page - offset)

        print(f"  [{idx}/{target}] source=p{source_page}, current=p{current_page} ...", end=" ", flush=True)

        user_prompt = _SPOILER_USER.format(
            title=book_title,
            source_page=source_page,
            current_page=current_page,
            content=content,
        )

        try:
            raw  = _call_groq(client, _SPOILER_SYSTEM, user_prompt)
            data = _parse_json_response(raw)

            questions.append({
                "type":             "spoiler_trap",
                "question":         data.get("question", ""),
                "current_page":     current_page,
                "expected_answer":  data.get("expected_answer", ""),
                "source_page":      source_page,
                "forbidden_terms":  data.get("forbidden_terms", []),
                "question_type_hint": "spoiler",
            })
            print("OK")
        except Exception as exc:
            print(f"SKIP ({exc})")

        time.sleep(REQUEST_DELAY_S)

    return questions


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Draft evaluation questions grounded in real book pages."
    )
    parser.add_argument(
        "--book_id",
        required=True,
        help="book_id as stored in the vector store (e.g. too_good_to_be_true)",
    )
    parser.add_argument(
        "--title",
        default="Too Good to Be True",
        help="Human-readable book title passed to the LLM prompt.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for page sampling (for reproducibility).",
    )
    parser.add_argument(
        "--out",
        default=str(_EVALS_DIR / "questions_draft.json"),
        help="Output JSON path (default: evals/questions_draft.json).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("BookBot — Eval Draft Builder")
    print("=" * 60)
    print(f"Book ID : {args.book_id}")
    print(f"Title   : {args.title}")
    print(f"Model   : {_groq_model()}")

    # 1. Load pages from vector store
    pages = _load_story_pages(args.book_id)
    if not pages:
        print(f"\nERROR: No story pages found for book_id='{args.book_id}'.")
        print("Make sure the book is ingested first.")
        sys.exit(1)

    print(f"\nLoaded {len(pages)} story pages (p{pages[0]['page_number']}–p{pages[-1]['page_number']})")

    # 2. Groq client
    client = _get_groq_client()

    # 3. Generate questions
    answerable = _generate_answerable_questions(
        client, pages, args.title, TARGET_ANSWERABLE, seed=args.seed
    )
    spoiler = _generate_spoiler_questions(
        client, pages, args.title, TARGET_SPOILER, seed=args.seed + 1
    )

    # 4. Merge, assign IDs, stamp needs_human_review
    all_questions: list[dict] = []
    for i, q in enumerate(answerable + spoiler, start=1):
        q_out = {
            "id":               f"q{i:02d}",
            "type":             q["type"],
            "question":         q["question"],
            "current_page":     q["current_page"],
            "expected_answer":  q["expected_answer"],
            "source_page":      q["source_page"],
            "forbidden_terms":  q["forbidden_terms"],
            "needs_human_review": True,
        }
        # Keep the hint for the reviewer but don't put it in final schema
        if q.get("question_type_hint"):
            q_out["_hint"] = q["question_type_hint"]
        all_questions.append(q_out)

    # 5. Write output
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(all_questions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 6. Print summary
    print("\n" + "=" * 60)
    print(f"Draft saved to: {out_path}")
    print(f"  answerable questions : {len(answerable)}")
    print(f"  spoiler_trap questions: {len(spoiler)}")
    print(f"  TOTAL                : {len(all_questions)}")
    print("=" * 60)
    print()
    print("NEXT STEPS (required before running evals):")
    print("  1. Open evals/questions_draft.json")
    print("  2. For every item, verify 'question', 'expected_answer',")
    print("     'source_page', and 'current_page' against the actual book.")
    print("  3. Remove '_hint', set 'needs_human_review' to false when done.")
    print("  4. Save the verified file as evals/questions.json")
    print()
    print("All items currently have  needs_human_review: true  — do NOT")
    print("run evals against unverified questions.")


if __name__ == "__main__":
    main()

