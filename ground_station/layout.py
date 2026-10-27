"""Which arrangement the full bar uses, driven by the Stage Sep point on the timeline.

Three arrangements, as on the Starship overlay, and a fourth for the pad:
  stage 1     booster engines and attitude dial on the left, speed and altitude on the right (until shortly before Stage Sep)
  stage sep   booster engines + dial on the left, speed + the upper stage's engines on the right (from 5 s before to 10 s after)
  flight      speed and altitude on the left, dial and the upper stage's engines on the right (after that)
  pad         engines and dial on the left, thrust and throttle on the right (the operator's pad / static-fire mode; it
              never follows the Stage Sep marker)

Qt-free so it can be unit-tested.
"""

from enum import Enum

from .timeline import Milestone

STAGE_SEP_LEAD = 5.0  # the stage-sep arrangement appears this long before the marker
STAGE_SEP_TAIL = 10.0  # and gives way to the flight arrangement this long after it
_STAGE_SEP_NAMES = {"stage sep", "stage separation"}


class Layout(Enum):
    STAGE_1 = "stage 1"
    STAGE_SEP = "stage sep"
    FLIGHT = "flight"
    PAD = "pad"


def is_stage_sep(name: str) -> bool:
    """'Stage Sep' or 'Stage Separation' in any capitalisation, with stray spaces ignored."""
    return " ".join(name.lower().split()) in _STAGE_SEP_NAMES


def stage_sep_time(milestones: list[Milestone]) -> float | None:
    """When the Stage Sep marker sits, or None when the timeline has none (the bar then never changes arrangement)."""
    return next((m.time for m in milestones if is_stage_sep(m.name)), None)


def layout_for(t: float, planned: float | None, observed: float | None = None) -> Layout:
    """The arrangement at flight time t.

    `planned` is the Stage Sep marker; it brings the stage-sep arrangement in ahead of time. `observed` is when the
    separation was actually seen in the data; once it is known it decides when the flight arrangement takes over,
    and it brings the stage-sep arrangement in at once if the stack separated earlier than planned.
    """
    if observed is not None:
        start = observed if planned is None else min(planned - STAGE_SEP_LEAD, observed)
        if t < start:
            return Layout.STAGE_1
        return Layout.STAGE_SEP if t < observed + STAGE_SEP_TAIL else Layout.FLIGHT
    if planned is None or t < planned - STAGE_SEP_LEAD:
        return Layout.STAGE_1
    return Layout.STAGE_SEP if t < planned + STAGE_SEP_TAIL else Layout.FLIGHT


def staged(t: float, observed: float | None) -> bool:
    """Whether the separation has been seen in the data, so the upper stage's engines are the live ones."""
    return observed is not None and t >= observed


ARRANGEMENT_FADE = 1.4  # seconds a change of arrangement takes: the old dial goes, then the new one draws itself in


def fade_progress(now: float, started: float, duration: float = ARRANGEMENT_FADE) -> float:
    """0 when a change of arrangement has just begun, 1 once it has finished."""
    if duration <= 0:
        return 1.0
    return min(max((now - started) / duration, 0.0), 1.0)


class BoosterMemory:
    """The booster's last readings, so its engine dial can hold what it showed when the stack separated.

    After the separation the game reports the upper stage, so the booster's own state is only known from before.
    """

    def __init__(self, keep_seconds: float = 3.0):
        self._keep = keep_seconds
        self._items: list[tuple[float, object]] = []

    def clear(self) -> None:
        self._items.clear()

    def record(self, t: float, reading: object) -> None:
        if self._items and t < self._items[-1][0] - 1.0:
            self._items.clear()  # time ran backwards (a reset), so the old readings are from another flight
        self._items.append((t, reading))
        while self._items and self._items[0][0] < t - self._keep:
            self._items.pop(0)

    def before(self, separated_at: float) -> object | None:
        """The newest reading from before the separation, or None if there is none."""
        earlier = [reading for t, reading in self._items if t < separated_at]
        return earlier[-1] if earlier else None
