"""Shared-memory helpers and thought persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.models import MemoryState, Node, Output, Scenario
from backend.schemas import ThoughtOut
from backend.services.neural import SignalFeatures
from backend.services.writer import ThoughtDraft

NODE_COUNT = 128
REGIONS = (
    "frontal",
    "parietal",
    "temporal",
    "occipital",
    "cingulate",
    "insula",
    "hippocampus",
    "cerebellum",
)


def region_for(node_id: int) -> str:
    """Map a node index onto the atlas-style region label used in the UI."""

    return REGIONS[node_id // 16]


def ensure_world(session: Session) -> MemoryState:
    """Create 128 free nodes and the singleton memory row if they are missing."""

    if session.get(Node, 0) is None:
        session.add_all(Node(id=i, scenario_count=0) for i in range(NODE_COUNT))
        session.flush()
    memory = session.get(MemoryState, 1)
    if memory is None:
        memory = MemoryState(
            id=1,
            summary_text="",
            curiosity=7,
            intensity=4,
            warmth=6,
            focus=5,
            restlessness=4,
            unresolved_thought="",
            cycle=0,
        )
        session.add(memory)
        session.flush()
    return memory


def recent_thought_texts(session: Session, limit: int = 24) -> list[str]:
    """Return the newest thought texts, oldest-of-window first, for the prompt."""

    rows = session.scalars(select(Output).order_by(Output.id.desc()).limit(limit)).all()
    return [row.text for row in reversed(rows)]


def recent_node_memory(session: Session, node_id: int | None, limit: int = 8) -> list[str]:
    """Return recent public traces from one node (scenarios + replies)."""

    if node_id is None:
        return []
    # selectinload + parent LIMIT: avoid joinedload row multiplication under LIMIT.
    scenarios = list(
        session.scalars(
            select(Scenario)
            .options(selectinload(Scenario.output))
            .where(Scenario.node_id == node_id)
            .order_by(Scenario.id.desc())
            .limit(limit)
        ).all()
    )
    lines: list[str] = []
    for row in reversed(scenarios):
        lines.append(f"scenario: {row.raw_text}")
        if row.output is not None and not row.output.hidden:
            lines.append(f"reply: {row.output.text}")
    return lines


def serialize_thought(row: Output) -> ThoughtOut:
    """Turn an output row into the public archive card."""

    scenario_text = row.scenario.raw_text if row.scenario is not None else None
    voice = row.voice_path or None
    return ThoughtOut(
        id=row.id,
        trigger=row.trigger_type,
        node_id=row.node_id,
        scenario=scenario_text,
        text=row.text,
        writer=row.writer,
        signal_source=row.signal_source,
        curiosity=row.curiosity,
        intensity=row.intensity,
        warmth=row.warmth,
        spike_count=row.spike_count,
        event_rate=row.event_rate,
        created_at=row.created_at,
        voice_url=voice or None,
        hidden=bool(row.hidden),
    )


def load_thoughts(session: Session, after_id: int = 0, limit: int = 40, *, include_hidden: bool = False) -> list[Output]:
    """Load thoughts for the feed. after_id=0 returns the newest page descending."""

    query = select(Output).options(joinedload(Output.scenario))
    if not include_hidden:
        query = query.where(Output.hidden.is_(False))
    if after_id:
        return list(session.scalars(query.where(Output.id > after_id).order_by(Output.id.asc())).all())
    return list(session.scalars(query.order_by(Output.id.desc()).limit(limit)).all())


def persist_thought(
    session: Session,
    *,
    trigger: str,
    node_id: int | None,
    scenario: Scenario | None,
    draft: ThoughtDraft,
    features: SignalFeatures,
) -> Output:
    """Save a thought, advance the cycle, and write the new summary."""

    memory = ensure_world(session)
    output = Output(
        trigger_type=trigger,
        scenario_id=scenario.id if scenario else None,
        node_id=node_id,
        text=draft.text,
        writer=draft.writer,
        signal_source=features.source,
        curiosity=draft.curiosity,
        intensity=draft.intensity,
        warmth=draft.warmth,
        spike_count=features.spike_count,
        event_rate=features.event_rate,
        amplitude=features.amplitude,
        active_channels=",".join(str(c) for c in features.active_channels),
        hidden=False,
        voice_path="",
        created_at=datetime.now(timezone.utc),
    )
    session.add(output)
    memory.summary_text = draft.summary
    memory.curiosity = draft.curiosity
    memory.intensity = draft.intensity
    memory.warmth = draft.warmth
    memory.focus = draft.focus
    memory.restlessness = draft.restlessness
    memory.unresolved_thought = draft.unresolved_thought
    memory.cycle += 1
    session.flush()
    return output


def short_address(address: str) -> str:
    """Display form used in the node panel."""

    if len(address) < 12:
        return address
    return f"{address[:6]}…{address[-4:]}"
