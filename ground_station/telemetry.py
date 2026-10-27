"""Telemetry snapshot shown on the bar, plus a clearly synthetic generator for demos."""

import math
from dataclasses import dataclass, replace

from .source import DataSource


@dataclass(frozen=True)
class Telemetry:
    t: float  # seconds relative to liftoff
    speed_kmh: float | None  # None when there is no data to show
    altitude_km: float | None
    fuel_fraction: float | None  # propellant remaining in the current stage, 0..1
    pitch_deg: float | None  # 0 = vertical, 90 = horizontal
    engines_on: int
    engines_total: int
    source: DataSource
    status: str | None = None  # set when the feed is unhealthy, e.g. "SIGNAL LOST"
    engine_lit: tuple[bool, ...] = ()  # per engine dot, inner rings first; empty = first engines_on are lit
    heading_deg: float | None = None  # compass heading of the nose; None = unknown, the dial then shows tilt only
    roll_deg: float | None = None  # roll about the nose axis; None = unknown, drawn as no roll
    latitude_deg: float | None = None  # where the vessel is over the planet; None = unknown, the map then shows no position
    longitude_deg: float | None = None
    separated_at: float | None = None  # flight time the stage separation was seen in the data; None = not (yet) seen
    thrust_n: float | None = None  # total thrust of the engines being flown, in newtons; None = not known
    max_thrust_n: float | None = None  # the same engines' thrust at full throttle, the 100 % mark of the thrust gauge
    throttle: float | None = None  # the throttle setting, 0..1


MOCK_UPPER_ENGINES = 6
MOCK_PAD_LATITUDE = 28.5  # the made-up flight leaves from Florida and heads due east
MOCK_PAD_LONGITUDE = -80.6


def mock_telemetry(t: float, stage_sep_t: float | None = None) -> Telemetry:
    """Smooth made-up ascent profile. Always tagged MOCK; never a stand-in for kRPC data.

    With `stage_sep_t` the booster stops there and the upper stage (6 engines, fresh tanks) takes over.
    """
    if stage_sep_t is not None and t >= stage_sep_t:
        since = t - stage_sep_t
        base = mock_telemetry(t)
        return replace(
            base,
            fuel_fraction=max(1.0 - since / 300.0, 0.0),
            engines_on=MOCK_UPPER_ENGINES if since >= 3.0 else 0,  # the upper stage lights a few seconds after separating
            engines_total=MOCK_UPPER_ENGINES,
        )
    burn = max(t, 0.0)
    speed = 0.0 if t < 0 else 0.55 * burn**1.9  # km/h, rough shape only
    altitude = 0.0 if t < 0 else 0.0009 * burn**2.0  # km
    fuel = 1.0 if t < 0 else max(1.0 - burn / 170.0, 0.0)
    pitch = 0.0 if t < 10 else min(90.0, 90.0 * (1.0 - math.exp(-(burn - 10.0) / 90.0)))
    ignition = t >= -3.0
    downrange_km = 0.0 if t < 0 else 0.55 / 2.9 * burn**2.9 / 3600.0  # the distance the made-up speed adds up to
    return Telemetry(
        t=t,
        latitude_deg=MOCK_PAD_LATITUDE,
        longitude_deg=MOCK_PAD_LONGITUDE + downrange_km / (111.2 * math.cos(math.radians(MOCK_PAD_LATITUDE))),  # due east
        speed_kmh=speed,
        altitude_km=altitude,
        fuel_fraction=fuel,
        pitch_deg=pitch,
        engines_on=33 if ignition and fuel > 0 else 0,
        engines_total=33,
        source=DataSource.MOCK,
        heading_deg=90.0,  # the made-up ascent heads due east, without rolling
        roll_deg=0.0,
    )


MOCK_FULL_THRUST_N = 18_900_000.0  # a 33-engine cluster of the size of the user's booster; only a stand-in
MOCK_BURN_START = 0.0  # the made-up static fire lights at T-0 ...
MOCK_BURN_SECONDS = 10.0  # ... and runs this long
MOCK_SPOOL_SECONDS = 2.5  # the thrust takes this long to build up
MOCK_LIGHT_SECONDS = 1.2  # the engines light one after another over this long
MOCK_FUEL_PER_SECOND = 0.012


def mock_pad_telemetry(t: float) -> Telemetry:
    """A clearly made-up static fire on the pad: the engines light at T-0, build up to full thrust, hold, then shut down.

    Always tagged MOCK; never a stand-in for kRPC data. The vehicle stands still and upright.
    """
    burn = t - MOCK_BURN_START
    running = 0.0 <= burn < MOCK_BURN_SECONDS
    ramp = min(max(burn / MOCK_SPOOL_SECONDS, 0.0), 1.0) if running else 0.0
    lit = round(33 * min(max(burn / MOCK_LIGHT_SECONDS, 0.0), 1.0)) if running else 0
    spent = min(max(burn, 0.0), MOCK_BURN_SECONDS)
    return Telemetry(
        t=t,
        speed_kmh=0.0,
        altitude_km=0.0,
        fuel_fraction=1.0 - MOCK_FUEL_PER_SECOND * spent,
        pitch_deg=0.0,
        engines_on=lit,
        engines_total=33,
        source=DataSource.MOCK,
        latitude_deg=MOCK_PAD_LATITUDE,
        longitude_deg=MOCK_PAD_LONGITUDE,
        heading_deg=90.0,
        roll_deg=0.0,
        thrust_n=MOCK_FULL_THRUST_N * (lit / 33) * ramp,  # fewer engines lit, less thrust
        max_thrust_n=MOCK_FULL_THRUST_N,
        throttle=1.0 if running else 0.0,
    )
