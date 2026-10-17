"""Canonical challenge terminology module.

Enforces that challenge titles and challenge names remain in canonical English
regardless of the user's selected language (including German), while allowing
supporting challenge UI copy (description, instructions, status, buttons)
to be localized.
"""

import re
from typing import Any

# Standard UI keys and phrases that should NEVER be treated as challenge titles
EXCLUDED_CHALLENGE_UI_KEYS = {
    "challenge",
    "challenges",
    "challenges:",
    "challenges...",
    "challenges hub",
    "challenges library",
    "challenge chat",
    "challenge chats",
    "challenge library",
    "challenge members",
    "challenge overview",
    "challenge details",
    "challenge progress",
    "challenge completed",
    "challenge finished",
    "challenge available",
    "challenge invite",
    "challenge guest invite",
    "active challenge",
    "active challenges",
    "completed challenge",
    "completed challenges",
    "ready to start challenge",
    "ready to start challenges",
    "your challenge",
    "your challenges",
    "community challenge",
    "community challenges",
    "limited challenges",
    "join challenge",
    "join this challenge",
    "leave challenge",
    "start challenge",
    "finish challenge",
    "failed to start challenge",
    "failed to start challenge.",
    "failed to load challenges",
    "failed to load challenges.",
    "failed to load challenge chat.",
    "failed to load challenge details.",
    "back to challenges",
    "fellow challengers",
    "what to do",
    "why it matters",
    "who is in it",
    "points",
    "pts",
    "joined",
    "days left",
    "day tracker",
    "challenge days",
}

CANONICAL_CHALLENGE_TITLES = [
    "21-Day Gold Beta",
    "21 Day Gold Beta",
    "21-Day Beta",
    "Morning Mobility Challenge",
    "Core Crusher",
    "30-Day Shred",
    "7-Day Reset",
    "Strength Foundation",
]

_CANONICAL_CHALLENGE_MAP = {
    title.strip().lower(): title.strip()
    for title in CANONICAL_CHALLENGE_TITLES
}

_CHALLENGE_TITLE_PATTERNS = [
    re.compile(r"^\d+[- ](?:day|week|month)\b", re.IGNORECASE),
    re.compile(r"\bgold beta\b", re.IGNORECASE),
]


def is_canonical_challenge_title(text: str) -> bool:
    """Returns True if text represents a challenge title that must stay in English."""
    cleaned = str(text or "").strip()
    if not cleaned or len(cleaned) < 2 or len(cleaned) > 200:
        return False

    lower = cleaned.lower()
    if lower in EXCLUDED_CHALLENGE_UI_KEYS:
        return False

    if lower in _CANONICAL_CHALLENGE_MAP:
        return True

    return any(pat.search(cleaned) for pat in _CHALLENGE_TITLE_PATTERNS)


def canonicalize_challenge_title(text: str) -> str:
    """Returns canonical English title with proper casing if known."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    lower = cleaned.lower()
    return _CANONICAL_CHALLENGE_MAP.get(lower, cleaned)
