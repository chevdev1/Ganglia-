"""Server-side English TTS. Files are cached per thought and replayed."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.config import DATA_DIR

log = logging.getLogger(__name__)


async def synthesize(output_id: int, text: str, voice: str) -> str:
    """Speak a thought to data/voices/{id}.mp3. Empty string if TTS is unavailable."""

    folder = DATA_DIR / "voices"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{output_id}.mp3"
    if path.exists() and path.stat().st_size > 0:
        return f"/data/voices/{output_id}.mp3"
    try:
        import edge_tts
    except ImportError:
        log.warning("edge-tts is not installed; skipping voice")
        return ""
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(path))
    except Exception:
        log.exception("TTS failed for output %s", output_id)
        if path.exists():
            path.unlink(missing_ok=True)
        return ""
    if not path.exists() or path.stat().st_size == 0:
        return ""
    return f"/data/voices/{output_id}.mp3"


def voice_file(output_id: int) -> Path:
    """Return the on-disk path for a thought's mp3, whether or not it exists."""

    return DATA_DIR / "voices" / f"{output_id}.mp3"
