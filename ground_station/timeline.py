"""Full-bar timing: when the bar and its side panels appear, and where milestones sit on the timeline.

Qt-free so it can be unit-tested.
"""

import math
from dataclasses import dataclass

from .countdown import PILL_HIDE_AT

BAR_FADE_DURATION = 0.5
PANELS_START = -10.0  # side panels rise in from the bottom at T-10
PANELS_DURATION = 1.0
PX_PER_SECOND = 1.35  # timeline scale measured from the Starship overlay at 1920 px wide


@dataclass(frozen=True)
class Milestone:
    name: str
    time: float  # seconds relative to liftoff; planned unless replaced by an observed time
    manual: bool = False  # typed in by the operator; drawn differently so it is never mistaken for a detected event


@dataclass(frozen=True)
class Rise:
    opacity: float
    offset: float  # 1.0 = fully below its resting place, 0.0 = at rest


def bar_state(t: float) -> Rise:
    """Clock, timeline and subtitle: fade in as the pill leaves at T-30."""
    progress = (t - PILL_HIDE_AT) / BAR_FADE_DURATION
    return Rise(min(max(progress, 0.0), 1.0), 0.0)


def panels_state(t: float) -> Rise:
    """Gauges, engine cluster and dial: rise from the bottom starting at T-10."""
    p = min(max((t - PANELS_START) / PANELS_DURATION, 0.0), 1.0)
    eased = 1.0 - (1.0 - p) ** 3
    return Rise(p, 1.0 - eased)


def milestone_x(milestone_time: float, now: float, center: float, px_per_second: float = PX_PER_SECOND) -> float:
    """The timeline scrolls: "now" stays at the centre and milestones drift left as time passes."""
    return center + (milestone_time - now) * px_per_second


def nearest_milestone(now: float, milestones: list[Milestone]) -> int:
    """Index of the milestone closest in time to now; it is the one drawn emphasised."""
    return min(range(len(milestones)), key=lambda i: abs(milestones[i].time - now))


FULL_CURVE_KM = 120.0  # the timeline is straight on the pad and fully bowed by this altitude
MAX_SAG_PX = 114.0  # measured: the reference drops ~133 px at 550 px from the centre, which is this at our line half-width


def curve_amount(altitude_km: float | None) -> float:
    """0 (straight) to 1 (fully curved), following altitude so it bends on ascent and unbends on descent.

    Unknown altitude keeps the line straight rather than guessing.
    """
    if altitude_km is None or altitude_km <= 0:
        return 0.0
    return min(altitude_km / FULL_CURVE_KM, 1.0)


def sag(x: float, center: float, half_width: float, amount: float) -> float:
    """How far below the centre height the line sits at x; a parabola, so the middle stays level."""
    if half_width <= 0:
        return 0.0
    offset = (x - center) / half_width
    return amount * MAX_SAG_PX * offset * offset


def tilt_degrees(x: float, center: float, half_width: float, amount: float) -> float:
    """Angle (degrees, clockwise on screen) of the line at x, so a label can lie along it."""
    if half_width <= 0:
        return 0.0
    slope = 2.0 * amount * MAX_SAG_PX * (x - center) / (half_width * half_width)
    return math.degrees(math.atan(slope))


FILL_DURATION = 0.6  # seconds a milestone's dot takes to turn white after the clock passes it


def passed_progress(now: float, milestone_time: float) -> float:
    """0 before the milestone, rising to 1 over FILL_DURATION once it is passed, 1 from then on.

    Driven by the clock alone, so a late joiner or a jump past it simply sees a finished white dot.
    """
    if now < milestone_time:
        return 0.0
    return min((now - milestone_time) / FILL_DURATION, 1.0)
