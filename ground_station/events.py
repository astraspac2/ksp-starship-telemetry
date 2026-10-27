"""Planned timeline events: the list the operator edits and how its rows are read and shown.

Qt-free so it can be unit-tested. Times are seconds relative to liftoff (negative = before).
"""

import math
import re
from dataclasses import dataclass

from .countdown import format_clock


@dataclass
class Event:
    time: float
    label: str
    description: str = ""
    enabled: bool = True


DEFAULT_EVENTS = [
    Event(0.0, "Liftoff"),
    Event(70.0, "Max Q"),
    Event(143.0, "Stage Sep"),
]

# The pad / static-fire view keeps its own list: a burn lasts seconds, not minutes (the times are only a plan).
DEFAULT_PAD_EVENTS = [
    Event(0.0, "Ignition"),
    Event(10.0, "Shutdown"),
]

_CLOCK = re.compile(r"^\s*T?\s*([+-])\s*(?:(\d+):)?(?:(\d+):)?(\d+)\s*$", re.IGNORECASE)


def parse_clock(text: str) -> float | None:
    """Read 'T-00:00:30', 'T+01:50', '-30' and similar as seconds relative to liftoff; None if invalid."""
    match = _CLOCK.match(text)
    if not match:
        return None
    sign, first, second, last = match.groups()
    parts = [int(p) for p in (first, second, last) if p is not None]
    if len(parts) == 3 and (parts[1] > 59 or parts[2] > 59):
        return None
    if len(parts) == 2 and parts[1] > 59:
        return None
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return float(-seconds if sign == "-" else seconds)


def format_clock_text(t: float) -> str:
    """'T-00:00:30' style text for a time relative to liftoff."""
    sign, clock = format_clock(t)
    return f"{sign}{clock}"


def sorted_events(events: list[Event]) -> list[Event]:
    return sorted(events, key=lambda e: e.time)


def next_event_index(events: list[Event], t: float) -> int | None:
    """Index of the first enabled event still ahead of t, in time order."""
    ahead = [(e.time, i) for i, e in enumerate(events) if e.enabled and e.time > t]
    return min(ahead)[1] if ahead else None


def event_status(events: list[Event], index: int, t: float) -> str:
    event = events[index]
    if not event.enabled:
        return "disabled"
    if t >= event.time:
        return "done"
    if index == next_event_index(events, t):
        return f"NEXT in {math.ceil(event.time - t)}s"
    return "upcoming"


def events_to_dicts(events: list[Event]) -> list[dict]:
    return [
        {"time": e.time, "label": e.label, "description": e.description, "enabled": e.enabled} for e in events
    ]


def events_from_dicts(rows) -> list[Event]:
    """Events from saved settings, skipping any row that is not usable."""
    events = []
    for row in rows if isinstance(rows, list) else []:
        try:
            time = float(row["time"])
            label = str(row["label"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if label and math.isfinite(time):
            events.append(Event(time, label, str(row.get("description", "")), bool(row.get("enabled", True))))
    return events
