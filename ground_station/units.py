"""Speed, altitude and thrust as shown on the bar. Qt-free so it can be unit-tested."""

KM_TO_MILES = 0.621371
NEWTONS_PER_TONNE_FORCE = 9806.65

SPEED_UNITS = ("km/h", "m/s", "mph")
ALTITUDE_UNITS = ("auto", "km", "m", "mi")
THRUST_UNITS = ("auto", "MN", "kN", "tf")

SPEED_LABELS = {"km/h": "Kilometres per hour (km/h)", "m/s": "Metres per second (m/s)", "mph": "Miles per hour (mph)"}
ALTITUDE_LABELS = {
    "auto": "Automatic (m below 1 km, km above)",
    "km": "Kilometres (km)",
    "m": "Metres (m)",
    "mi": "Miles (mi)",
}


def _one_decimal_under_ten(value: float) -> str:
    return f"{value:.1f}" if value < 10 else f"{value:.0f}"


def format_speed(kmh: float, unit: str) -> tuple[str, str]:
    """(text, unit label) for a speed given in km/h."""
    if unit == "m/s":
        return f"{kmh / 3.6:.0f}", "M/S"
    if unit == "mph":
        return f"{kmh * KM_TO_MILES:.0f}", "MPH"
    return f"{kmh:.0f}", "KM/H"


def format_altitude(km: float, unit: str) -> tuple[str, str]:
    """(text, unit label) for an altitude given in km."""
    if unit == "auto":
        unit = "m" if abs(km) < 1.0 else "km"
    if unit == "m":
        return f"{km * 1000:.0f}", "M"
    if unit == "mi":
        return _one_decimal_under_ten(km * KM_TO_MILES), "MI"
    return _one_decimal_under_ten(km), "KM"

THRUST_LABELS = {
    "auto": "Automatic (MN, or kN for small engines)",
    "MN": "Meganewtons (MN)",
    "kN": "Kilonewtons (kN)",
    "tf": "Tonnes-force (tf)",
}


def format_thrust(newtons: float, unit: str, reference_n: float | None = None) -> tuple[str, str]:
    """(text, unit label) for a thrust in newtons.

    "auto" picks meganewtons or kilonewtons by the size of the engines (`reference_n`, their full thrust, when it is
    known) rather than by the value, so the unit does not flip while the thrust ramps up or down.
    """
    newtons = max(newtons, 0.0)
    if unit == "auto":
        unit = "MN" if (reference_n if reference_n else newtons) >= 1e6 else "kN"
    if unit == "MN":
        return f"{newtons / 1e6:.1f}", "MN"
    if unit == "tf":
        return f"{newtons / NEWTONS_PER_TONNE_FORCE:.0f}", "TF"
    return f"{newtons / 1e3:.0f}", "KN"
