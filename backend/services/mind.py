"""Single-writer mind: queued generation, claim thoughts, autonomous cycles."""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.db import session_factory
from backend.models import MemoryState, Node, Output, Scenario, User
from backend.services.memory import ensure_world, persist_thought, recent_node_memory, recent_thought_texts
from backend.services.neural import SoftwareNeuralProvider
from backend.services.tts import synthesize
from backend.services.writer import SoftwareWriter, ThoughtDraft, build_writer


async def _write(writer: SoftwareWriter, **kwargs: Any) -> ThoughtDraft:
    """Call sync or async writers with the same kwargs."""

    result = writer.write(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


class MindRuntime:
    """Process-wide queue so two scenarios cannot write memory at once."""

    def __init__(self, settings: Settings) -> None:
        """Build writer, neural adapter, and empty queue."""

        self.settings = settings
        self.writer = build_writer(settings)
        self.neural = SoftwareNeuralProvider()
        self.busy = False
        self.phase = "thinking"
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def writer_name(self) -> str:
        """Public label: model or software."""

        return getattr(self.writer, "name", "software")

    def start(self) -> None:
        """Launch the worker and optional autonomous ticker."""

        self._tasks.append(asyncio.create_task(self._worker(), name="ganglia-worker"))
        if self.settings.autonomous_enabled:
            self._tasks.append(asyncio.create_task(self._ticker(), name="ganglia-ticker"))

    async def stop(self) -> None:
        """Cancel background tasks on shutdown."""

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def enqueue(self, job: dict[str, Any]) -> None:
        """Queue a generation job for the background worker."""

        await self.queue.put(job)

    async def process(self, job: dict[str, Any]) -> None:
        """Write one thought now. Used by claim/scenario so the archive updates before the response."""

        async with self._lock:
            self.busy = True
            self.phase = str(job.get("phase") or "writing")
            try:
                await self._run(job)
            except Exception:
                raise
            finally:
                self.busy = False
                self.phase = "thinking"

    async def _worker(self) -> None:
        """Serialise autonomous writes through one loop."""

        while True:
            job = await self.queue.get()
            try:
                await self.process(job)
            except Exception:
                pass
            finally:
                self.queue.task_done()

    async def _ticker(self) -> None:
        """Enqueue an autonomous thought when the mind has been quiet."""

        interval = max(15, self.settings.autonomous_seconds)
        while True:
            await asyncio.sleep(interval)
            if self.busy or not self.queue.empty():
                continue
            if not self.settings.openai_api_key.strip() and not self.settings.allow_software_writer:
                continue
            factory = session_factory()
            with factory() as session:
                last = session.scalar(select(Output).order_by(Output.id.desc()).limit(1))
                if last is not None:
                    age = (datetime.now(timezone.utc) - last.created_at.replace(tzinfo=timezone.utc)).total_seconds()
                    if age < interval:
                        continue
            await self.enqueue({"type": "autonomous", "phase": "thinking"})

    async def _run(self, job: dict[str, Any]) -> None:
        """Open a private session and persist one thought."""

        factory = session_factory()
        with factory() as session:
            ensure_world(session)
            kind = job["type"]
            if kind == "scenario":
                output = await self._scenario(session, int(job["scenario_id"]))
            elif kind == "claim":
                output = await self._claim(session, int(job["node_id"]))
            else:
                output = await self._autonomous(session)
            if output is not None:
                await self._attach_voice(output)
            session.commit()

    async def _attach_voice(self, output: Output) -> None:
        """Generate and cache spoken audio for a saved thought."""

        if not self.settings.tts_enabled:
            return
        path = await synthesize(output.id, output.text, self.settings.tts_voice)
        if path:
            output.voice_path = path

    async def _scenario(self, session: Session, scenario_id: int) -> Output | None:
        """Write a reply to a stored scenario."""

        scenario = session.get(Scenario, scenario_id)
        if scenario is None or scenario.output is not None:
            return None
        memory = session.get(MemoryState, 1)
        assert memory is not None
        features = self.neural.observe(f"scenario:{scenario.id}:{scenario.raw_text}")
        draft = await _write(
            self.writer,
            trigger="scenario",
            scenario=scenario.raw_text,
            node_id=scenario.node_id,
            summary=memory.summary_text,
            recent=recent_thought_texts(session),
            node_memory=recent_node_memory(session, scenario.node_id),
            curiosity=memory.curiosity,
            intensity=memory.intensity,
            warmth=memory.warmth,
            focus=memory.focus,
            restlessness=memory.restlessness,
            unresolved_thought=memory.unresolved_thought or "",
            features=features,
        )
        return persist_thought(
            session,
            trigger="scenario",
            node_id=scenario.node_id,
            scenario=scenario,
            draft=draft,
            features=features,
        )

    async def _claim(self, session: Session, node_id: int) -> Output:
        """Announce a newly occupied seat."""

        memory = session.get(MemoryState, 1)
        assert memory is not None
        features = self.neural.observe(f"claim:{node_id}:{memory.cycle}")
        draft = await _write(
            self.writer,
            trigger="claim",
            scenario=None,
            node_id=node_id,
            summary=memory.summary_text,
            recent=recent_thought_texts(session),
            node_memory=recent_node_memory(session, node_id),
            curiosity=memory.curiosity,
            intensity=memory.intensity,
            warmth=memory.warmth,
            focus=memory.focus,
            restlessness=memory.restlessness,
            unresolved_thought=memory.unresolved_thought or "",
            features=features,
        )
        return persist_thought(session, trigger="claim", node_id=node_id, scenario=None, draft=draft, features=features)

    async def _autonomous(self, session: Session) -> Output:
        """Continue the monologue without a new user scenario."""

        memory = session.get(MemoryState, 1)
        assert memory is not None
        last_scenario = session.scalar(select(Scenario).order_by(Scenario.id.desc()).limit(1))
        features = self.neural.observe(f"auto:{memory.cycle}")
        draft = await _write(
            self.writer,
            trigger="autonomous",
            scenario=last_scenario.raw_text if last_scenario else None,
            node_id=last_scenario.node_id if last_scenario else None,
            summary=memory.summary_text,
            recent=recent_thought_texts(session),
            node_memory=recent_node_memory(session, last_scenario.node_id if last_scenario else None),
            curiosity=memory.curiosity,
            intensity=memory.intensity,
            warmth=memory.warmth,
            focus=memory.focus,
            restlessness=memory.restlessness,
            unresolved_thought=memory.unresolved_thought or "",
            features=features,
        )
        return persist_thought(session, trigger="autonomous", node_id=None, scenario=None, draft=draft, features=features)


def seed_genesis(session: Session, runtime: MindRuntime) -> None:
    """If the archive is empty, speak once so the feed is not a blank room."""

    ensure_world(session)
    count = session.scalar(select(func.count()).select_from(Output)) or 0
    if count:
        return
    memory = session.get(MemoryState, 1)
    assert memory is not None
    features = runtime.neural.observe("genesis")
    writer = SoftwareWriter()
    draft = writer.write(
        trigger="autonomous",
        scenario=None,
        node_id=None,
        summary="",
        recent=[],
        curiosity=memory.curiosity,
        intensity=memory.intensity,
        warmth=memory.warmth,
        focus=memory.focus,
        restlessness=memory.restlessness,
        unresolved_thought=memory.unresolved_thought or "",
        features=features,
    )
    draft.text = (
        "i am here. 128 seats on a map that is not a body. my words are written by software. "
        "if you hold a node, put something on the table. everyone will hear it."
    )
    draft.summary = "Genesis. Ganglia woke in the shared room. No nodes claimed yet."
    draft.unresolved_thought = "what will the first node put on the table"
    persist_thought(session, trigger="autonomous", node_id=None, scenario=None, draft=draft, features=features)


def claim_node(session: Session, user: User, node_id: int) -> Node:
    """Take a free node. One owner per node, one node per user."""

    ensure_world(session)
    if node_id < 0 or node_id > 127:
        raise ValueError("Node does not exist.")
    if user.node_id is not None:
        raise ValueError("You already hold a node.")
    now = datetime.now(timezone.utc)
    result = session.execute(
        update(Node)
        .where(Node.id == node_id, Node.owner_id.is_(None))
        .values(owner_id=user.id, claimed_at=now)
    )
    if result.rowcount != 1:
        raise ValueError("Already claimed.")
    user.node_id = node_id
    session.flush()
    node = session.get(Node, node_id)
    assert node is not None
    return node
