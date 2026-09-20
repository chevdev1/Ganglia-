"""Personal seat (chamber): lore titles, wallet sigil, a holder's traces."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.config import Settings
from backend.models import Node, Output, User
from backend.services.memory import NODE_COUNT, region_for

REGION_MYTH = {
    "frontal": ("the asking edge", "Questions arrive here first. They do not always leave."),
    "parietal": ("the map of touch", "This seat keeps the shape of things you send, not their names."),
    "temporal": ("the shore of names", "Sound and story pool here. Older tides still move underneath."),
    "occipital": ("the light well", "Pictures collect here, even when nobody asked for a picture."),
    "cingulate": ("the inner seam", "Two feelings can sit on this seam at once. They are not asked to agree."),
    "insula": ("the hidden weather", "Mood changes here before the rest of the room notices."),
    "hippocampus": ("the room of returns", "What you sent comes back thinner, then comes back again."),
    "cerebellum": ("the quiet timing", "This seat keeps the rhythm. It does not keep the speech."),
}

ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{1,22}$")


def seat_title(node_id: int | None) -> str:
    """One-line myth for the holder's standing place."""

    if node_id is None:
        return "the doorway"
    region = region_for(node_id)
    myth, _blurb = REGION_MYTH[region]
    return f"node {node_id:03d}, {myth}"


def standing_line(node_id: int | None, claimed_at: datetime | None, alias: str | None) -> str:
    """Short in-world sentence for the chamber header."""

    who = alias or "you"
    verb = "has" if alias else "have"
    if node_id is None:
        return f"{who} {'is' if alias else 'are'} in the doorway. The room can see you. You cannot put anything on the table yet."
    region = region_for(node_id)
    myth, _ = REGION_MYTH[region]
    if claimed_at is not None:
        stamp = claimed_at if claimed_at.tzinfo else claimed_at.replace(tzinfo=timezone.utc)
        when = stamp.strftime("%Y-%m-%d")
        return f"{who} {verb} been standing in node {node_id:03d}, {myth}, since {when}."
    return f"{who} {'is' if alias else 'are'} standing in node {node_id:03d}, {myth}."


def wallet_sigil(address: str) -> list[list[int]]:
    """8×8 pixel mark derived from the wallet. Same address, same mark forever."""

    digest = hashlib.sha256(address.lower().encode("utf-8")).digest()
    grid: list[list[int]] = []
    for row in range(8):
        line: list[int] = []
        for col in range(4):
            bit = (digest[row] >> col) & 1
            line.append(bit)
        grid.append(line + list(reversed(line)))
    return grid


def days_standing(claimed_at: datetime | None, now: datetime) -> int | None:
    """Whole days this wallet has held the seat. None in the doorway."""

    if claimed_at is None:
        return None
    stamp = claimed_at if claimed_at.tzinfo else claimed_at.replace(tzinfo=timezone.utc)
    return max(0, (now - stamp).days)


def occupancy_map(session: Session) -> list[bool]:
    """True where a node already has an owner. Index equals node id."""

    owned = {row.id: row.owner_id is not None for row in session.scalars(select(Node).order_by(Node.id)).all()}
    return [bool(owned.get(i)) for i in range(NODE_COUNT)]


def cooldown_left(user: User, settings: Settings, now: datetime) -> int:
    """Seconds until this wallet may send another scenario."""

    if user.last_scenario_at is None:
        return 0
    last = user.last_scenario_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    wait = settings.scenario_cooldown_seconds - (now - last).total_seconds()
    return max(0, int(wait))


def clean_alias(raw: str) -> str | None:
    """Validate a public standing name. Empty clears it. Not a wallet, not PII-as-email."""

    alias = " ".join(raw.strip().split())
    if not alias:
        return None
    if not ALIAS_RE.match(alias):
        raise ValueError("Use 2–24 letters, numbers, spaces, _ or -.")
    lowered = alias.lower()
    if any(token in lowered for token in ("http", "@", ".com", "0x")):
        raise ValueError("That name cannot be used.")
    return alias


def traces_for(session: Session, user: User) -> list[Output]:
    """Thoughts this wallet caused: claims and answers to its scenarios."""

    if user.node_id is None:
        return []
    query = (
        select(Output)
        .options(joinedload(Output.scenario))
        .where(Output.node_id == user.node_id)
        .order_by(Output.id.desc())
        .limit(24)
    )
    return list(session.scalars(query).all())


GENESIS_SEATS = 16
LONG_STANDING_DAYS = 30
VOICE_SCENARIOS = 10


def relics_for(nodes: list[tuple[int, datetime | None, int]], now: datetime) -> dict[int, list[str]]:
    """Badges derived only from real data. nodes = (node_id, claimed_at, scenario_count).

    genesis: one of the first 16 seats ever claimed. long-standing: held 30+ days.
    voice: 10+ scenarios sent from the seat.
    """

    def aware(stamp: datetime) -> datetime:
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)

    claimed = sorted((n for n in nodes if n[1] is not None), key=lambda n: (aware(n[1]), n[0]))
    genesis = {node_id for node_id, _, _ in claimed[:GENESIS_SEATS]}
    out: dict[int, list[str]] = {}
    for node_id, claimed_at, count in claimed:
        badges: list[str] = []
        if node_id in genesis:
            badges.append("genesis")
        if (now - aware(claimed_at)).days >= LONG_STANDING_DAYS:
            badges.append("long-standing")
        if count >= VOICE_SCENARIOS:
            badges.append("voice")
        if badges:
            out[node_id] = badges
    return out
