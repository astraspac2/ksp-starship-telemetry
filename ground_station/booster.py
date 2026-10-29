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
READ_EVERY_SECONDS = 0.25  # asking for readings one by one (no stream): this often
PARTS_EVERY_SECONDS = 1.0  # whether the booster still has readable parts is looked at this often
HISTORY_EVERY_SECONDS = 0.25
LOST_AFTER_SECONDS = 3.0  # readings that fail this long mean the booster is gone
NO_DATA_SECONDS = 5.0  # once the booster has no readable parts (it has been unloaded) its gauges say NO DATA this long
LOG_SECONDS = 20.0  # what the last readings were, kept for the record written when the booster is lost


@dataclass(frozen=True)
class BoosterReading:
    speed_ms: float | None = None
    altitude_m: float | None = None
    live: bool = False  # True from the moment the booster is found until its gauges are taken off; speed and altitude are None while it has no data


class BoosterTracker:
    def __init__(self, log_path: Path | None = None):
        self._log_path = log_path  # where to write a record of the booster's last moments when it is lost; None = none
        self.reset()

    def reset(self) -> None:
        self._close_streams() if hasattr(self, "_streams") else None
        self._had_cluster = False
        self._search_until: float | None = None
        self._vessel = None
        self._lost = False
        self._reading = BoosterReading()
        self._last_read: float | None = None
        self._failing_since: float | None = None
        self._no_data_since: float | None = None
        self._streams: tuple | None = None  # (speed stream, altitude stream, altitude mode) once the booster is found
        self._parts_at: float | None = None
        self._has_parts = True
        self._last_error = ""
        self._history: deque[tuple[float, float, float]] = deque()  # (time, speed, altitude) of the last good readings

    @property
    def reading(self) -> BoosterReading:
        return self._reading

    def update(
        self, now: float, centre, ship_has_booster_engines: bool, altitude_mode: str = "surface", conn=None
    ) -> BoosterReading:
        """Look for or read the booster. `ship_has_booster_engines` is True while the vessel being flown still has the booster's cluster.

        With `conn` the speed and altitude are streamed (the game pushes every new value, so each call just picks up
        the latest and costs nothing); without it they are asked for a few times a second."""
        if self._had_cluster and not ship_has_booster_engines:  # the stack has just separated
            self._forget()
            self._search_until = now + FIND_SECONDS
        if ship_has_booster_engines:  # the stack again (a reload) or the booster itself is being flown
            self._forget()
            self._search_until = None
        self._had_cluster = ship_has_booster_engines
        if self._lost or ship_has_booster_engines:
            return self._reading
        if self._vessel is None:
            if self._search_until is not None and now <= self._search_until:
                self._vessel = self._nearest(centre)
                self._last_read = self._parts_at = None
                self._has_parts = True
            if self._vessel is None:
                return self._reading
        if self._streams is not None and self._streams[2] != altitude_mode:
            self._close_streams()
        if self._streams is None and conn is not None:
            self._open_streams(conn, altitude_mode)
        if self._streams is None and self._last_read is not None and now - self._last_read < READ_EVERY_SECONDS:
            return self._reading  # asking for each reading is costly: only a few a second
        self._last_read = now
        try:
            speed, altitude = self._values(altitude_mode)
            if self._parts_at is None or now - self._parts_at >= PARTS_EVERY_SECONDS:
                self._parts_at = now
                self._has_parts = len(self._vessel.parts.all) > 0
            if not (math.isfinite(speed) and math.isfinite(altitude)):
                raise ValueError("not a number")
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            if self._failing_since is None:
                self._failing_since = now
            if now - self._failing_since >= LOST_AFTER_SECONDS:  # gone: the game removed it
                if self._no_data_since is None:
                    self._write_loss(centre, now)
                return self._no_data(now)
            return self._reading
        self._failing_since = None
        if not self._has_parts:  # unloaded: the game still gives a speed and altitude from its orbit, but no parts, engines or air readings
            return self._no_data(now)
        self._no_data_since = None
        self._reading = BoosterReading(speed, altitude, True)
        if not self._history or now - self._history[-1][0] >= HISTORY_EVERY_SECONDS:
            self._history.append((round(now, 2), round(speed, 1), round(altitude, 1)))
        while self._history and self._history[0][0] < now - LOG_SECONDS:
            self._history.popleft()
        return self._reading

    def _forget(self) -> None:
        self._close_streams()
        self._vessel, self._lost = None, False
        self._reading = BoosterReading()
        self._failing_since = self._no_data_since = None

    def _open_streams(self, conn, altitude_mode: str) -> None:
        try:
            vessel = self._vessel
            speed = conn.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), "speed")
            altitude = conn.add_stream(getattr, vessel.flight(), "mean_altitude" if altitude_mode == "sea" else "surface_altitude")
            self._streams = (speed, altitude, altitude_mode)
        except Exception:
            self._streams = None  # asked for reading by reading instead

    def _close_streams(self) -> None:
        if self._streams is not None:
            for stream in self._streams[:2]:
                try:
                    stream.remove()
                except Exception:
                    pass
        self._streams = None

    def _values(self, altitude_mode: str) -> tuple[float, float]:
        if self._streams is not None:
            return self._streams[0](), self._streams[1]()
        vessel = self._vessel
        altitude = vessel.flight().mean_altitude if altitude_mode == "sea" else vessel.flight().surface_altitude
        return vessel.flight(vessel.orbit.body.reference_frame).speed, altitude

    def _no_data(self, now: float) -> BoosterReading:
        """The gauges say NO DATA for a while, then come off for good."""
        if self._no_data_since is None:
            self._no_data_since = now
        if now - self._no_data_since >= NO_DATA_SECONDS:
            self._close_streams()
            self._lost, self._vessel = True, None
            self._reading = BoosterReading()
        else:
            self._reading = BoosterReading(None, None, True)
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
