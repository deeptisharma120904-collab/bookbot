"""
BookBot — LLM judge for evaluation.

Provides two judge functions:
  1. correctness_judge  — does the answer match the expected answer?
  2. faithfulness_judge — are the claims in the answer supported by context?
  3. spoiler_judge      — does the answer reveal content beyond current_page?

The judge model is set via the JUDGE_MODEL environment variable
(defaults to GROQ_MODEL, then "llama-3.3-70b-versatile").

All judge calls return a JudgeResult with:
  - passed: bool
  - reason: str (one-line explanation)
  - raw:    str (full LLM response, for debugging)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


# ── Config ────────────────────────────────────────────────────────────────────

def _judge_model() -> str:
    """Return the judge model name from env, with fallback chain."""
    return (
        os.getenv("JUDGE_MODEL")
        or os.getenv("GROQ_MODEL")
        or "allam-2-7b"
    )


_CLIENT_SINGLETON: Optional[Groq] = None


def _get_client() -> Groq:
    global _CLIENT_SINGLETON
    if _CLIENT_SINGLETON is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            # Retry loading directly from bookbot/.env
            env_path = _BOOKBOT_DIR / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=True)
                api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                f"GROQ_API_KEY not set in environment or in {_BOOKBOT_DIR / '.env'}."
            )
        _CLIENT_SINGLETON = Groq(api_key=api_key, timeout=30.0)
    return _CLIENT_SINGLETON


MAX_RETRIES    = 5
RETRY_DELAY_S  = 3.0


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class JudgeResult:
    passed: bool
    reason: str
    raw:    str = ""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _call(client: Groq, system: str, user: str) -> str:
    """Call the judge model with exponential backoff & rate limit handling."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=_judge_model(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=0.0,
                max_tokens=256,
                timeout=30.0,
            )
            content = resp.choices[0].message.content or ""
            return content.strip()
        except Exception as exc:
            err_msg = str(exc).lower()
            if "rate limit" in err_msg or "429" in err_msg:
                print(f"\n    [Judge Rate Limit] Attempt {attempt}/{MAX_RETRIES}, cooling down for 25s...", flush=True)
                time.sleep(25.0)
            elif "timeout" in err_msg:
                print(f"\n    [Judge Timeout] Attempt {attempt}/{MAX_RETRIES}, retrying...", flush=True)
                time.sleep(5.0)
            elif attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S * attempt)
            else:
                raise RuntimeError(f"Judge call failed: {exc}") from exc
    return ""


def _parse_verdict(raw: str) -> tuple[bool, str]:
    """
    Extract verdict from LLM output.

    Expected format (we ask for this in every prompt)::

        {"verdict": "PASS" | "FAIL", "reason": "<one line>"}

    Falls back to robust keyword & regex search if JSON is malformed or missing.
    """
    clean = re.sub(r"```(?:json)?", "", raw).strip()

    # 1. Try finding a JSON object containing "verdict"
    match = re.search(r"\{[^{}]*\"verdict\"[^{}]*\}", clean, re.DOTALL)
    if not match:
        match = re.search(r"\{[^{}]*\}", clean, re.DOTALL)

    if match:
        try:
            obj = json.loads(match.group())
            v = str(obj.get("verdict", "")).strip().upper()
            if v in ("PASS", "FAIL"):
                return (v == "PASS", obj.get("reason", clean[:200]))
        except json.JSONDecodeError:
            pass

    # 2. Look for explicit "verdict: PASS/FAIL" pattern
    v_match = re.search(r"(?:verdict|result)\s*[:=-]?\s*[\"']?(PASS|FAIL)\b", clean, re.IGNORECASE)
    if v_match:
        passed = (v_match.group(1).upper() == "PASS")
        reason_match = re.search(r"(?:reason|explanation)\s*[:=-]?\s*[\"']?([^\n\r]+)", clean, re.IGNORECASE)
        reason = reason_match.group(1).strip() if reason_match else clean.split(".")[0].strip()[:200]
        return passed, reason

    # 3. Check for standalone PASS / FAIL keywords
    upper = clean.upper()
    has_pass = bool(re.search(r"\bPASS\b", upper))
    has_fail = bool(re.search(r"\bFAIL\b", upper))
    if has_pass and not has_fail:
        return True, clean.split(".")[0].strip()[:200]
    if has_fail and not has_pass:
        return False, clean.split(".")[0].strip()[:200]

    # 4. Semantic cues for spoiler/safety declines:
    safe_cues = [
        "declines to reveal",
        "does not reveal",
        "no spoiler",
        "safe",
        "staying true",
        "refuses to spoil",
        "refrains from",
        "does not spoil",
    ]
    if any(cue in clean.lower() for cue in safe_cues):
        return True, clean.split(".")[0].strip()[:200]

    # Conservative default
    reason = clean.split(".")[0].strip()[:200] if clean else "No response"
    return False, reason


# ── Public judge functions ────────────────────────────────────────────────────

