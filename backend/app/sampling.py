"""Timeline frame-sampling rule shared by preview generation and (later)
tagging (Specification §9.4): interior, evenly spaced timestamps that avoid
the very beginning and end of a video by default.
"""

from __future__ import annotations


def sample_interior_timestamps(duration: float, count: int) -> list[float]:
    """Divide `duration` into `count + 1` segments and return the `count`
    interior segment boundaries as timestamps in seconds."""
    if count <= 0 or duration <= 0:
        return []
    step = duration / (count + 1)
    return [step * (i + 1) for i in range(count)]
