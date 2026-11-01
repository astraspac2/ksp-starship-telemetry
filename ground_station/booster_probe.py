"""A read-only, detailed look at the booster after the stack separates, for finding out what the game really reports.

It takes the vessel left behind within a few kilometres of the ship as the booster, then writes a row of everything
that can be read about it, several times a second, down to the moment it can no longer be read. Nothing here sends
anything to the game. Qt-free so it can be unit-tested.
"""

import math

from .vessel_probe import UNREADABLE, _value

DROP_PARTS = 5  # the vessel flown losing this many parts at once is taken for the separation
FIND_SECONDS = 90.0
FIND_DISTANCE_M = 5000.0
COLUMNS = (
    "wall_s", "ut", "mission_s", "distance_m", "situation", "altitude_m", "mean_altitude_m", "speed_ms", "mach",
    "dynamic_pressure_pa", "g_force", "density", "mass_kg", "parts", "engines", "engines_active", "thrust_n",
    "available_thrust_n", "throttle", "sep_modes", "engine_detail", "errors",
)


def _sum_or_error(values):
    return sum(values) if all(isinstance(v, (int, float)) for v in values) else f"{UNREADABLE} partial"


def read_booster(vessel, active, ut: float, wall: float) -> dict:
    """One row of everything about `vessel`; what the game will not say comes back as ERR plus the kind of error."""
    row = {"wall_s": round(wall, 2), "ut": round(ut, 2)}
    row["mission_s"] = _value(lambda: round(vessel.met, 2))
    row["distance_m"] = _value(lambda: round(math.dist(vessel.position(active.reference_frame), (0.0, 0.0, 0.0)), 1))
    row["situation"] = _value(lambda: str(getattr(vessel.situation, "name", vessel.situation)))
    flight = _value(lambda: vessel.flight())
    body = _value(lambda: vessel.flight(vessel.orbit.body.reference_frame))
    row["altitude_m"] = _value(lambda: round(flight.surface_altitude, 1))
    row["mean_altitude_m"] = _value(lambda: round(flight.mean_altitude, 1))
    row["speed_ms"] = _value(lambda: round(body.speed, 1))
    row["mach"] = _value(lambda: round(flight.mach, 2))
    row["dynamic_pressure_pa"] = _value(lambda: round(flight.dynamic_pressure, 1))
    row["g_force"] = _value(lambda: round(flight.g_force, 2))
    row["density"] = _value(lambda: round(flight.atmosphere_density, 4))
    row["mass_kg"] = _value(lambda: round(vessel.mass, 1))
    row["parts"] = _value(lambda: len(vessel.parts.all))
    engines = _value(lambda: list(vessel.parts.engines))
    row["engines"] = engines if isinstance(engines, str) else len(engines)
    if isinstance(engines, str):
        row.update(engines_active=engines, thrust_n=engines, available_thrust_n=engines, sep_modes=engines, engine_detail=engines)
    else:
        row["engines_active"] = _value(lambda: sum(1 for e in engines if e.active))
        row["thrust_n"] = _sum_or_error([_value(lambda e=e: round(e.thrust, 1)) for e in engines])
        row["available_thrust_n"] = _sum_or_error([_value(lambda e=e: round(e.available_thrust, 1)) for e in engines])
        row["sep_modes"] = ";".join(_sep_mode(e) for e in engines)
        row["engine_detail"] = ";".join(_engine_detail(e) for e in engines)
    row["throttle"] = _value(lambda: round(vessel.control.throttle, 3))
    row["errors"] = ";".join(
        f"{key}={value}" for key, value in row.items() if isinstance(value, str) and value.startswith(UNREADABLE)
    )
    return row


def _engine_detail(engine) -> str:
    name = _value(lambda: engine.part.name)
    state = "on" if _value(lambda: engine.active) is True else "off"
    return f"{name}:{state}:{_value(lambda: round(engine.thrust))}:{_value(lambda: len(engine.thrusters))}n"


def _sep_mode(engine) -> str:
    """The Starship Expansion Project cluster's mode field, or empty for an engine that has no such module."""

    def read():
        module = next((m for m in engine.part.modules if m.name == "ModuleSEPEngineSwitch"), None)
        return "" if module is None else str(module.get_field("Mode"))

    return str(_value(read))


class BoosterFinder:
    """Takes the vessel left within a few kilometres when the vessel flown drops several parts at once for the booster."""

    def __init__(self):
        self._parts: int | None = None
        self._until: float | None = None
        self.vessel = None

    def update(self, now: float, centre) -> object | None:
        try:
            active = centre.active_vessel
            parts = len(active.parts.all)
        except Exception:
            return self.vessel
        if self._parts is not None and self._parts - parts >= DROP_PARTS:
            self._until, self.vessel = now + FIND_SECONDS, None
        self._parts = parts
        if self.vessel is None and self._until is not None and now <= self._until:
            best, best_distance = None, FIND_DISTANCE_M
            try:
                for vessel in centre.vessels:
                    if vessel == active:
                        continue
                    distance = math.dist(vessel.position(active.reference_frame), (0.0, 0.0, 0.0))
                    if distance < best_distance:
                        best, best_distance = vessel, distance
            except Exception:
                best = None
            self.vessel = best
        return self.vessel
