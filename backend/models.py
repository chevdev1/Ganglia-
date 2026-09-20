"""Database models for users, nodes, scenarios, thoughts, and shared memory."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for Ganglia tables."""


class User(Base):
    """A visitor identity. One claimed node at most."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(String(42), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    node_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_scenario_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alias: Mapped[str | None] = mapped_column(String(24), unique=True, nullable=True)

    scenarios: Mapped[list[Scenario]] = relationship(back_populates="author")


class LoginNonce(Base):
    """One-time wallet-login nonce. Deleted after a successful signature."""

    __tablename__ = "login_nonces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(String(42), index=True)
    nonce: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Node(Base):
    """One of 128 seats. Ownership is stored here; the user row mirrors it."""

    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scenario_count: Mapped[int] = mapped_column(Integer, default=0)

    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])


class Scenario(Base):
    """A public message from a node holder."""

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    raw_text: Mapped[str] = mapped_column(String(280))
    moderation_status: Mapped[str] = mapped_column(String(16), default="approved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author: Mapped[User] = relationship(back_populates="scenarios")
    output: Mapped[Output | None] = relationship(back_populates="scenario", uselist=False)


class Output(Base):
    """A public thought: reply, claim notice, or autonomous monologue."""

    __tablename__ = "outputs"
    __table_args__ = (UniqueConstraint("scenario_id", name="uq_output_scenario"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger_type: Mapped[str] = mapped_column(String(16), index=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id"), nullable=True)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    writer: Mapped[str] = mapped_column(String(16))
    signal_source: Mapped[str] = mapped_column(String(16), default="software")
    curiosity: Mapped[int] = mapped_column(Integer)
    intensity: Mapped[int] = mapped_column(Integer)
    warmth: Mapped[int] = mapped_column(Integer)
    spike_count: Mapped[int] = mapped_column(Integer, default=0)
    event_rate: Mapped[float] = mapped_column(Float, default=0.0)
    amplitude: Mapped[float] = mapped_column(Float, default=0.0)
    active_channels: Mapped[str] = mapped_column(String(64), default="")
    hidden: Mapped[bool] = mapped_column(default=False)
    voice_path: Mapped[str] = mapped_column(String(255), default="")
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    scenario: Mapped[Scenario | None] = relationship(back_populates="output")


class MemoryState(Base):
    """Singleton shared memory and character meters."""

    __tablename__ = "memory_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    summary_text: Mapped[str] = mapped_column(Text, default="")
    curiosity: Mapped[int] = mapped_column(Integer, default=7)
    intensity: Mapped[int] = mapped_column(Integer, default=4)
    warmth: Mapped[int] = mapped_column(Integer, default=6)
    focus: Mapped[int] = mapped_column(Integer, default=5)
    restlessness: Mapped[int] = mapped_column(Integer, default=4)
    unresolved_thought: Mapped[str] = mapped_column(Text, default="")
    cycle: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Purchase(Base):
    """A verified on-chain node purchase. tx_hash is unique so a payment can't be replayed."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tx_hash: Mapped[str] = mapped_column(String(66), unique=True, index=True)
    address: Mapped[str] = mapped_column(String(42), index=True)
    node_id: Mapped[int] = mapped_column(Integer)
    chain_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
