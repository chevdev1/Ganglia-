"""Tamper-evident archive: every thought stores the hash of the one before it.

Changing, removing or reordering any past thought breaks every later hash, and
/api/verify recomputes the whole chain from scratch. `hidden` is deliberately not
part of the hash, so a steward hiding a thought does not break the chain.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Output

GENESIS = "0" * 64


def _epoch(row: Output) -> int:
    stamp = row.created_at
    return int((stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)).timestamp())


def link_hash(prev: str, row: Output) -> str:
    """sha256 over the previous hash plus the row's immutable public content."""

    body = json.dumps(
        [row.id, row.trigger_type, row.node_id, row.scenario_id, row.text, _epoch(row)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"{prev}\n{body}".encode("utf-8")).hexdigest()


def seal(session: Session, row: Output) -> None:
    """Chain a freshly flushed row onto the latest earlier one."""

    prev = session.scalar(select(Output.hash).where(Output.id < row.id).order_by(Output.id.desc()).limit(1))
    row.prev_hash = prev or GENESIS
    row.hash = link_hash(row.prev_hash, row)
    session.flush()


def backfill(session: Session) -> int:
    """Chain any rows that predate the ledger (or were inserted without sealing)."""

    prev = GENESIS
    sealed = 0
    for row in session.scalars(select(Output).order_by(Output.id.asc())):
        if row.hash is None:
            row.prev_hash = prev
            row.hash = link_hash(prev, row)
            sealed += 1
        prev = row.hash
    if sealed:
        session.flush()
    return sealed


def verify(session: Session) -> dict[str, object]:
    """Recompute the full chain. broken_at is the first thought that does not match."""

    prev = GENESIS
    count = 0
    for row in session.scalars(select(Output).order_by(Output.id.asc())):
        expected = link_hash(prev, row)
        if row.hash != expected or row.prev_hash != prev:
            return {"ok": False, "count": count, "head": prev, "broken_at": row.id}
        prev = row.hash
        count += 1
    return {"ok": True, "count": count, "head": prev, "broken_at": None}
