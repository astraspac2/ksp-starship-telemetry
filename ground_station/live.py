"""Turn kRPC reader output into what the bar shows, including honest no-signal/stale/lost states.

Qt-free so it can be unit-tested.
"""

from .clock import COUNTDOWN_HOLD, CountdownClock, has_launched  # noqa: F401  (re-exported for callers)
from .krpc_source import ConnState, ReaderStatus
from .source import DataSource
from .telemetry import Telemetry


def status_text(status: ReaderStatus) -> str | None:
    if status.state is ConnState.CONNECTED and not status.stale:
        return None
    if status.state is ConnState.DISCONNECTED:
        return "NOT CONNECTED"
    if status.state is ConnState.CONNECTED:
        return f"STALE {status.age:.1f}S" if status.age is not None else "NO DATA"
    if status.state is ConnState.LOST:
        return "SIGNAL LOST"
    return "NO SIGNAL"


def live_telemetry(clock: CountdownClock, status: ReaderStatus) -> Telemetry:
    t = clock.t(status)
    sample = status.sample
    if sample is None:
        return Telemetry(t, None, None, None, None, 0, 0, DataSource.LIVE, status_text(status))
    return Telemetry(
        t=t,
        speed_kmh=sample.speed_ms * 3.6,
        altitude_km=sample.altitude_m / 1000.0,
        fuel_fraction=sample.fuel_fraction,
        pitch_deg=90.0 - sample.pitch_deg,  # kRPC pitch is above the horizon; the dial wants tilt from vertical
        engines_on=sample.engines_on,
        engines_total=sample.engines_total,
        source=DataSource.LIVE,
        status=status_text(status),
        engine_lit=sample.nozzles_lit,
        heading_deg=sample.heading_deg,
        roll_deg=sample.roll_deg,
        latitude_deg=sample.latitude_deg,
        longitude_deg=sample.longitude_deg,
        thrust_n=sample.thrust_n,
        max_thrust_n=sample.max_thrust_n,
        throttle=sample.throttle,
    )
