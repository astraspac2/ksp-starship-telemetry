"""Timeline markers the station adds by itself from what the game reports. Qt-free.

Two kinds:
  node     a maneuver node planned in KSP. Once it has stayed put for a moment the operator is asked to name it, and it
           goes on the timeline at the moment it will happen (now plus the time left on the node). While the node is
           being dragged the marker follows it.
  reentry  RE-ENTRY, when the vessel comes down through 70 km. It only works after the vessel has been above 70 km
           (so a suborbital flight counts, a low hop does not). Once the path dips into the atmosphere the marker is
           placed at the predicted moment, and when 70 km is really crossed on the way down it is set to that moment.

  landing  LANDING BURN, when the vessel coming down passes 800 m (above the ground, or above sea level if that is the chosen
           altitude). Like re-entry it only works after the vessel has been above 70 km. From the first time the vessel is above
           70 km the marker is placed at the predicted moment (from the orbit while it is still above the air, from how
           fast it is sinking and slowing once it is braking in it), kept up to date as it comes down, and when 800 m
           is really crossed it is set to that moment.

The re-entry and landing markers are kept off the timeline until the flight clock reaches T+00:10:00 (see
LATE_MARKER_VISIBLE_FROM), so they do not sit on the bar during the launch.

Nothing here sends anything to the game.
"""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Sequence

NODE_STABLE_SECONDS = 2.0  # a new node must stay unchanged this long (wall time) before the operator is asked about it
NODE_MATCH_SECONDS = 900.0  # a node that moved less than this between two readings is still the same node
NODE_MOVED_SECONDS = 0.05  # smaller shifts are rounding noise
REENTRY_ALTITUDE_KM = 70.0  # the marker arms once the vessel is above this, and is set when it comes back down through it
REENTRY_NAME = "Re-entry"
REENTRY_MOVED_SECONDS = 0.5

LATE_MARKER_KINDS = ("reentry", "landing")
LATE_MARKER_VISIBLE_FROM = 600.0  # these two stay off the timeline until the flight clock reaches T+00:10:00

LANDING_BURN_ALTITUDE_M = 800.0  # Starship lights its engines for the landing burn at about this height
LANDING_ARM_KM = REENTRY_ALTITUDE_KM  # arms like the re-entry marker: only flights that got above 70 km
LANDING_NAME = "Landing burn"
LANDING_MOVED_SECONDS = 0.5
LANDING_RATE_WINDOW = 10.0  # game seconds of readings the sink rate and its slowing are measured over
LANDING_SMOOTHING_SECONDS = 4.0  # the predicted moment moves toward each new prediction with this time constant
LANDING_RATE_MIN_SPAN = 2.0

NODE = "node"
REENTRY = "reentry"
LANDING = "landing"


@dataclass
class AutoMarker:
    name: str
    time: float  # seconds relative to liftoff
    kind: str  # NODE, REENTRY or LANDING
    enabled: bool = True
    node_ut: float | None = field(default=None, compare=False)  # the node it follows, while that node still exists


@dataclass(frozen=True)
class NodeProposal:
    node_ut: float
    time: float  # when it will happen, relative to liftoff
    ahead: float  # seconds from now


def auto_markers_to_dicts(markers: list[AutoMarker]) -> list[dict]:
    return [{"name": m.name, "time": m.time, "kind": m.kind, "enabled": m.enabled} for m in markers]


def auto_markers_from_dicts(rows) -> list[AutoMarker]:
    """Markers from saved settings, skipping any row that is not usable."""
    markers = []
    for row in rows if isinstance(rows, list) else []:
        try:
            name = str(row["name"]).strip()
            time = float(row["time"])
            kind = str(row["kind"])
        except (KeyError, TypeError, ValueError):
            continue
        if name and math.isfinite(time) and kind in (NODE, REENTRY, LANDING):
            markers.append(AutoMarker(name, time, kind, bool(row.get("enabled", True))))
    return markers


def seconds_to_reach(samples: Sequence[tuple[float, float]], target: float) -> float | None:
    """How long until a falling vessel is down to `target` metres, from recent (game time, metres) readings.

    Fits a curve through all of the readings (so one noisy reading cannot throw it) that has both a speed and a rate of
    slowing, so a vessel braking in the atmosphere is not predicted to arrive as if it kept its speed. With no usable
    slowing it falls back to the plain speed. None when it is not sinking."""
    if len(samples) < 3:
        return None
    now = samples[-1][0]
    # least squares for height = c0 + c1 * tau + c2 * tau^2, with tau the seconds before the newest reading (<= 0)
    power = [0.0] * 5  # sums of tau^0 .. tau^4
    moment = [0.0] * 3  # sums of tau^k * height
    for moment_time, height in samples:
        tau = moment_time - now
        for k in range(5):
            power[k] += tau**k
        for k in range(3):
            moment[k] += tau**k * height
    matrix = [[power[row + col] for col in range(3)] for row in range(3)]
    solution = _solve3(matrix, moment)
    if solution is None:
        return None
    c0, c1, c2 = solution
    speed = -c1  # sinking speed at the newest reading
    if speed <= 0:
        return None
    distance = c0 - target
    if distance <= 0:
        return 0.0
    if abs(c2) > 1e-9:
        room = c1 * c1 - 4.0 * c2 * distance
        if room >= 0:
            roots = [(-c1 + sign * math.sqrt(room)) / (2.0 * c2) for sign in (-1.0, 1.0)]
            ahead = [r for r in roots if r > 0]
            if ahead:  # it still gets there while braking
                return min(ahead)
    return distance / speed


