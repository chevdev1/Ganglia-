"""Tests for public-archive moderation."""

from __future__ import annotations

from backend.services.moderation import moderate_scenario


def test_accepts_ordinary_scenario() -> None:
    """A short public prompt is allowed."""

    result = moderate_scenario("What does the sea sound like if you have never heard it?")
    assert result.ok is True


def test_rejects_email() -> None:
    """Email addresses must not enter the public archive."""

    result = moderate_scenario("write to me at ada@example.com please")
    assert result.ok is False
    assert "private" in result.reason.lower()


def test_rejects_empty() -> None:
    """Whitespace-only input is rejected."""

    result = moderate_scenario("   ")
    assert result.ok is False
