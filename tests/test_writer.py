"""Tests for the software writer grounding and state-update loop helpers."""

from __future__ import annotations

from backend.services.neural import SoftwareNeuralProvider
from backend.services.prompt import build_context_pack, build_system_prompt, lore_sections
from backend.services.writer import SoftwareWriter, apply_state_update, nudge_from_text


def test_software_reply_mentions_scenario() -> None:
    """The local writer must keep a visible trace of the user's scenario."""

    features = SoftwareNeuralProvider().observe("test")
    draft = SoftwareWriter().write(
        trigger="scenario",
        scenario="Remember this: my grandmother hummed while she cooked.",
        node_id=7,
        summary="",
        recent=[],
        curiosity=7,
        intensity=4,
        warmth=6,
        features=features,
    )
    assert "grandmother" in draft.text.lower() or "hummed" in draft.text.lower()
    assert draft.writer == "software"
    assert "table" in draft.text.lower() or "room" in draft.text.lower() or "node" in draft.text.lower()
    assert draft.focus >= 1
    assert draft.restlessness >= 1


def test_nudge_raises_curiosity_on_question() -> None:
    """Questions should lift curiosity rather than rolling a random meter."""

    curiosity, _intensity, _warmth, focus, _rest = nudge_from_text("What is behind the door?", 5, 5, 5, 5, 4)
    assert curiosity >= 6
    assert focus >= 6


def test_lore_layers_load() -> None:
    """Layered lore must parse into the static system stack without runtime placeholders."""

    from backend.services.prompt import clear_lore_cache

    clear_lore_cache()
    sections = lore_sections()
    assert "IDENTITY" in sections or "CORE LORE" in sections
    system = build_system_prompt()
    assert "CORE LORE" in system
    assert "PERSONALITY" in system
    assert "SAFETY" in system
    assert "{{SHARED_MEMORY_SUMMARY}}" not in system


def test_context_pack_keeps_runtime_out_of_system() -> None:
    """Runtime memory belongs in the context pack, not the static constitution."""

    pack = build_context_pack(
        trigger="scenario",
        summary="cities keep coming up",
        recent=["quiet again", "maps again"],
        node_memory=["scenario: remember the harbour"],
        node_id=3,
        curiosity=7,
        intensity=4,
        warmth=6,
        focus=5,
        restlessness=4,
        unresolved_thought="why harbours",
        signal_source="software",
        user_input="What about the harbour light?",
    )
    assert "SHARED MEMORY SUMMARY" in pack
    assert "RECENT SHARED ENTRIES" in pack
    assert "NODE MEMORY" in pack
    assert "CURRENT USER INPUT" in pack
    assert "harbour" in pack


def test_apply_state_update_keeps_durable_memory() -> None:
    """Important memory candidates append; tiny deltas stay clamped."""

    summary, c, i, w, f, r, unresolved = apply_state_update(
        summary="old weather",
        curiosity=5,
        intensity=5,
        warmth=5,
        focus=5,
        restlessness=5,
        unresolved_thought="",
        update={
            "memory_candidate": "someone keeps asking about harbours",
            "memory_importance": 0.8,
            "state_delta": {"curiosity": 1, "intensity": 0, "warmth": -1, "focus": 2, "restlessness": 9},
            "unresolved_thought": "why harbours return",
        },
    )
    assert "harbours" in summary
    assert c == 6
    assert w == 4
    assert f == 7
    assert r == 7  # delta clamped to +2
    assert "harbours" in unresolved
