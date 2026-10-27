"""A stand-in for KSP's game clock, to test the countdown logic without KSP running.

It only drives the MOCK source. Everything it produces is labelled as mock data on the display.
Qt-free so it can be unit-tested.
"""

import time
from typing import Callable

WARP_RATES = (1.0, 5.0, 10.0, 50.0, 100.0, 1000.0)


class MockGame:
    """Simulated universal time (UT) that can pause, warp, lag and jump like the real game."""

    def __init__(self, now: Callable[[], float] = time.monotonic, start_ut: float = 1_000_000.0):
        self._now = now
        self._ut = start_ut
        self._last = now()
        self._frozen_until = 0.0
        self.paused = False
        self.warp = 1.0
        self.link_lost = False  # the game keeps running but nothing reaches the display

    def ut(self) -> float:
        now = self._now()
        elapsed = max(0.0, now - self._last)
        frozen = max(0.0, min(now, self._frozen_until) - self._last)  # time spent in a lag spike
        if not self.paused:
            self._ut += (elapsed - frozen) * self.warp
        self._last = now
        return self._ut

    @property
    def warping(self) -> bool:
        return self.warp > 1.0

    def freeze(self, seconds: float) -> None:
        """A lag spike: the game stops advancing for `seconds` of real time."""
        self.ut()  # settle the time up to now first
        self._frozen_until = self._now() + seconds

    @property
    def frozen(self) -> bool:
        return self._now() < self._frozen_until

    def jump(self, seconds: float) -> None:
        """A discontinuity in game time, such as a quickload (negative) or a skip ahead (positive)."""
        self.ut()
        self._ut += seconds
