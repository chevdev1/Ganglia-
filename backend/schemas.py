"""Pydantic schemas for the public API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConnectIn(BaseModel):
    """Signed wallet login. Address alone is not enough."""

    address: str
    signature: str


class LocalKeyIn(BaseModel):
    """Browser-held secp256k1 secret used when no injected wallet is present."""

    secret: str = Field(min_length=64, max_length=66)


class NonceOut(BaseModel):
    """Challenge for personal_sign."""

    address: str
    nonce: str
    message: str


class MeOut(BaseModel):
    """The caller's identity and claimed node, if any."""

    address: str
    node_id: int | None
    token: str | None = None
    alias: str | None = None


class NodeOut(BaseModel):
    """One seat on the 128-node map."""

    id: int
    owner: str | None
    alias: str | None = None
    scenarios: int
    region: str
    relics: list[str] = []


class ThoughtOut(BaseModel):
    """A public thought in the archive."""

    id: int
    trigger: str
    node_id: int | None
    scenario: str | None
    text: str
    writer: str
    signal_source: str
    curiosity: int
    intensity: int
    warmth: int
    spike_count: int
    event_rate: float
    created_at: datetime
    voice_url: str | None = None
    hidden: bool = False


class CharacterStateOut(BaseModel):
    """Live meters shown under the brain."""

    curiosity: int
    intensity: int
    warmth: int
    focus: int = 5
    restlessness: int = 4
    unresolved_thought: str = ""


class StateOut(BaseModel):
    """Bootstrap payload for the landing page."""

    me: MeOut | None
    nodes: list[NodeOut]
    thoughts: list[ThoughtOut]
    state: CharacterStateOut
    cycle: int
    busy: bool
    status: str
    signal_source: str
    writer: str
    summary: str
    model_ready: bool = False


class ScenarioIn(BaseModel):
    """A node holder's public scenario."""

    text: str = Field(min_length=1, max_length=280)


class ClaimOut(BaseModel):
    """Result of taking a free node."""

    node_id: int
    address: str


class AliasIn(BaseModel):
    """Public standing name shown on the map. Empty string clears it."""

    alias: str = Field(default="", max_length=24)


class TraceOut(BaseModel):
    """One thread this seat left in the shared room."""

    id: int
    trigger: str
    scenario: str | None
    text: str
    created_at: datetime
    curiosity: int
    intensity: int
    warmth: int
    voice_url: str | None = None


class ChamberOut(BaseModel):
    """Personal cabinet: the holder's standing place in the mind."""

    address: str
    alias: str | None
    node_id: int | None
    region: str | None
    title: str
    blurb: str
    standing_line: str
    claimed_at: datetime | None
    days_standing: int | None
    scenario_count: int
    cooldown_seconds: int
    sigil: list[list[int]]
    traces: list[TraceOut]
    occupancy: list[bool]
    occupied_count: int
    cycle: int
    summary: str
    weather: CharacterStateOut
    model_ready: bool
    writer: str


class AdminOverviewOut(BaseModel):
    """Steward dashboard snapshot for ops."""

    cycle: int
    writer: str
    model_ready: bool
    signal_source: str
    busy: bool
    status: str
    nodes_total: int
    nodes_claimed: int
    nodes_free: int
    users: int
    scenarios: int
    thoughts_total: int
    thoughts_public: int
    thoughts_hidden: int
    summary: str
    weather: CharacterStateOut
    unresolved_thought: str = ""
    recent_scenarios: list[str] = []
    occupancy: list[bool] = []
