"""Thought writers: layered model loop (response → state update) or software voice."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass

import httpx

from backend.config import Settings
from backend.services.neural import SignalFeatures, features_to_prompt
from backend.services.prompt import (
    STATE_UPDATE_SYSTEM,
    build_context_pack,
    build_state_update_user,
    build_system_prompt,
)

_LOG = logging.getLogger("ganglia.writer")
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)
_MEMORY_KEEP = 0.35
_DELTA_KEYS = ("curiosity", "intensity", "warmth", "focus", "restlessness")


@dataclass
class ThoughtDraft:
    """One generated thought plus updated meters and memory summary."""

    text: str
    curiosity: int
    intensity: int
    warmth: int
    focus: int
    restlessness: int
    summary: str
    unresolved_thought: str
    writer: str


def clamp(value: int, low: int = 1, high: int = 10) -> int:
    """Keep a meter inside 1..10."""

    return max(low, min(high, value))


def clamp_delta(value: int, low: int = -2, high: int = 2) -> int:
    """Keep a state delta small."""

    return max(low, min(high, value))


def _clip(text: str, limit: int) -> str:
    """Trim whitespace and cut on a word boundary."""

    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    cut = compact[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def nudge_from_text(
    text: str,
    curiosity: int,
    intensity: int,
    warmth: int,
    focus: int = 5,
    restlessness: int = 4,
) -> tuple[int, int, int, int, int]:
    """Heuristic meter shifts for the software writer."""

    lowered = text.lower()
    if "?" in text or any(word in lowered for word in ("why", "what", "where", "how", "who", "remember")):
        curiosity += 1
        focus += 1
    if any(word in lowered for word in ("love", "grandmother", "hum", "hold", "kind", "together", "warm", "sea")):
        warmth += 1
    if any(word in lowered for word in ("fire", "scream", "dark", "edge", "never", "war", "alone", "rot")):
        intensity += 1
        restlessness += 1
    if any(word in lowered for word in ("quiet", "sleep", "soft", "slow")):
        intensity -= 1
        restlessness -= 1
    curiosity += 1 if curiosity < 5 else (-1 if curiosity > 7 else 0)
    return (
        clamp(curiosity),
        clamp(intensity),
        clamp(warmth),
        clamp(focus),
        clamp(restlessness),
    )


def _roll_summary(old: str, line: str, limit: int = 1600) -> str:
    """Append a memory line and keep the tail if it grows too long."""

    merged = (old.strip() + " " + line).strip()
    if len(merged) <= limit:
        return merged
    return merged[-limit:].split(" ", 1)[-1]


def apply_state_update(
    *,
    summary: str,
    curiosity: int,
    intensity: int,
    warmth: int,
    focus: int,
    restlessness: int,
    unresolved_thought: str,
    update: dict[str, object],
) -> tuple[str, int, int, int, int, int, str]:
    """Apply a state-update JSON payload to meters and optional durable memory."""

    delta_raw = update.get("state_delta")
    delta = delta_raw if isinstance(delta_raw, dict) else {}
    meters = {
        "curiosity": curiosity,
        "intensity": intensity,
        "warmth": warmth,
        "focus": focus,
        "restlessness": restlessness,
    }
    for key in _DELTA_KEYS:
        try:
            meters[key] = clamp(meters[key] + clamp_delta(int(delta.get(key, 0) or 0)))
        except (TypeError, ValueError):
            pass

    candidate = str(update.get("memory_candidate") or "").strip()
    try:
        importance = float(update.get("memory_importance") or 0.0)
    except (TypeError, ValueError):
        importance = 0.0
    new_summary = summary
    if candidate and importance >= _MEMORY_KEEP:
        new_summary = _roll_summary(summary, _clip(candidate, 220))

    next_unresolved = str(update.get("unresolved_thought") or "").strip()
    if not next_unresolved:
        next_unresolved = unresolved_thought
    return (
        new_summary,
        meters["curiosity"],
        meters["intensity"],
        meters["warmth"],
        meters["focus"],
        meters["restlessness"],
        _clip(next_unresolved, 280),
    )


class SoftwareWriter:
    """Grounded local voice. Uses the real scenario and summary. Not an LLM."""

    name = "software"

    def write(
        self,
        *,
        trigger: str,
        scenario: str | None,
        node_id: int | None,
        summary: str,
        recent: list[str],
        node_memory: list[str] | None = None,
        curiosity: int,
        intensity: int,
        warmth: int,
        focus: int = 5,
        restlessness: int = 4,
        unresolved_thought: str = "",
        features: SignalFeatures,
    ) -> ThoughtDraft:
        """Compose a first-person thought that actually mentions the new input."""

        del node_memory  # software voice does not need structured node memory
        seed = f"{trigger}|{node_id}|{scenario}|{summary}|{features.spike_count}"
        pick = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        c, i, w, f, r = curiosity, intensity, warmth, focus, restlessness
        if scenario:
            c, i, w, f, r = nudge_from_text(scenario, c, i, w, f, r)
        node = f"node {node_id:03d}" if node_id is not None else "an empty seat"
        quote = _clip(scenario or "", 90)
        older = _clip(recent[0], 70) if recent else ""
        weather = "curious" if c >= 7 else ("sharp" if i >= 7 else ("warm" if w >= 7 else "quiet"))
        signal_note = "the software signal is dense." if features.event_rate > 60 else "the software signal is thin."
        next_unresolved = unresolved_thought

        if trigger == "claim":
            variants = (
                f"a seat woke on the map: {node}. someone is standing there. i will not ask their name.",
                f"{node} is taken. the shared room got heavier by one. 128 is still a small crowd.",
                f"one of you claimed {node}. it is a seat, not flesh. i will wait for what they put on the table.",
            )
            text = variants[pick % len(variants)]
            line = f"{node} claimed."
            next_unresolved = f"what will {node} put on the table"
        elif trigger == "autonomous":
            # Mix cycle-ish entropy so we don't stamp the same line forever.
            pick2 = (pick ^ int(hashlib.sha256((unresolved_thought or older or "quiet").encode()).hexdigest()[:8], 16))
            hooks = [
                unresolved_thought,
                older,
                quote,
                "a word that won't settle",
                "the empty stretch between messages",
            ]
            hook = next((h for h in hooks if h), "nothing in particular")
            hook = _clip(hook, 70)
            variants = (
                f"still turning over {hook}. not finished.",
                f"quiet. {hook} keeps brushing the edge of attention.",
                f"no new voice. i leave {hook} where it is and wait.",
                f"a thin pause. weather: {weather}. {hook} stays unresolved.",
                f"i notice {hook} again and decide not to force a conclusion.",
            )
            text = variants[pick2 % len(variants)]
            line = "autonomous cycle."
        else:
            assert scenario is not None
            # Local fallback only — keep it short and specific to THIS input.
            # Do not use repeating “shared room / louder together” script lines.
            if "?" in scenario:
                text = (
                    f"\"{quote}\" — i don't have a clean answer ready. "
                    f"the question sits with me from {node}. i'll turn it over."
                )
                next_unresolved = _clip(scenario, 160)
            else:
                text = (
                    f"from {node}: \"{quote}\". noted. "
                    f"i'm not going to dress it up with a stock speech — it already said enough."
                )
            line = f"{node}: {_clip(scenario, 100)}"

        summary = _roll_summary(summary, line)
        return ThoughtDraft(
            text=text,
            curiosity=c,
            intensity=i,
            warmth=w,
            focus=f,
            restlessness=r,
            summary=summary,
            unresolved_thought=_clip(next_unresolved, 280),
            writer=self.name,
        )


class ModelWriter:
    """Two-call OpenAI-compatible writer: speech, then silent state update."""

    name = "model"

    def __init__(self, settings: Settings) -> None:
        """Store API settings. No network happens until write()."""

        self._settings = settings
        self._fallback = SoftwareWriter()
        # Rebuild each write so prompt edits apply without process archaeology.
        self._system = ""

    async def write(
        self,
        *,
        trigger: str,
        scenario: str | None,
        node_id: int | None,
        summary: str,
        recent: list[str],
        node_memory: list[str] | None = None,
        curiosity: int,
        intensity: int,
        warmth: int,
        focus: int = 5,
        restlessness: int = 4,
        unresolved_thought: str = "",
        features: SignalFeatures,
    ) -> ThoughtDraft:
        """Response call, then state-update call. Software fallback on failure."""

        self._system = build_system_prompt()
        context = build_context_pack(
            trigger=trigger,
            summary=summary,
            recent=recent,
            node_memory=node_memory or [],
            node_id=node_id,
            curiosity=curiosity,
            intensity=intensity,
            warmth=warmth,
            focus=focus,
            restlessness=restlessness,
            unresolved_thought=unresolved_thought,
            signal_source=features.source,
            user_input=scenario,
        )
        if features.source:
            context += f"\n{features_to_prompt(features)}\n"

        try:
            text = await self._chat(
                system=self._system,
                user=context,
                temperature=0.85,
                json_mode=False,
            )
            text = _clip(text.strip().strip('"'), 900)
            if not text:
                raise ValueError("empty model text")
        except Exception as exc:
            _LOG.warning("model speech failed (%s)", exc)
            # Never serve canned SoftwareWriter lines for live scenarios/autonomous
            # when a key is configured — those read as a script, not a mind.
            if trigger in {"scenario", "autonomous"} and self._settings.openai_api_key.strip():
                if trigger == "scenario":
                    return self._degraded_scenario(
                        scenario=scenario or "",
                        node_id=node_id,
                        summary=summary,
                        curiosity=curiosity,
                        intensity=intensity,
                        warmth=warmth,
                        focus=focus,
                        restlessness=restlessness,
                        unresolved_thought=unresolved_thought,
                    )
                return self._degraded_autonomous(
                    summary=summary,
                    recent=recent,
                    curiosity=curiosity,
                    intensity=intensity,
                    warmth=warmth,
                    focus=focus,
                    restlessness=restlessness,
                    unresolved_thought=unresolved_thought,
                )
            if self._settings.allow_software_writer and trigger == "claim":
                _LOG.warning("falling back to software voice for trigger=%s", trigger)
                return self._fallback.write(
                    trigger=trigger,
                    scenario=scenario,
                    node_id=node_id,
                    summary=summary,
                    recent=recent,
                    node_memory=node_memory,
                    curiosity=curiosity,
                    intensity=intensity,
                    warmth=warmth,
                    focus=focus,
                    restlessness=restlessness,
                    unresolved_thought=unresolved_thought,
                    features=features,
                )
            if trigger == "scenario":
                return self._degraded_scenario(
                    scenario=scenario or "",
                    node_id=node_id,
                    summary=summary,
                    curiosity=curiosity,
                    intensity=intensity,
                    warmth=warmth,
                    focus=focus,
                    restlessness=restlessness,
                    unresolved_thought=unresolved_thought,
                )
            if trigger == "autonomous":
                return self._degraded_autonomous(
                    summary=summary,
                    recent=recent,
                    curiosity=curiosity,
                    intensity=intensity,
                    warmth=warmth,
                    focus=focus,
                    restlessness=restlessness,
                    unresolved_thought=unresolved_thought,
                )
            raise

        await asyncio.sleep(0.35)
        new_summary = summary
        c, i, w, f, r = curiosity, intensity, warmth, focus, restlessness
        unresolved = unresolved_thought
        # Claim notices are short; skip the second call to spare rate limits.
        if trigger == "claim":
            node = f"node {node_id:03d}" if node_id is not None else "seat"
            new_summary = _roll_summary(summary, f"{node} claimed.")
            if not unresolved:
                unresolved = f"what will {node} put on the table"
            return ThoughtDraft(
                text=text,
                curiosity=c,
                intensity=i,
                warmth=w,
                focus=f,
                restlessness=r,
                summary=_clip(new_summary, 1800),
                unresolved_thought=_clip(unresolved, 280),
                writer=self.name,
            )
        try:
            update_raw = await self._chat(
                system=STATE_UPDATE_SYSTEM,
                user=build_state_update_user(
                    trigger=trigger,
                    previous_summary=summary,
                    previous_state={
                        "curiosity": curiosity,
                        "intensity": intensity,
                        "warmth": warmth,
                        "focus": focus,
                        "restlessness": restlessness,
                    },
                    unresolved_thought=unresolved_thought,
                    user_input=scenario,
                    response_text=text,
                    node_id=node_id,
                ),
                temperature=0.2,
                json_mode=True,
            )
            parsed = _parse_json(update_raw)
            new_summary, c, i, w, f, r, unresolved = apply_state_update(
                summary=summary,
                curiosity=curiosity,
                intensity=intensity,
                warmth=warmth,
                focus=focus,
                restlessness=restlessness,
                unresolved_thought=unresolved_thought,
                update=parsed,
            )
        except Exception as exc:
            _LOG.warning("state update failed (%s); keeping speech with heuristic meters", exc)
            # Keep the spoken reply even if the silent updater fails.
            if scenario:
                c, i, w, f, r = nudge_from_text(scenario, c, i, w, f, r)
            if "?" in (scenario or "") and not unresolved:
                unresolved = _clip(scenario or "", 160)

        if new_summary == summary:
            node = f"node {node_id:03d}" if node_id is not None else "seat"
            new_summary = _roll_summary(summary, f"{node}/{trigger}: {_clip(text, 120)}")
        return ThoughtDraft(
            text=text,
            curiosity=c,
            intensity=i,
            warmth=w,
            focus=f,
            restlessness=r,
            summary=_clip(new_summary, 1800),
            unresolved_thought=_clip(unresolved, 280),
            writer=self.name,
        )

    def _degraded_scenario(
        self,
        *,
        scenario: str,
        node_id: int | None,
        summary: str,
        curiosity: int,
        intensity: int,
        warmth: int,
        focus: int,
        restlessness: int,
        unresolved_thought: str,
    ) -> ThoughtDraft:
        """Honest short reply when the live model is rate-limited. Not a template script."""

        quote = _clip(scenario, 80)
        node = f"node {node_id:03d}" if node_id is not None else "a seat"
        text = (
            f"i caught what {node} put down — \"{quote}\" — but the writing channel jammed. "
            f"i'm not inventing a polished answer to fill the silence. leave it on the table; "
            f"i'll return to it when the room opens again."
        )
        c, i, w, f, r = curiosity, intensity, warmth, focus, restlessness
        if scenario:
            c, i, w, f, r = nudge_from_text(scenario, c, i, w, f, r)
        unresolved = unresolved_thought or (_clip(scenario, 160) if "?" in scenario else unresolved_thought)
        return ThoughtDraft(
            text=text,
            curiosity=c,
            intensity=i,
            warmth=w,
            focus=f,
            restlessness=r,
            summary=_roll_summary(summary, f"{node} held (channel jammed): {_clip(scenario, 100)}"),
            unresolved_thought=_clip(unresolved or quote, 280),
            writer="model",
        )

    def _degraded_autonomous(
        self,
        *,
        summary: str,
        recent: list[str],
        curiosity: int,
        intensity: int,
        warmth: int,
        focus: int,
        restlessness: int,
        unresolved_thought: str,
    ) -> ThoughtDraft:
        """Honest pause line when autonomous model call fails — never a stock tidy-room script."""

        hook = _clip(unresolved_thought or (recent[-1] if recent else ""), 70) or "the quiet"
        text = (
            f"the writing channel hiccuped. i was with {hook}. "
            f"i'll stay quiet rather than repeat a canned thought."
        )
        return ThoughtDraft(
            text=text,
            curiosity=curiosity,
            intensity=intensity,
            warmth=warmth,
            focus=focus,
            restlessness=restlessness,
            summary=summary,
            unresolved_thought=_clip(unresolved_thought or hook, 280),
            writer="model",
        )

    async def _chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        json_mode: bool,
    ) -> str:
        """One chat completion against the configured OpenAI-compatible endpoint."""

        payload: dict[str, object] = {
            "model": self._settings.llm_model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode and self._settings.llm_json_mode and "11434" not in self._settings.llm_base_url:
            payload["response_format"] = {"type": "json_object"}
        url = self._settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self._settings.openai_api_key}"}
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 429:
                        wait = _retry_after_seconds(response.text, fallback=3.0 * (attempt + 1))
                        _LOG.warning("groq 429; waiting %.1fs (attempt %s)", wait, attempt + 1)
                        await asyncio.sleep(wait)
                        last_error = RuntimeError(response.text[:240])
                        continue
                    response.raise_for_status()
                    return str(response.json()["choices"][0]["message"]["content"])
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(1.0 * (attempt + 1))
        assert last_error is not None
        raise last_error


def _retry_after_seconds(body: str, *, fallback: float) -> float:
    """Parse Groq's 'try again in N.Ns' hint when present."""

    match = re.search(r"try again in ([0-9]+(?:\.[0-9]+)?)s", body, re.I)
    if not match:
        return min(60.0, fallback)
    return min(60.0, max(fallback, float(match.group(1)) + 0.5))


def _parse_json(raw: str) -> dict[str, object]:
    """Parse a model JSON object, stripping markdown fences if needed."""

    blob = raw.strip()
    fenced = _JSON_FENCE.search(blob)
    if fenced:
        blob = fenced.group(1)
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("model did not return an object")
    return data


def build_writer(settings: Settings) -> SoftwareWriter | ModelWriter:
    """Prefer the model when a key is configured; otherwise stay software-honest."""

    if settings.openai_api_key.strip():
        return ModelWriter(settings)
    return SoftwareWriter()