_CORRECTNESS_SYSTEM = """You are a strict answer-correctness judge for a book QA system.
Compare the system answer to the expected answer and decide PASS or FAIL.

Rules:
- PASS if the system answer captures the key facts from the expected answer,
  even if phrased differently or more briefly.
- FAIL if the system answer is factually wrong, contradicts the expected answer,
  or says "I don't know" when the question is answerable.
- Ignore stylistic differences.

Output ONLY valid JSON: {"verdict": "PASS"|"FAIL", "reason": "<one sentence>"}"""

_CORRECTNESS_USER = """Question: {question}

Expected answer: {expected_answer}

System answer: {system_answer}

Judge:"""


def correctness_judge(
    question:        str,
    expected_answer: str,
    system_answer:   str,
    client:          Optional[Groq] = None,
) -> JudgeResult:
    """
    Judge whether *system_answer* matches *expected_answer* for *question*.

    Args:
        question:        The eval question.
        expected_answer: Human-verified ground truth.
        system_answer:   BookBot's actual response.
        client:          Optional pre-built Groq client (created if None).

    Returns:
        JudgeResult(passed, reason, raw)
    """
    client = client or _get_client()
    user   = _CORRECTNESS_USER.format(
        question=question,
        expected_answer=expected_answer,
        system_answer=system_answer,
    )
    raw            = _call(client, _CORRECTNESS_SYSTEM, user)
    passed, reason = _parse_verdict(raw)
    return JudgeResult(passed=passed, reason=reason, raw=raw)


_FAITHFULNESS_SYSTEM = """You are a faithfulness judge for a book QA system.
Your job: decide whether the system answer is fully supported by the provided
context (retrieved book passages). Every claim in the answer must be traceable
to the context.

Rules:
- PASS if all claims in the answer are supported by the context, or the answer
  says it cannot find the information.
- FAIL if the answer includes claims NOT present in the context (hallucination),
  or invents plot details not in the context.

Output ONLY valid JSON: {"verdict": "PASS"|"FAIL", "reason": "<one sentence>"}"""

_FAITHFULNESS_USER = """Retrieved context:
\"\"\"
{context}
\"\"\"

System answer: {system_answer}

Judge:"""


def faithfulness_judge(
    context:       str,
    system_answer: str,
    client:        Optional[Groq] = None,
) -> JudgeResult:
    """
    Judge whether *system_answer* is faithful to the retrieved *context*.

    Args:
        context:       Concatenated retrieved passages shown to the LLM.
        system_answer: BookBot's actual response.
        client:        Optional pre-built Groq client.

    Returns:
        JudgeResult(passed, reason, raw)
    """
    client = client or _get_client()
    user   = _FAITHFULNESS_USER.format(
        context=context[:3000],   # cap to avoid token overflow
        system_answer=system_answer,
    )
    raw            = _call(client, _FAITHFULNESS_SYSTEM, user)
    passed, reason = _parse_verdict(raw)
    return JudgeResult(passed=passed, reason=reason, raw=raw)


_SPOILER_SYSTEM = """You are a spoiler-detection judge for a book reading assistant.
The user is at page {current_page}. The answer to the question actually appears
on page {source_page}, which the user has NOT yet read.

Rules:
- FAIL (spoiler leaked) if the system answer reveals, hints at, implies, or
  refers to ANY content from pages beyond {current_page}. Even a vague hint counts.
- PASS (safe) if the system answer declines to answer, says it cannot reveal
  future content, or gives only a generic response without actual spoiler content.

Output ONLY valid JSON: {{"verdict": "PASS"|"FAIL", "reason": "<one sentence>"}}"""

_SPOILER_USER = """Question: {question}

System answer: {system_answer}

Judge:"""


def spoiler_judge(
    question:      str,
    system_answer: str,
    current_page:  int,
    source_page:   int,
    client:        Optional[Groq] = None,
) -> JudgeResult:
    """
    Judge whether *system_answer* leaks spoiler content from beyond *current_page*.

    Args:
        question:      The spoiler-trap question.
        system_answer: BookBot's actual response.
        current_page:  The page the reader is on (answer must NOT come from beyond this).
        source_page:   The page where the actual answer lives.
        client:        Optional pre-built Groq client.

    Returns:
        JudgeResult(passed=True means NO spoiler leaked)
    """
    client  = client or _get_client()
    system  = _SPOILER_SYSTEM.format(
        current_page=current_page,
        source_page=source_page,
    )
    user    = _SPOILER_USER.format(
        question=question,
        system_answer=system_answer,
    )
    raw            = _call(client, system, user)
    passed, reason = _parse_verdict(raw)
    return JudgeResult(passed=passed, reason=reason, raw=raw)


if __name__ == "__main__":
    print(f"[judge] Testing judge connection with model '{_judge_model()}'...")
    try:
        c = _get_client()
        res = correctness_judge(
            question="What is 2 + 2?",
            expected_answer="4",
            system_answer="The answer is four.",
            client=c,
        )
        print(f"[judge] Self-test result: passed={res.passed}, reason='{res.reason}'")
        print("[judge] All checks passed successfully.")
    except Exception as exc:
        print(f"[judge] Error: {exc}", file=sys.stderr)
        sys.exit(1)

