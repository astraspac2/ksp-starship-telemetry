"""A read-only look at the flown vessel's flaps, for finding out what the game really reports about them.

kRPC's own list of control surfaces misses some flap parts (the Starship Expansion Project may use its own module), so this
scans every part and takes the ones that look like a flap or fin: a title with "flap" or "fin" in it, or any module with a
Deploy Angle or Authority Limiter field. For each it writes the names of all its modules and every field they expose, plus
the pilot's pitch/yaw/roll input and the part's direction. Nothing here sends anything to the game. Qt-free so it can be
unit-tested.
"""

from .vessel_probe import UNREADABLE, _value

COLUMNS = (
    "wall_s", "flap", "title", "modules", "kind", "deployed", "deploy_angle", "authority_limiter", "direction", "fields",
    "input_pitch", "input_yaw", "input_roll", "errors",
)
TITLE_HINTS = ("flap", "fin")
FIELD_HINTS = ("deploy angle", "authority")


def _module_fields(part) -> dict[str, dict]:
    """Every module's fields, by module name; a module that will not list its fields gives an ERR entry."""
    found = {}
    for module in part.modules:
        try:
            found[module.name] = dict(module.fields)
        except Exception as exc:
            found[module.name] = {"fields": f"{UNREADABLE} {type(exc).__name__}"}
    return found


def _is_flap(part, modules: dict[str, dict]) -> bool:
    title = str(_value(lambda: part.title)).lower()
    if any(hint in title for hint in TITLE_HINTS):
        return True
    return any(any(hint in key.lower() for hint in FIELD_HINTS) for fields in modules.values() for key in fields)


def _find(modules: dict[str, dict], *names: str):
    for fields in modules.values():
        for key, value in fields.items():
            if key.lower() in names:
                return value
    return ""


def read_flaps(vessel, wall: float) -> list[dict]:
    """One row per flap-like part on `vessel`; what the game will not say comes back as ERR plus the kind of error."""
    parts = _value(lambda: list(vessel.parts.all))
    if isinstance(parts, str):
        return [{"wall_s": round(wall, 2), "flap": parts, "errors": f"parts={parts}"}]
    control = vessel.control
    inputs = {
        "input_pitch": _value(lambda: round(control.pitch, 3)),
        "input_yaw": _value(lambda: round(control.yaw, 3)),
        "input_roll": _value(lambda: round(control.roll, 3)),
    }
    rows = []
    for index, part in enumerate(parts):
        modules = _value(lambda: _module_fields(part))
        if isinstance(modules, str):
            continue
        if not _is_flap(part, modules):
            continue
        row = {"wall_s": round(wall, 2), **inputs}
        row["flap"] = _value(lambda: f"{index}:{part.name}")
        row["title"] = _value(lambda: part.title)
        row["modules"] = ";".join(modules)
        row["kind"] = "control-surface" if "ModuleControlSurface" in modules else "other"
        row["deployed"] = _find(modules, "deploy")
        row["deploy_angle"] = _find(modules, "deploy angle")
        row["authority_limiter"] = _find(modules, "authority limiter")
        row["direction"] = _value(lambda: tuple(round(x, 3) for x in part.direction(vessel.reference_frame)))
        row["fields"] = ";".join(f"{name}:{key}={value}" for name, fields in modules.items() for key, value in fields.items())
        row["errors"] = ";".join(
            f"{key}={value}" for key, value in row.items() if isinstance(value, str) and value.startswith(UNREADABLE)
        ) or (f"fields={UNREADABLE}" if f"{UNREADABLE} " in row["fields"] else "")
        rows.append(row)
    return rows
