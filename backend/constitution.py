"""Load the character constitution / layered lore system prompt."""

from __future__ import annotations

from backend.services.prompt import build_system_prompt


def load_constitution() -> str:
    """Return the static system stack (core lore + personality + behavior + safety)."""

    return build_system_prompt()
