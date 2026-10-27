"""Notice the real stage separation from the data, instead of trusting the planned marker time.

When the booster is left behind the game switches to the upper stage, whose engine count differs (33 -> 6 on the
Starship Expansion Project stack). A change in the engine count after liftoff that holds for a moment is taken as the separation.

Qt-free so it can be unit-tested.
"""

import time
from typing import Callable

CONFIRM_SECONDS = 0.4  # a new engine count must hold this long, so one odd reading does not count as a separation


class SeparationDetector:
    def __init__(self, now: Callable[[], float] = time.monotonic):
        self._now = now
        self.reset()

    def reset(self) -> None:
        self.separated_at: float | None = None
        self._baseline: int | None = None
        self._candidate: tuple[int, float, float] | None = None  # engine count, flight time first seen, wall time first seen

    def update(self, t: float, engines_total: int, valid: bool) -> float | None:
        """Feed one reading; returns the flight time of the separation once seen, else None.

        `valid` is False while the feed is lost or stale, when the reading means nothing.
        """
        if self.separated_at is not None or not valid or engines_total <= 0:
            return self.separated_at
        if t < 0 or self._baseline is None:
            self._baseline = engines_total  # on the pad the vessel may be reloaded or switched without it meaning anything
            self._candidate = None
            return None
        if engines_total == self._baseline:
            self._candidate = None
            return None
        if self._candidate is None or self._candidate[0] != engines_total:
            self._candidate = (engines_total, t, self._now())
        elif self._now() - self._candidate[2] >= CONFIRM_SECONDS:
            self.separated_at = self._candidate[1]
        return self.separated_at
