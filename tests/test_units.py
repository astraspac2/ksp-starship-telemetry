import pytest

from ground_station.units import format_altitude, format_speed, format_thrust


@pytest.mark.parametrize(
    "kmh, unit, expected",
    [
        (1315.0, "km/h", ("1315", "KM/H")),
        (360.0, "m/s", ("100", "M/S")),
        (100.0, "mph", ("62", "MPH")),
        (0.0, "km/h", ("0", "KM/H")),
    ],
)
def test_format_speed(kmh, unit, expected):
    assert format_speed(kmh, unit) == expected


@pytest.mark.parametrize(
    "km, unit, expected",
    [
        (0.0279, "auto", ("28", "M")),  # on the pad: metres
        (0.999, "auto", ("999", "M")),
        (3.24, "auto", ("3.2", "KM")),
        (152.4, "auto", ("152", "KM")),
        (3.24, "km", ("3.2", "KM")),
        (9.96, "km", ("10.0", "KM")),
        (0.5, "m", ("500", "M")),
        (100.0, "mi", ("62", "MI")),
        (4.0, "mi", ("2.5", "MI")),
    ],
)
def test_format_altitude(km, unit, expected):
    assert format_altitude(km, unit) == expected


@pytest.mark.parametrize(
    "newtons, unit, reference, expected",
    [
        (18_903_286.0, "auto", None, ("18.9", "MN")),
        (0.0, "auto", 18_915_933.0, ("0.0", "MN")),  # the unit follows the engines' size, so it does not flip while the thrust ramps
        (400_000.0, "auto", 18_915_933.0, ("0.4", "MN")),
        (874_000.0, "auto", None, ("874", "KN")),  # small engines, no reference: kilonewtons
        (874_000.0, "auto", 900_000.0, ("874", "KN")),
        (18_903_286.0, "kN", None, ("18903", "KN")),
        (18_903_286.0, "MN", None, ("18.9", "MN")),
        (9_806_650.0, "tf", None, ("1000", "TF")),
        (-5.0, "kN", None, ("0", "KN")),  # never negative
    ],
)
def test_format_thrust(newtons, unit, reference, expected):
    assert format_thrust(newtons, unit, reference) == expected
