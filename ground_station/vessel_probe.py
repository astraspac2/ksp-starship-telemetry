"""A read-only look at every vessel in the game: which ones kRPC can still read, and how far away they are.

Meant for finding out how long a booster stays readable after it leaves the vessel you are flying (KSP stops
simulating vessels that are far away). Nothing here sends anything to the game. Qt-free so it can be unit-tested.
"""

import math

UNREADABLE = "ERR"
COLUMNS = ("name", "situation", "distance_m", "altitude_m", "speed_ms", "parts", "engines")


def _value(read):
    """What `read()` gives, or ERR plus the kind of error when the game will not say (an unloaded vessel)."""
    try:
        return read()
    except Exception as exc:
        return f"{UNREADABLE} {type(exc).__name__}"


def read_vessel(vessel, active) -> dict:
    """One row about `vessel`: the fields kRPC may refuse for a vessel that is not loaded come back as ERR."""
    row = {
        "name": _value(lambda: vessel.name),
        "situation": _value(lambda: str(getattr(vessel.situation, "name", vessel.situation))),
        "distance_m": _value(lambda: round(math.dist(vessel.position(active.reference_frame), (0.0, 0.0, 0.0)), 1)),
        "altitude_m": _value(lambda: round(vessel.flight().surface_altitude, 1)),
        "speed_ms": _value(lambda: round(vessel.flight(vessel.orbit.body.reference_frame).speed, 1)),
        "parts": _value(lambda: len(vessel.parts.all)),
        "engines": _value(lambda: len(vessel.parts.engines)),
    }
    row["readable"] = not any(str(row[key]).startswith(UNREADABLE) for key in ("altitude_m", "speed_ms", "parts"))
    return row


def probe(space_center, limit: int = 12) -> list[dict]:
    """A row for the vessel being flown (first) and the nearest others."""
    active = space_center.active_vessel
    rows = []
    for vessel in space_center.vessels:
        row = read_vessel(vessel, active)
        row["active"] = _value(lambda v=vessel: v == active) is True
        rows.append(row)
    rows.sort(key=lambda r: (not r["active"], r["distance_m"] if isinstance(r["distance_m"], float) else math.inf))
    return rows[:limit]
