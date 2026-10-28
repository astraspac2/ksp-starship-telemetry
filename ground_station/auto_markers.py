"""Timeline markers the station adds by itself from what the game reports. Qt-free.

Two kinds:
  node     a maneuver node planned in KSP. Once it has stayed put for a moment the operator is asked to name it, and it
           goes on the timeline at the moment it will happen (now plus the time left on the node). While the node is
           being dragged the marker follows it.
  reentry  RE-ENTRY, when the vessel comes down through 70 km. It only works after the vessel has been above 70 km
           (so a suborbital flight counts, a low hop does not). Once the path dips into the atmosphere the marker is
           placed at the predicted moment, and when 70 km is really crossed on the way down it is set to that moment.

Nothing here sends anything to the game.
"""

import math
from dataclasses import dataclass, field
from typing import Sequence

NODE_STABLE_SECONDS = 2.0  # a new node must stay unchanged this long (wall time) before the operator is asked about it
NODE_MATCH_SECONDS = 900.0  # a node that moved less than this between two readings is still the same node
NODE_MOVED_SECONDS = 0.05  # smaller shifts are rounding noise
REENTRY_ALTITUDE_KM = 70.0  # the marker arms once the vessel is above this, and is set when it comes back down through it
REENTRY_NAME = "Re-entry"
REENTRY_MOVED_SECONDS = 0.5

NODE = "node"
REENTRY = "reentry"


@dataclass
class AutoMarker:
    name: str
    time: float  # seconds relative to liftoff
    kind: str  # NODE or REENTRY
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
        if name and math.isfinite(time) and kind in (NODE, REENTRY):
            markers.append(AutoMarker(name, time, kind, bool(row.get("enabled", True))))
    return markers


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
    ) -> None:
        """Take one reading: `wall` is real time, `t` the flight clock, `ut` game time, the rest as the game reports."""
        if ut is None:
            return
        self._follow_nodes(wall, t, ut, sorted(u for u in node_uts if u > ut))
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
