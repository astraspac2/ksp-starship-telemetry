"""Live telemetry from KSP through kRPC (read-only: nothing here sends a flight command).

The reader runs on a background thread, keeps the newest sample, and reports honestly when
it is not connected or when its data has gone stale.
"""

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from . import sep_cluster
from .branding import KRPC_CLIENT_NAME
from .attitude import attitude_from_rotation

STALE_AFTER_SECONDS = 1.0
RETRY_SECONDS = 2.0
VESSEL_CHECK_SECONDS = 1.0
DEFAULT_PROPELLANTS = ("LiquidFuel", "Oxidizer")
FUEL_FLOW_WINDOW = 0.5  # seconds of tank readings the fuel flow is measured over
FUEL_FLOW_MIN_SPAN = 0.25  # and the least span that gives a trustworthy rate
MIN_NOZZLE_THRUST_N = 1000.0  # below this per nozzle an "engine" is a placeholder, not propulsion
EXTRAS_SECONDS = 0.5  # maneuver nodes and the re-entry prediction are read this often; they change slowly
REENTRY_ALTITUDE_M = 70_000.0  # where the re-entry prediction looks for the vessel coming down


class ConnState(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    LOST = "LOST"


@dataclass(frozen=True)
class LiveSample:
    met: float  # mission elapsed time reported by KSP, seconds
    speed_ms: float  # surface speed
    altitude_m: float  # above terrain
    fuel_fraction: float  # propellant left in the current stage's tanks, 0..1
    pitch_deg: float  # degrees above the horizon, 90 = vertical
    engines_on: int  # nozzles lit in the current stage
    engines_total: int  # nozzles in the current stage
    situation: str
    received_at: float  # monotonic time the sample was read
    nozzles_lit: tuple[bool, ...] = ()  # per nozzle, inner engine groups first
    ut: float | None = None  # KSP universal time, seconds: game time, so it slows when the game lags
    warp_rate: float = 1.0  # KSP time warp multiplier; above 1 game time runs faster than real time
    heading_deg: float | None = None  # compass heading of the nose, 0 = north, 90 = east
    roll_deg: float | None = None  # roll about the nose axis
    latitude_deg: float | None = None  # where the vessel is over the body it orbits
    longitude_deg: float | None = None
    node_uts: tuple[float, ...] = ()  # game time of each maneuver node the operator has planned
    apoapsis_km: float | None = None  # of the current orbit, above sea level
    periapsis_km: float | None = None
    reentry_ut: float | None = None  # game time the orbit will next come down through 70 km, if it dips that low
    thrust_n: float | None = None  # total thrust of the engines being flown, in newtons; None = burning but not known
    max_thrust_n: float | None = None  # what those engines would give at full throttle; None = not known
    throttle: float | None = None  # the throttle setting, 0..1


@dataclass(frozen=True)
class ReaderStatus:
    state: ConnState
    sample: LiveSample | None
    age: float | None  # seconds since the last sample, None if there has been none
    error: str | None
    server_version: str | None = None  # kRPC server version once connected

    @property
    def stale(self) -> bool:
        return self.state is ConnState.CONNECTED and (self.age is None or self.age > STALE_AFTER_SECONDS)


def current_stage_group(active: list[bool], stages: list[tuple[int, int]]) -> int | None:
    """Decouple stage of the stage currently flying, from each engine's (activation, decouple) stage.

    Tanks and engines dropped together share a decouple stage, so this picks out the fuel and
    engines of the current stage. While engines burn it is the burning group that drops first;
    before ignition it is the group that ignites first. None if the vessel has no engines.
    """
    if not stages:
        return None
    burning = [decouple for on, (_, decouple) in zip(active, stages) if on]
    if burning:
        return max(burning)
    first_to_fire = max(activation for activation, _ in stages)
    return max(decouple for activation, decouple in stages if activation == first_to_fire)


def counts_as_engine(activation_stage: int, propellants: list[str], max_vacuum_thrust_n: float, nozzles: int) -> bool:
    """Leave out engine parts that are not real engines for the dial.

    A launch tower or clamp can register as an engine but burns nothing; a part that staging
    never activates (stage -1, e.g. a ship core with built-in nozzles next to separately
    fitted engines) would double-count the ship's engines; and a near-zero-thrust engine
    (the SEP booster core's 13 nozzles rate 1 kN in total, while the cluster holds the real
    33) is a placeholder.
    """
    return (
        bool(propellants)
        and activation_stage >= 0
        and max_vacuum_thrust_n / max(nozzles, 1) >= MIN_NOZZLE_THRUST_N
    )


def stage_propellants(engine_propellants: list[list[str]], all_engines: list[list[str]] | None = None) -> list[str]:
    """Resources the stage's engines burn (e.g. LqdMethane + Oxidizer on modded Starships).

    If this stage's engines report nothing (a cluster switched to another mode can), the other engines on
    the vessel say what is burned; failing that, stock LiquidFuel + Oxidizer.
    """
    for source in (engine_propellants, all_engines or []):
        names = sorted({name for names in source for name in names})
        if names:
            return names
    return list(DEFAULT_PROPELLANTS)


class _Streams:
    """Streams for one vessel. Rebuilt whenever the active vessel changes."""

    def __init__(self, conn, altitude_mode: Callable[[], str] = lambda: "surface", rated_memory: dict[str, float] | None = None):
        self._altitude_mode = altitude_mode
        self._rated_memory = rated_memory if rated_memory is not None else {}  # a cluster engine's full-throttle thrust, kept across rebuilds
        self._conn = conn
        vessel = self._vessel = conn.space_center.active_vessel
        self.vessel_name = vessel.name
        # Speed against the rotating planet; attitude as the vessel's rotation against the local horizon (kRPC's
        # pitch/heading/roll angles mix up the roll when the rocket stands upright, and the body frame gives a pitch
        # that is not "above the horizon", which tipped the dial's rocket over).
        flight = vessel.flight(vessel.orbit.body.reference_frame)
        self.met = conn.add_stream(getattr, vessel, "met")
        self.ut = conn.add_stream(getattr, conn.space_center, "ut")
        self.warp_rate = conn.add_stream(getattr, conn.space_center, "warp_rate")
        self.speed = conn.add_stream(getattr, flight, "speed")
        self.altitude_surface = conn.add_stream(getattr, flight, "surface_altitude")  # above the ground/sea
        self.altitude_sea = conn.add_stream(getattr, flight, "mean_altitude")  # above sea level
        self.rotation = conn.add_stream(vessel.rotation, vessel.surface_reference_frame)
        self.latitude = conn.add_stream(getattr, flight, "latitude")
        self.longitude = conn.add_stream(getattr, flight, "longitude")
        orbit = vessel.orbit
        self.apoapsis = conn.add_stream(getattr, orbit, "apoapsis_altitude")
        self.periapsis = conn.add_stream(getattr, orbit, "periapsis_altitude")
        self._extras_at: float | None = None
        self._extras: tuple[tuple[float, ...], float | None] = ((), None)
        self.situation = conn.add_stream(getattr, vessel, "situation")
        self.current_stage = conn.add_stream(getattr, vessel.control, "current_stage")
        self.built_at_stage = self.current_stage()
        engines, switches = [], []
        for e in vessel.parts.engines:
            # A SEP cluster is always an engine, whatever its first module says: once the outer engines are
            # switched off that module reports no thrust, which would wrongly drop the whole cluster.
            switch = next((m for m in e.part.modules if m.name == sep_cluster.SWITCH_MODULE), None)
            if switch is not None or counts_as_engine(e.part.stage, list(e.propellant_names), e.max_vacuum_thrust, len(e.thrusters)):
                engines.append(e)
                switches.append(switch)
        self.engine_stages = [(e.part.stage, e.part.decouple_stage) for e in engines]
        # One engine part can hold many nozzles (a 33-engine cluster part); count nozzles, not parts.
        self.engine_nozzles = [max(len(e.thrusters), 1) for e in engines]
        self.throttle = conn.add_stream(getattr, vessel.control, "throttle")
        # SEP clusters: kRPC sees only one engine group, so follow the switch's mode name and total thrust.
        self.sep: dict[int, tuple] = {}
        self.sep_available: dict[int, Callable[[], float]] = {}
        self.sep_key: dict[int, str] = {}
        for i, (e, switch) in enumerate(zip(engines, switches)):
            if switch is None:
                continue
            self.sep_available[i] = conn.add_stream(getattr, e, "available_thrust")
            self.sep_key[i] = f"{vessel.name}|{e.part.title}"
            self.sep[i] = (
                conn.add_stream(switch.get_field, "Thrust"),
                conn.add_stream(switch.get_field, "Mode"),
                conn.add_stream(getattr, e, "thrust"),
                conn.add_stream(getattr, e, "max_thrust"),
                self.engine_nozzles[i],
            )
            self.engine_nozzles[i] = sep_cluster.CLUSTER_ENGINES
        self.engine_propellants = [list(e.propellant_names) for e in engines]
        # Every engine on the vessel, including ones left out of the dial, tells what the vessel burns.
        self.vessel_propellants = [list(e.propellant_names) for e in vessel.parts.engines]
        self.engine_active = [conn.add_stream(getattr, e, "active") for e in engines]
        self.engine_has_fuel = [conn.add_stream(getattr, e, "has_fuel") for e in engines]
        self.engine_thrust = [conn.add_stream(getattr, e, "thrust") for e in engines]
        self.engine_available = [conn.add_stream(getattr, e, "available_thrust") for e in engines]
        self.stage_group: int | None = None
        self.fuel: list[tuple] | None = None
        self._fuel_history: deque[tuple[float, float]] = deque()
        self._flow = 0.0
        self.refresh_stage()

    def _in_stage(self) -> list[int]:
        return [
            i for i, (_, decouple) in enumerate(self.engine_stages) if self.stage_group is None or decouple == self.stage_group
        ]

    def refresh_stage(self) -> None:
        """Point the fuel streams at the current stage's tanks; called again after staging."""
        group = current_stage_group([a() for a in self.engine_active], self.engine_stages)
        if self.fuel is not None and group == self.stage_group:
            return
        for amount, maximum in self.fuel or []:
            for stream in (amount, maximum):
                remove = getattr(stream, "remove", None)
                if remove:
                    remove()
        self.stage_group = group
        self._fuel_history.clear()  # a different set of tanks: the old readings say nothing about this one
        self._flow = 0.0
        if group is None:
            resources = self._vessel.resources
        else:
            resources = self._vessel.resources_in_decouple_stage(group, cumulative=False)
        names = stage_propellants([self.engine_propellants[i] for i in self._in_stage()], self.vessel_propellants)
        self.fuel = [
            (self._conn.add_stream(resources.amount, n), self._conn.add_stream(resources.max, n)) for n in names
        ]

    def _fuel_flow(self, now: float, amount: float) -> float:
        """Propellant leaving this stage's tanks, in units per second, measured over the last half second or so."""
        history = self._fuel_history
        history.append((now, amount))
        while len(history) > 1 and now - history[1][0] >= FUEL_FLOW_WINDOW:
            history.popleft()
        then, earlier = history[0]
        if now - then >= FUEL_FLOW_MIN_SPAN:
            self._flow = max((earlier - amount) / (now - then), 0.0)
        return self._flow

    def _sep_read(self, i: int, fuel_flow: float) -> tuple[tuple[bool, ...], float | None, float | None]:
        """A SEP cluster's lit engines, its total thrust and its full-throttle thrust (None where they cannot be known)."""
        total, mode, first_thrust, max_thrust, first_nozzles = self.sep[i]
        total_kn = sep_cluster.parse_thrust_kn(str(total()))
        first = first_thrust()
        producing = sep_cluster.is_producing(total_kn, first, fuel_flow)
        pattern = sep_cluster.lit_for_mode(str(mode()), producing)
        if pattern is None:
            # An unknown mode name (a different version of the part): estimate from thrust instead.
            engines = sep_cluster.engines_burning(total_kn, first, first_nozzles, max_thrust(), self.throttle())
            pattern = sep_cluster.lit_pattern(sep_cluster.lit_groups(engines))
        key = self.sep_key[i]
        each = sep_cluster.per_engine_rated_n(self.sep_available[i](), first_nozzles, self._rated_memory.get(key))
        if each is not None:
            self._rated_memory[key] = each
        thrust = sep_cluster.cluster_thrust_n(sum(pattern), producing, first, first_nozzles, total_kn, each, self.throttle())
        return pattern, thrust, None if each is None else each * sep_cluster.CLUSTER_ENGINES

    def _reentry_ut(self, ut: float) -> float | None:
        """Game time the orbit next comes down through 70 km, or None when it never gets that low (or is already below)."""
        orbit = self._vessel.orbit
        radius = orbit.body.equatorial_radius + REENTRY_ALTITUDE_M
        if not (orbit.periapsis < radius < orbit.apoapsis):
            return None
        anomaly = orbit.true_anomaly_at_radius(radius)  # on the way up; the way down is its mirror image
        crossing = orbit.ut_at_true_anomaly(2.0 * math.pi - anomaly)
        return crossing if crossing > ut else None

    def _read_extras(self, now: float, ut: float) -> tuple[tuple[float, ...], float | None]:
        if self._extras_at is None or now - self._extras_at >= EXTRAS_SECONDS:
            self._extras_at = now
            nodes = tuple(sorted(node.ut for node in self._vessel.control.nodes))
            try:
                reentry = self._reentry_ut(ut)
            except Exception:  # an orbit the maths cannot handle (escape, no orbit) just has no prediction
                reentry = None
            self._extras = (nodes, reentry)
        return self._extras

    def read(self, now: float) -> LiveSample:
        amount = sum(a() for a, _ in self.fuel)
        capacity = sum(m() for _, m in self.fuel)
        fuel_flow = self._fuel_flow(now, amount)
        # Smallest engine groups first so they land on the inner rings of the dial: on the SEP
        # booster that is the 13-nozzle core in the centre and the 20-nozzle cluster outside.
        in_stage = sorted(self._in_stage(), key=lambda i: self.engine_nozzles[i])
        lit: list[bool] = []
        thrust: float | None = 0.0  # None as soon as one engine's thrust cannot be known
        rated: float | None = 0.0
        for i in in_stage:
            if i in self.sep:
                pattern, part_thrust, part_rated = self._sep_read(i, fuel_flow)
                lit.extend(pattern)
            else:
                # "Active" only means the engine is enabled; with the throttle at zero it is still active but not burning.
                part_thrust, part_rated = self.engine_thrust[i](), self.engine_available[i]()
                burning = self.engine_active[i]() and self.engine_has_fuel[i]() and part_thrust > 0
                lit.extend([burning] * self.engine_nozzles[i])
            thrust = None if thrust is None or part_thrust is None else thrust + part_thrust
            rated = None if rated is None or part_rated is None else rated + part_rated
        pitch, heading, roll = attitude_from_rotation(self.rotation())
        ut = self.ut()
        nodes, reentry_ut = self._read_extras(now, ut)
        apoapsis, periapsis = self.apoapsis(), self.periapsis()
        return LiveSample(
            met=self.met(),
            speed_ms=self.speed(),
            altitude_m=self.altitude_sea() if self._altitude_mode() == "sea" else self.altitude_surface(),
            fuel_fraction=(amount / capacity) if capacity > 0 else 0.0,
            pitch_deg=pitch,
            engines_on=sum(lit),
            engines_total=len(lit),
            nozzles_lit=tuple(lit),
            ut=ut,
            warp_rate=self.warp_rate(),
            heading_deg=heading,
            roll_deg=roll,
            latitude_deg=self.latitude(),
            longitude_deg=self.longitude(),
            node_uts=nodes,
            apoapsis_km=apoapsis / 1000.0 if math.isfinite(apoapsis) else None,
            periapsis_km=periapsis / 1000.0 if math.isfinite(periapsis) else None,
            reentry_ut=reentry_ut,
            thrust_n=thrust,
            max_thrust_n=rated if rated else None,
            throttle=self.throttle(),
            situation=str(getattr(self.situation(), "name", self.situation())),
            received_at=now,
        )


class KrpcReader:
    def __init__(
        self,
        address: str = "127.0.0.1",
        rpc_port: int = 50000,
        stream_port: int = 50001,
        connect_fn: Callable | None = None,
        clock: Callable[[], float] = time.monotonic,
        poll_interval: float = 0.05,
        retry_seconds: float = RETRY_SECONDS,
    ):
        self._address, self._rpc_port, self._stream_port = address, rpc_port, stream_port
        self._connect_fn = connect_fn or self._default_connect
        self._clock = clock
        self._poll_interval = poll_interval
        self._retry_seconds = retry_seconds
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = ConnState.DISCONNECTED
        self._sample: LiveSample | None = None
        self._error: str | None = None
        self._server_version: str | None = None
        self.altitude_mode = "surface"  # "surface" (above ground/sea) or "sea" (above sea level); may change while running
        self._rated_memory: dict[str, float] = {}

    def _default_connect(self):
        import krpc

        return krpc.connect(
            name=KRPC_CLIENT_NAME,
            address=self._address,
            rpc_port=self._rpc_port,
            stream_port=self._stream_port,
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="krpc-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._set(ConnState.DISCONNECTED, None)

    def snapshot(self) -> ReaderStatus:
        with self._lock:
            sample = self._sample
            age = None if sample is None else self._clock() - sample.received_at
            return ReaderStatus(self._state, sample, age, self._error, self._server_version)

    def _set(self, state: ConnState, error: str | None) -> None:
        with self._lock:
            self._state, self._error = state, error

    def _run(self) -> None:
        while not self._stop.is_set():
            conn = None
            if self._state is ConnState.DISCONNECTED:
                self._set(ConnState.CONNECTING, None)  # a LOST feed stays LOST until a new connection succeeds
            if self._state is ConnState.CONNECTING and self._error is None:
                self._set(
                    ConnState.CONNECTING,
                    f"waiting for kRPC at {self._address}:{self._rpc_port} "
                    "(if KSP shows a kRPC 'allow connection' prompt, accept it)",
                )
            try:
                conn = self._connect_fn()
                self._poll(conn)
            except Exception as exc:  # any failure leaves the reader honest about it
                had_feed = self._state in (ConnState.CONNECTED, ConnState.LOST)
                message = f"{type(exc).__name__}: {exc}"
                if had_feed:
                    self._set(ConnState.LOST, message)
                else:
                    self._set(
                        ConnState.CONNECTING,
                        f"kRPC not reachable at {self._address}:{self._rpc_port} "
                        f"(is the kRPC server started in KSP?) - {message}",
                    )
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
            self._stop.wait(self._retry_seconds)

    def _read_server_version(self, conn) -> str | None:
        try:
            return str(conn.krpc.get_status().version)
        except Exception:  # only a label for the operator; a missing version must not stop the telemetry
            return None

    def _poll(self, conn) -> None:
        streams = _Streams(conn, lambda: self.altitude_mode, self._rated_memory)
        with self._lock:
            self._server_version = self._read_server_version(conn)
        self._set(ConnState.CONNECTED, None)
        last_check = self._clock()
        while not self._stop.is_set():
            now = self._clock()
            if now - last_check >= VESSEL_CHECK_SECONDS:
                last_check = now
                vessel_changed = conn.space_center.active_vessel.name != streams.vessel_name
                if vessel_changed or streams.current_stage() != streams.built_at_stage:
                    streams = _Streams(conn, lambda: self.altitude_mode, self._rated_memory)  # staging drops parts: read afresh
                else:
                    streams.refresh_stage()
            sample = streams.read(now)
            with self._lock:
                self._sample = sample
            self._stop.wait(self._poll_interval)
