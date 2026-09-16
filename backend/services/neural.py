"""Software neural adapter. Spike features modulate state; they do not write speech."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SignalFeatures:
    """Electrical-looking numbers derived from a seed. Always software in this build."""

    source: str
    spike_count: int
    event_rate: float
    amplitude: float
    active_channels: tuple[int, ...]


class SoftwareNeuralProvider:
    """Deterministic, labeled software spikes. Not a lab connection."""

    source = "software"

    def observe(self, seed: str, window_ms: int = 800) -> SignalFeatures:
        """Return stable fake-physiology for a given seed string."""

        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        spike_count = 12 + digest[0] % 80
        event_rate = round(spike_count / max(window_ms / 1000, 0.1), 2)
        amplitude = round(0.4 + (digest[1] / 255) * 2.2, 2)
        channels = tuple(sorted({digest[i] % 12 for i in range(2, 8)}))[:4]
        return SignalFeatures(
            source=self.source,
            spike_count=spike_count,
            event_rate=event_rate,
            amplitude=amplitude,
            active_channels=channels,
        )


def features_to_prompt(features: SignalFeatures) -> str:
    """Render spike features as a prompt clause. They are mood, not authorship."""

    channels = ",".join(str(c) for c in features.active_channels) or "none"
    return (
        f"signal source={features.source}; spike_count={features.spike_count}; "
        f"event_rate={features.event_rate}; amplitude={features.amplitude}; "
        f"active_channels={channels}. "
        "These numbers may colour mood. They did not write the sentence."
    )
