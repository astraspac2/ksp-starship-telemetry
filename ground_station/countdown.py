"""Countdown clock formatting and pill visibility, independent of Qt so it can be unit-tested."""

import math
from dataclasses import dataclass

PILL_HIDE_AT = -30.0  # seconds relative to liftoff; the pill is gone once T-30 is reached
PILL_FADE_DURATION = 0.5
PILL_SHIFT_PX = 6.0  # the reference clip nudges the pill slightly left as it fades


def format_clock(t: float) -> tuple[str, str]:
    """Return (sign, "HH:MM:SS") for a time relative to liftoff.

    Before liftoff the display counts down on the whole second still remaining
    (T-00:00:01 until liftoff), after it counts up on whole elapsed seconds.
    """
    if t < 0:
        sign = "T-"
        whole = math.ceil(-t)
    else:
        sign = "T+"
        whole = math.floor(t)
    hours, rem = divmod(whole, 3600)
    minutes, seconds = divmod(rem, 60)
    return sign, f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@dataclass(frozen=True)
class PillState:
    visible: bool
    opacity: float
    x_offset: float


def pill_state(t: float) -> PillState:
    """Opacity and horizontal nudge of the pill at time t (seconds relative to liftoff)."""
    if t < PILL_HIDE_AT:
        return PillState(True, 1.0, 0.0)
    progress = (t - PILL_HIDE_AT) / PILL_FADE_DURATION
    if progress >= 1.0:
        return PillState(False, 0.0, -PILL_SHIFT_PX)
    return PillState(True, 1.0 - progress, -PILL_SHIFT_PX * progress)
