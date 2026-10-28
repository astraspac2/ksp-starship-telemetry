"""A small record of what the game reported around a change in the engine count (a staging), for finding out what really happened.

Qt-free. Only readings are written, to one csv file that the next staging overwrites; nothing is sent anywhere.
"""

import time
from collections import deque
from pathlib import Path
from typing import Callable

BEFORE_SECONDS = 6.0  # kept from before the change
AFTER_SECONDS = 20.0  # written after it
HEADER = "wall_s,flight_t,engines_total,engines_on,separated_at,status\n"


class StagingTrace:
    def __init__(self, path: Path, now: Callable[[], float] = time.monotonic):
        self._path = path
        self._now = now
        self._recent: deque[tuple] = deque()
        self._until = 0.0
        self._last_total = 0

    def add(self, t: float, engines_total: int, engines_on: int, separated_at: float | None, status: str | None) -> None:
        wall = self._now()
        row = (round(wall, 3), round(t, 2), engines_total, engines_on, "" if separated_at is None else round(separated_at, 2), status or "")
        changed = t > 0 and self._last_total > 0 and engines_total > 0 and engines_total != self._last_total
        if t > 0 and engines_total > 0:  # on the pad a vessel may be switched or reloaded without it meaning anything
            self._last_total = engines_total
        if changed:
            self._until = wall + AFTER_SECONDS
            self._write("w", HEADER + "".join(self._line(r) for r in self._recent))
        if changed or wall < self._until:
            self._write("a", self._line(row))
        self._recent.append(row)
        while self._recent and self._recent[0][0] < wall - BEFORE_SECONDS:
            self._recent.popleft()

    @staticmethod
    def _line(row: tuple) -> str:
        return ",".join(str(v) for v in row) + "\n"

    def _write(self, mode: str, text: str) -> None:
        try:
            with open(self._path, mode, encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass  # a trace that cannot be written must never get in the way of the display
