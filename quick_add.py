"""
quick_add.py — Deterministic mock parser for the Quick Add Task feature.

Parses a free-text task description and extracts:
  • title      — a short, cleaned title (NOT a copy of the full description)
  • priority   — "high" | "medium" | "low"
  • due_date_hint — matched/resolved date phrase (lowercase) or None

This parser uses zero network calls and zero API keys.
It is structured around a role-based LLM prompt so that the same
interface can later be wired to a real language model.

Changelog (latency/bug-fix pass):
  - All keyword/phrase matching now uses word boundaries (\\b) so a keyword
    can no longer match mid-word (e.g. "urgent" no longer matches inside
    "insurgent").
  - Priority keywords are now symmetric: high-priority phrasing
    ("high priority", "important", "critical") is recognized just like
    low-priority phrasing already was.
  - Due-date detection now also recognizes ISO dates (2024-12-31),
    slash dates (12/31 or 12/31/2024), and relative "in N day(s)/week(s)"
    phrases — resolved to an actual calendar date — in addition to the
    original fixed phrase list (today, tomorrow, next <weekday>, etc).
  - Title generation now produces a genuinely short title (first clause,
    capped at a handful of words) instead of returning nearly the entire
    original text with a couple of words removed. The full original text
    is still preserved separately as the task's `description`.
"""
from __future__ import annotations
import re
import os
from datetime import date, timedelta
from typing import TypedDict, Optional


# ── Result type ───────────────────────────────────────────────────────────────

class ParsedTask(TypedDict):
    title: str
    priority: str          # "high" | "medium" | "low"
    due_date_hint: Optional[str]


# ── Keyword tables ────────────────────────────────────────────────────────────
# Ordered longest/most-specific phrase first within each group so that, e.g.,
# "low priority" is matched (and stripped) as a whole phrase rather than
# leaving a stray "priority" behind.

_HIGH_KEYWORDS: list[str] = [
    "high priority", "urgent", "asap", "important", "critical",
]
_LOW_KEYWORDS: list[str] = [
    "low priority", "whenever", "no rush", "no hurry", "someday",
]
_ALL_PRIORITY_KEYWORDS: list[str] = _HIGH_KEYWORDS + _LOW_KEYWORDS

# Fixed date phrases checked in strict priority order:
#   today → tomorrow → next week → next <weekday> → bare <weekday>
_DATE_PHRASES: list[str] = [
    "today",
    "tomorrow",
    "next week",
    "next monday",
    "next tuesday",
    "next wednesday",
    "next thursday",
    "next friday",
    "next saturday",
    "next sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

# ── Numeric / relative date patterns ──────────────────────────────────────────
# Checked BEFORE the fixed phrase list, since they're more specific.
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
_SLASH_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_RELATIVE_DAYS_RE = re.compile(r"\bin\s+(\d+)\s+(day|days|week|weeks)\b", re.IGNORECASE)


def _word_boundary_pattern(phrase: str) -> re.Pattern:
    """Compile a case-insensitive, word-boundary-safe pattern for `phrase`."""
    return re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)


def _contains_phrase(text: str, phrase: str) -> bool:
    return _word_boundary_pattern(phrase).search(text) is not None


def _strip_phrase(text: str, phrase: str) -> str:
    return _word_boundary_pattern(phrase).sub("", text)


# ── Core parser ───────────────────────────────────────────────────────────────

