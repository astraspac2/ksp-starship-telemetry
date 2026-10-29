"""Follow the booster after the stack separates, for as long as the game still reports it. Qt-free.

Once the ship is flying alone, the vessel that was left behind within a few kilometres is taken for the booster. Its
speed and altitude are read straight from the game. KSP stops simulating a vessel that is far away, but an unloaded
one still gives its speed and altitude (from its orbit), until the game removes it in the atmosphere. When the
readings stop for a moment the booster is lost for good: nothing is guessed. Nothing here sends anything to the game.
"""

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

FIND_SECONDS = 60.0  # after the separation the booster is looked for this long
FIND_DISTANCE_M = 5000.0  # and must be this close to the ship to be taken for it
READ_EVERY_SECONDS = 0.25
LOST_AFTER_SECONDS = 3.0  # readings that fail this long mean the booster is gone
LOG_SECONDS = 20.0  # what the last readings were, kept for the record written when the booster is lost


@dataclass(frozen=True)
class BoosterReading:
    speed_ms: float | None = None
    altitude_m: float | None = None
    live: bool = False  # True from the moment the booster is found until it is lost


class BoosterTracker:
    def __init__(self, log_path: Path | None = None):
        self._log_path = log_path  # where to write a record of the booster's last moments when it is lost; None = none
        self.reset()

    def reset(self) -> None:
        self._had_cluster = False
        self._search_until: float | None = None
        self._vessel = None
        self._lost = False
        self._reading = BoosterReading()
        self._last_read: float | None = None
        self._failing_since: float | None = None
        self._last_error = ""
        self._history: deque[tuple[float, float, float]] = deque()  # (time, speed, altitude) of the last good readings

    @property
    def reading(self) -> BoosterReading:
        return self._reading

    def update(self, now: float, centre, ship_has_booster_engines: bool, altitude_mode: str = "surface") -> BoosterReading:
        """Look for or read the booster. `ship_has_booster_engines` is True while the vessel being flown still has the booster's cluster."""
        if self._had_cluster and not ship_has_booster_engines:  # the stack has just separated
            self._vessel, self._lost = None, False
            self._reading = BoosterReading()
            self._search_until = now + FIND_SECONDS
        if ship_has_booster_engines:  # the stack again (a reload) or the booster itself is being flown
            self._vessel, self._search_until, self._lost = None, None, False
            self._reading = BoosterReading()
        self._had_cluster = ship_has_booster_engines
        if self._lost or ship_has_booster_engines:
            return self._reading
        if self._vessel is None:
            if self._search_until is not None and now <= self._search_until:
                self._vessel = self._nearest(centre)
                self._last_read = None
            if self._vessel is None:
                return self._reading
        if self._last_read is not None and now - self._last_read < READ_EVERY_SECONDS:
            return self._reading
        self._last_read = now
        try:
            flight_speed = self._vessel.flight(self._vessel.orbit.body.reference_frame).speed
            flight_altitude = (
                self._vessel.flight().mean_altitude if altitude_mode == "sea" else self._vessel.flight().surface_altitude
            )
            if not (math.isfinite(flight_speed) and math.isfinite(flight_altitude)):
                raise ValueError("not a number")
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            if self._failing_since is None:
                self._failing_since = now
            if now - self._failing_since >= LOST_AFTER_SECONDS:  # gone: the game removed it
                self._write_loss(centre, now)
                self._lost, self._vessel = True, None
                self._reading = BoosterReading()
            return self._reading
        self._failing_since = None
        self._reading = BoosterReading(flight_speed, flight_altitude, True)
        self._history.append((round(now, 2), round(flight_speed, 1), round(flight_altitude, 1)))
        while self._history and self._history[0][0] < now - LOG_SECONDS:
            self._history.popleft()
        return self._reading

    def _write_loss(self, centre, now: float) -> None:
        """A small csv of the booster's last readings and what the game said when they stopped, for finding out why it went."""
        if self._log_path is None:
            return
        listed = "unknown"
        try:
            listed = "yes" if self._vessel in centre.vessels else "no"
        except Exception as exc:
            listed = f"error {type(exc).__name__}"
        situation = "unknown"
        try:
            situation = str(getattr(self._vessel.situation, "name", self._vessel.situation))
        except Exception as exc:
            situation = f"error {type(exc).__name__}"
        lines = ["wall_s,speed_ms,altitude_m"] + [f"{t},{v},{a}" for t, v, a in self._history]
        lines.append(f"# lost at wall_s {round(now, 2)}, the last good reading was {round(self._failing_since or now, 2)}")
        lines.append(f"# the game said: {self._last_error}")
        lines.append(f"# still in the game's vessel list: {listed}; its situation: {situation}")
        try:
            self._log_path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
        except OSError:
            pass  # a record is only a help: failing to write it must not stop the telemetry

    @staticmethod
    def _nearest(centre):
        try:
            active = centre.active_vessel
            best, best_distance = None, FIND_DISTANCE_M
            for vessel in centre.vessels:
                if vessel == active:
                    continue
                distance = math.dist(vessel.position(active.reference_frame), (0.0, 0.0, 0.0))
                if distance < best_distance:
                    best, best_distance = vessel, distance
            return best
        except Exception:
            return None
