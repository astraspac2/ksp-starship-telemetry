"""A read-only look at the flown vessel's flaps (control surfaces), for finding out what the game really reports about them.

For every control surface it writes the deployed state, authority limiter, which axes it answers, and every field the part's
modules expose (the Deploy Angle is likely one), plus the pilot's pitch/yaw/roll input and the part's direction. Nothing here
sends anything to the game. Qt-free so it can be unit-tested.
"""

from .vessel_probe import UNREADABLE, _value

COLUMNS = (
    "wall_s", "flap", "title", "deployed", "authority_limiter", "pitch_enabled", "yaw_enabled", "roll_enabled",
    "inverted", "surface_area", "direction", "fields", "input_pitch", "input_yaw", "input_roll", "errors",
)
FIELD_HINTS = ("deploy", "angle", "authority", "flap", "surface", "ctrl", "control")


def _fields(part) -> str:
    """Every module field that looks like it could be a flap's angle or state, as module.name:field=value."""

    def read():
        found = []
        for module in part.modules:
            try:
                fields = dict(module.fields)
            except Exception as exc:
                found.append(f"{module.name}:{UNREADABLE} {type(exc).__name__}")
                continue
            for key, value in fields.items():
                if any(hint in key.lower() or hint in module.name.lower() for hint in FIELD_HINTS):
                    found.append(f"{module.name}:{key}={value}")
        return ";".join(found)

    return str(_value(read))


def read_flaps(vessel, wall: float) -> list[dict]:
    """One row per control surface on `vessel`; what the game will not say comes back as ERR plus the kind of error."""
    surfaces = _value(lambda: list(vessel.parts.control_surfaces))
    if isinstance(surfaces, str):
        return [{"wall_s": round(wall, 2), "flap": surfaces, "errors": f"control_surfaces={surfaces}"}]
    control = vessel.control
    inputs = {
        "input_pitch": _value(lambda: round(control.pitch, 3)),
        "input_yaw": _value(lambda: round(control.yaw, 3)),
        "input_roll": _value(lambda: round(control.roll, 3)),
    }
    rows = []
    for index, surface in enumerate(surfaces):
        part = surface.part
        row = {"wall_s": round(wall, 2), **inputs}
        row["flap"] = _value(lambda: f"{index}:{part.name}")
        row["title"] = _value(lambda: part.title)
        row["deployed"] = _value(lambda: surface.deployed)
        row["authority_limiter"] = _value(lambda: round(surface.authority_limiter, 2))
        row["pitch_enabled"] = _value(lambda: surface.pitch_enabled)
        row["yaw_enabled"] = _value(lambda: surface.yaw_enabled)
        row["roll_enabled"] = _value(lambda: surface.roll_enabled)
        row["inverted"] = _value(lambda: surface.inverted)
        row["surface_area"] = _value(lambda: round(surface.surface_area, 2))
        row["direction"] = _value(lambda: tuple(round(x, 3) for x in part.direction(vessel.reference_frame)))
        row["fields"] = _fields(part)
        row["errors"] = ";".join(
            f"{key}={value}" for key, value in row.items() if isinstance(value, str) and value.startswith(UNREADABLE)
        )
        rows.append(row)
    return rows