def parse_quick_add(description: str) -> ParsedTask:
    """
    Parse a free-text task description and return a ParsedTask dict.

    This function mirrors the structure of a role-based LLM prompt:

        messages = [
            {
                "role": "system",
                "content": (
                    "Parse the task description and return title, priority, "
                    "and due_date_hint according to the required rules."
                )
            },
            {
                "role": "user",
                "content": description
            }
        ]

    The deterministic rules below replace what a language model would infer,
    giving 100% reproducible results without any API key or network call.
    """
    working_text = description.lower()

    # ── A. Priority detection (word-boundary safe) ────────────────────────────
    if any(_contains_phrase(working_text, kw) for kw in _HIGH_KEYWORDS):
        priority = "high"
    elif any(_contains_phrase(working_text, kw) for kw in _LOW_KEYWORDS):
        priority = "low"
    else:
        priority = "medium"

    # ── B. Due-date detection (most specific match wins) ──────────────────────
    due_date_hint: Optional[str] = None
    matched_date_span: Optional[str] = None  # exact substring to strip from title

    iso_match = _ISO_DATE_RE.search(description)
    slash_match = _SLASH_DATE_RE.search(description) if not iso_match else None
    relative_match = (
        _RELATIVE_DAYS_RE.search(description) if not (iso_match or slash_match) else None
    )

    if iso_match:
        due_date_hint = iso_match.group(0)
        matched_date_span = iso_match.group(0)
    elif slash_match:
        due_date_hint = slash_match.group(0)
        matched_date_span = slash_match.group(0)
    elif relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2).lower()
        days = amount * 7 if unit.startswith("week") else amount
        resolved = date.today() + timedelta(days=days)
        due_date_hint = resolved.isoformat()
        matched_date_span = relative_match.group(0)
    else:
        for phrase in _DATE_PHRASES:
            if _contains_phrase(working_text, phrase):
                due_date_hint = phrase
                matched_date_span = phrase
                break

    # ── C. Title generation ────────────────────────────────────────────────────
    # Start from the original-cased description and strip out the
    # priority/date phrases that were detected, then reduce that to a
    # short title. The FULL original text is preserved separately by the
    # caller as the task's `description` — the title should not duplicate it.
    cleaned = description
    for kw in _ALL_PRIORITY_KEYWORDS:
        cleaned = _strip_phrase(cleaned, kw)
    if matched_date_span:
        cleaned = _strip_phrase(cleaned, matched_date_span)

    # Collapse whitespace and stray leading/trailing punctuation left behind
    # by removed phrases (e.g. "Write the report , it's" stays intact in the
    # middle, but leading/trailing ", " or extra spaces are trimmed).
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    cleaned = re.sub(r"^[,;\s]+|[,;\s]+$", "", cleaned)
    # A dangling preposition can be left at the very end once a trailing
    # date phrase is removed (e.g. "Submit the report by" after "by
    # 2026-09-01" loses its date). Only trim it if it's the last word.
    cleaned = re.sub(r"\s+(?:by|on|at|in)$", "", cleaned, flags=re.IGNORECASE).strip()

    title = _shorten_title(cleaned)

    if not title:
        title = "Untitled task"

    return ParsedTask(title=title, priority=priority, due_date_hint=due_date_hint)


def _shorten_title(cleaned: str, max_words: int = 8) -> str:
    """
    Reduce `cleaned` text to a short title:
      1. Cut at the first sentence-ending punctuation (., ;, newline) if one
         appears after the first few characters, so multi-clause input
         doesn't all end up in the title.
      2. Cap at `max_words` words, appending an ellipsis if truncated.
    Short input passes through unchanged (nothing to shorten).
    """
    text = cleaned
    for punct in (".", ";", "\n"):
        idx = text.find(punct)
        if idx > 3:
            text = text[:idx]
            break

    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]) + "…"

    return text.strip()


# ── Optional real-LLM shim ────────────────────────────────────────────────────
# If USE_REAL_LLM=true is set in the environment AND an API key is available,
# a real language model can be called here.  The mock is always the fallback.

def _use_real_llm() -> bool:
    return os.getenv("USE_REAL_LLM", "false").strip().lower() == "true"


def parse_task_description(description: str) -> ParsedTask:
    """
    Public entry point.  Uses the real LLM only when USE_REAL_LLM=true AND
    an API key is present; otherwise falls back to the deterministic mock.
    """
    if _use_real_llm():
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key:
            # Real LLM path — not implemented by default; falls through to mock.
            pass  # pragma: no cover

    # Default: deterministic mock (always works, no network, no key)
    return parse_quick_add(description)