def _solve3(matrix: list[list[float]], vector: list[float]) -> tuple[float, float, float] | None:
    """Solve a 3x3 linear system by Cramer's rule; None when it has no single answer."""

    def det(m):
        return (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )

    whole = det(matrix)
    if abs(whole) < 1e-12:
        return None
    answer = []
    for col in range(3):
        swapped = [row[:] for row in matrix]
        for row in range(3):
            swapped[row][col] = vector[row]
        answer.append(det(swapped) / whole)
    return answer[0], answer[1], answer[2]


def _nearest(target: float, candidates: Sequence[float], limit: float = NODE_MATCH_SECONDS) -> float | None:
    best = min(candidates, key=lambda c: abs(c - target), default=None)
    return best if best is not None and abs(best - target) <= limit else None


class AutoMarkerTracker:
    """Watches the game's nodes and orbit and keeps `markers` up to date. The list is shared with the session."""

    def __init__(self, markers: list[AutoMarker]):
        self.markers = markers
        self.pending: NodeProposal | None = None
        self._changed = False
        self._declined: list[float] = []  # nodes the operator said no to, followed as they move
        self._candidate: float | None = None
        self._candidate_since = 0.0
        self._armed = False
        self._suppressed = False  # the operator deleted the marker; leave it deleted
        self._reentry: AutoMarker | None = None
        self._last_altitude: float | None = None
        self._landing_armed = False
        self._landing_suppressed = False
        self._landing: AutoMarker | None = None
        self._landing_estimate: tuple[float, float] | None = None  # smoothed (game time, flight time) of the burn
        self._sinking: deque[tuple[float, float]] = deque()  # (game time, metres) while the vessel is falling

    def take_changed(self) -> bool:
        changed, self._changed = self._changed, False
        return changed

    def reset(self) -> None:
        """Forget what was being asked or watched, e.g. after the data source changed. Saved markers stay."""
        self.pending = None
        self._declined.clear()
        self._candidate = None
        self._armed = self._suppressed = False
        self._reentry = None
        self._last_altitude = None
        self._landing_armed = self._landing_suppressed = False
        self._landing = None
        self._landing_estimate = None
        self._sinking.clear()
        for marker in self.markers:
            marker.node_ut = None

    # answers from the operator
    def accept(self, name: str) -> AutoMarker | None:
        proposal, self.pending = self.pending, None
        name = name.strip()
        if proposal is None or not name:
            return None
        marker = AutoMarker(name, round(proposal.time, 1), NODE, node_ut=proposal.node_ut)
        self.markers.append(marker)
        self._candidate = None
        self._changed = True
        return marker

    def decline(self) -> None:
        if self.pending is not None:
            self._declined.append(self.pending.node_ut)
        self.pending = None
        self._candidate = None

    # readings
    def update(
        self,
        wall: float,
        t: float,
        ut: float | None,
        node_uts: Sequence[float],
        altitude_km: float | None,
        reentry_ut: float | None,
        landing_ut: float | None = None,
    ) -> None:
        """Take one reading: `wall` is real time, `t` the flight clock, `ut` game time, the rest as the game reports."""
        if ut is None:
            return
        self._follow_nodes(wall, t, ut, sorted(u for u in node_uts if u > ut))
        self._watch_landing(t, ut, altitude_km, landing_ut)  # reads the previous altitude, so it goes before the re-entry watch
        self._watch_reentry(t, ut, altitude_km, reentry_ut)

    def _follow_nodes(self, wall: float, t: float, ut: float, nodes: list[float]) -> None:
        free = list(nodes)
        for marker in self.markers:
            if marker.node_ut is None:
                continue
            match = _nearest(marker.node_ut, free)
            if match is None:  # the node is gone: it was executed or removed, and the marker stays as it was
                marker.node_ut = None
                continue
            free.remove(match)
            if abs(match - marker.node_ut) > NODE_MOVED_SECONDS:
                marker.time = round(marker.time + (match - marker.node_ut), 1)
                marker.node_ut = match
                self._changed = True
        for index, old in enumerate(self._declined):
            match = _nearest(old, free)
            if match is not None:
                free.remove(match)
                self._declined[index] = match
        if self.pending is not None:
            match = _nearest(self.pending.node_ut, free)
            if match is None:
                self.pending = None
                self._candidate = None
            else:
                free.remove(match)
                self.pending = NodeProposal(match, t + (match - ut), match - ut)
            return
        if not free:
            self._candidate = None
            return
        newest = free[0]
        if self._candidate is None or abs(newest - self._candidate) > NODE_MOVED_SECONDS:
            self._candidate, self._candidate_since = newest, wall
        elif wall - self._candidate_since >= NODE_STABLE_SECONDS:
            self.pending = NodeProposal(newest, t + (newest - ut), newest - ut)

    def _watch_reentry(self, t: float, ut: float, altitude_km: float | None, reentry_ut: float | None) -> None:
        if self._reentry is not None and self._reentry not in self.markers:
            self._reentry, self._suppressed = None, True  # taken off the list by the operator
        known = altitude_km is not None and math.isfinite(altitude_km)
        if known and altitude_km > REENTRY_ALTITUDE_KM and not self._armed:  # every climb above 70 km is a new flight
            self._armed, self._suppressed = True, False
        falling = altitude_km is not None and self._last_altitude is not None and altitude_km < self._last_altitude
        previous, self._last_altitude = self._last_altitude, altitude_km
        if not self._armed:
            return
        if altitude_km is not None and previous is not None and altitude_km <= REENTRY_ALTITUDE_KM and falling:
            self._place_reentry(t)  # 70 km crossed on the way down
            self._armed = False
        elif reentry_ut is not None and reentry_ut > ut:
            self._place_reentry(t + (reentry_ut - ut))  # the orbit now dips into the atmosphere

    def _place_reentry(self, time: float) -> None:
        time = round(time, 1)
        if self._suppressed:
            return
        if self._reentry is None:  # one from an earlier flight, kept in the settings, is reused
            self._reentry = next((m for m in self.markers if m.kind == REENTRY), None)
        if self._reentry is None:
            self._reentry = AutoMarker(REENTRY_NAME, time, REENTRY)
            self.markers.append(self._reentry)
            self._changed = True
        elif abs(self._reentry.time - time) > REENTRY_MOVED_SECONDS:
            self._reentry.time = time
            self._changed = True

    def _watch_landing(self, t: float, ut: float, altitude_km: float | None, landing_ut: float | None) -> None:
        if self._landing is not None and self._landing not in self.markers:
            self._landing, self._landing_suppressed = None, True  # taken off the list by the operator
        if altitude_km is None or not math.isfinite(altitude_km):
            return
        metres = altitude_km * 1000.0
        if altitude_km > LANDING_ARM_KM and not self._landing_armed:  # every climb above 70 km is a new flight
            self._landing_armed, self._landing_suppressed = True, False
        previous = self._last_altitude
        if not self._landing_armed:
            return
        if previous is not None and altitude_km > previous:
            self._sinking.clear()  # climbing: what was measured on the way down no longer applies
        if previous is not None and altitude_km < previous and metres <= LANDING_BURN_ALTITUDE_M:
            self._place_landing(t)  # 800 m crossed on the way down
            self._landing_armed = False
            self._landing_estimate = None
            self._sinking.clear()
            return
        if not self._sinking or ut > self._sinking[-1][0]:  # the game repeats a reading until it has a new one
            self._sinking.append((ut, metres))
        while self._sinking and ut - self._sinking[0][0] > LANDING_RATE_WINDOW:
            self._sinking.popleft()
        falling = self._sinking[-1][0] - self._sinking[0][0] >= LANDING_RATE_MIN_SPAN
        seconds = seconds_to_reach(self._sinking, LANDING_BURN_ALTITUDE_M) if falling else None
        in_atmosphere = altitude_km <= LANDING_ARM_KM
        if seconds is not None and (in_atmosphere or landing_ut is None or landing_ut <= ut):
            self._place_landing(self._smoothed(ut, t + seconds))  # braking in the air: its own speed says more than the orbit
        elif landing_ut is not None and landing_ut > ut:
            self._place_landing(self._smoothed(ut, t + (landing_ut - ut)))  # the orbit says when 800 m comes

    def _smoothed(self, ut: float, time: float) -> float:
        """The predicted flight time of the burn, eased toward each new prediction so the marker does not jitter."""
        if self._landing_estimate is None or ut < self._landing_estimate[0]:
            self._landing_estimate = (ut, time)
            return time
        before_ut, before = self._landing_estimate
        weight = 1.0 - math.exp(-(ut - before_ut) / LANDING_SMOOTHING_SECONDS)
        smoothed = before + (time - before) * weight
        self._landing_estimate = (ut, smoothed)
        return smoothed

    def _place_landing(self, time: float) -> None:
        time = round(time, 1)
        if self._landing_suppressed:
            return
        if self._landing is None:  # one from an earlier flight, kept in the settings, is reused
            self._landing = next((m for m in self.markers if m.kind == LANDING), None)
        if self._landing is None:
            self._landing = AutoMarker(LANDING_NAME, time, LANDING)
            self.markers.append(self._landing)
            self._changed = True
        elif abs(self._landing.time - time) > LANDING_MOVED_SECONDS:
            self._landing.time = time
            self._changed = True
