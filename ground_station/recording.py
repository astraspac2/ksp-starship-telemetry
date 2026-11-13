"""Recording a vehicle's flight and playing it back later. Qt-free.

While the booster is the vessel being flown, its numbers are written down against the time since the stage separation. On a
later flight, when the booster cannot be read (it is far away, or the ship is the vessel being flown), those numbers are played back
in its place. A playback is not live data: the panel always says when one is in use.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

FORMAT_VERSION = 1
SAMPLE_SECONDS = 0.25  # at most this often is a reading kept
HOLD_AFTER_SECONDS = 5.0  # after the last reading the playback goes on showing it this long, then ends
FILE_NAME = "booster-last.json"


@dataclass(frozen=True)
class Reading:
    speed_kmh: float
    altitude_km: float
    fuel: float
    engines_on: int
    engines_total: int


@dataclass
class Recording:
    role: str = "booster"
    # (seconds since the separation, speed in km/h, altitude in km, fuel 0..1, engines on, engines in all)
    samples: list[tuple[float, float, float, float, int, int]] = field(default_factory=list)

    @property
    def length(self) -> float:
        return self.samples[-1][0] if self.samples else 0.0

    def at(self, seconds: float) -> Reading | None:
        """The vehicle's numbers `seconds` after the separation, or None when there is no recording or the playback has ended."""
        if not self.samples or seconds > self.length + HOLD_AFTER_SECONDS:
            return None
        if seconds <= self.samples[0][0]:
            return self._reading(self.samples[0])
        if seconds >= self.length:
            return self._reading(self.samples[-1])
        low, high = 0, len(self.samples) - 1
        while high - low > 1:  # the two readings round this moment
            middle = (low + high) // 2
            if self.samples[middle][0] <= seconds:
                low = middle
            else:
                high = middle
        before, after = self.samples[low], self.samples[high]
        share = (seconds - before[0]) / (after[0] - before[0]) if after[0] > before[0] else 0.0
        mix = lambda i: before[i] + (after[i] - before[i]) * share  # noqa: E731
        return Reading(mix(1), mix(2), mix(3), before[4], before[5])

    @staticmethod
    def _reading(row) -> Reading:
        return Reading(row[1], row[2], row[3], row[4], row[5])

    def to_dict(self) -> dict:
        return {"version": FORMAT_VERSION, "role": self.role, "samples": [list(s) for s in self.samples]}

    @staticmethod
    def from_dict(data) -> "Recording | None":
        """A recording from saved data, or None if it is not usable."""
        try:
            if data["version"] != FORMAT_VERSION:
                return None
            rows = []
            for row in data["samples"]:
                seconds, speed, altitude, fuel = (float(row[i]) for i in range(4))
                rows.append((seconds, speed, altitude, fuel, int(row[4]), int(row[5])))
            if len(rows) < 2 or any(b[0] < a[0] for a, b in zip(rows, rows[1:])):
                return None
            return Recording(str(data.get("role", "booster")), rows)
        except (KeyError, TypeError, ValueError, IndexError):
            return None


class FlightRecorder:
    """Collects readings against the time since the separation."""

    def __init__(self, role: str = "booster"):
        self.role = role
        self.samples: list[tuple[float, float, float, float, int, int]] = []

    def add(self, seconds: float, speed_kmh: float, altitude_km: float, fuel: float, engines_on: int, engines_total: int) -> None:
        if seconds < 0:
            return
        if self.samples and seconds - self.samples[-1][0] < SAMPLE_SECONDS:
            return
        if self.samples and seconds < self.samples[-1][0]:
            return  # time went back (a reload): keep what was recorded
        self.samples.append((round(seconds, 2), round(speed_kmh, 1), round(altitude_km, 3), round(fuel, 3), engines_on, engines_total))

    def finish(self) -> Recording | None:
        return Recording(self.role, list(self.samples)) if len(self.samples) >= 2 else None


def save_recording(recording: Recording, folder: Path) -> Path:
    """Write the recording as the folder's latest, and keep a dated copy. Written atomically."""
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(recording.to_dict())
    for name in (FILE_NAME, f"booster-{time.strftime('%Y%m%d-%H%M%S')}.json"):
        temp = folder / (name + ".tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, folder / name)
    return folder / FILE_NAME


def load_latest(folder: Path | None) -> Recording | None:
    if folder is None:
        return None
    try:
        return Recording.from_dict(json.loads((folder / FILE_NAME).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None
