"""Follow the booster after the stack separates, for as long as the game still reports it. Qt-free.

Once the ship is flying alone, the vessel that was left behind within a few kilometres is taken for the booster. Its
speed and altitude are read straight from the game. KSP stops simulating a vessel that is far away, but an unloaded
one still gives its speed and altitude (from its orbit), until the game removes it in the atmosphere. When the
readings stop for a moment the booster is lost for good: nothing is guessed. Nothing here sends anything to the game.
"""

import math
from dataclasses import dataclass

FIND_SECONDS = 60.0  # after the separation the booster is looked for this long
FIND_DISTANCE_M = 5000.0  # and must be this close to the ship to be taken for it
READ_EVERY_SECONDS = 0.25
LOST_AFTER_SECONDS = 3.0  # readings that fail this long mean the booster is gone


@dataclass(frozen=True)
class BoosterReading:
    speed_ms: float | None = None
    altitude_m: float | None = None
    live: bool = False  # True from the moment the booster is found until it is lost


class BoosterTracker:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._had_cluster = False
        self._search_until: float | None = None
        self._vessel = None
        self._lost = False
        self._reading = BoosterReading()
        self._last_read: float | None = None
        self._failing_since: float | None = None

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
        except Exception:
            if self._failing_since is None:
                self._failing_since = now
            if now - self._failing_since >= LOST_AFTER_SECONDS:  # gone: the game removed it
                self._lost, self._vessel = True, None
                self._reading = BoosterReading()
            return self._reading
        self._failing_since = None
        self._reading = BoosterReading(flight_speed, flight_altitude, True)
        return self._reading

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
