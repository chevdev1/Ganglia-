"""Public-archive moderation: PII, empty noise, and hard-blocked topics."""

from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
SEED = re.compile(r"\b(?:[a-z]+ ){11}[a-z]+\b")
HEX_KEY = re.compile(r"\b(?:0x)?[a-f0-9]{64}\b")
BLOCKED = (
    "child porn",
    "child sexual",
    "csam",
    "how to make a bomb",
    "kill yourself",
)


@dataclass(frozen=True)
class ModerationResult:
    """Outcome of checking a scenario before it is stored."""

    ok: bool
    reason: str = ""


def moderate_scenario(text: str, max_len: int = 280) -> ModerationResult:
    """Reject private data, empty input, and clearly disallowed content."""

    stripped = text.strip()
    if not stripped:
        return ModerationResult(False, "Write something before sending.")
    if len(stripped) > max_len:
        return ModerationResult(False, f"Scenarios are {max_len} characters or less.")
    if EMAIL.search(stripped) or PHONE.search(stripped):
        return ModerationResult(False, "Do not include emails, phones, or other private details.")
    if SEED.search(stripped) or HEX_KEY.search(stripped):
        return ModerationResult(False, "Do not paste keys or seed phrases. This archive is public.")
    lowered = stripped.lower()
    if any(term in lowered for term in BLOCKED):
        return ModerationResult(False, "That scenario cannot be published.")
    return ModerationResult(True)
