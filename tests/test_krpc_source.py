import time
from types import SimpleNamespace

import pytest
from attitude_helpers import quaternion_from_axes
from ground_station.render3d import body_to_world

from ground_station.krpc_source import (
    STALE_AFTER_SECONDS,
    ConnState,
    KrpcReader,
    counts_as_engine,
    current_stage_group,
    stage_propellants,
)


METHALOX = ["LqdMethane", "Oxidizer"]


@pytest.mark.parametrize(
    "stage, propellants, rated, nozzles, expected",
    [
        (2, METHALOX, 11464202.0, 20, True),  # Andrada booster cluster
        (1, [], 1000.0, 1, False),  # Starship Orbital Launch Tower 2 reports as an engine with no propellant
        (-1, METHALOX, 1002.0, 6, False),  # Donnager ship core: never staged, would double-count
        (0, METHALOX, 1001.0, 13, False),  # Behemoth core: 13 placeholder nozzles, 1 kN in total
    ],
)
def test_counts_as_engine(stage, propellants, rated, nozzles, expected):
    assert counts_as_engine(stage, propellants, rated, nozzles) is expected


@pytest.mark.parametrize(
    "mode, lit_count, middle_lit, centre_lit",
    [
        ("Outer Twenty", 33, 10, 3),
        ("Middle Eight", 13, 10, 3),
        ("Middle Two", 5, 2, 3),
        ("Center Three", 3, 0, 3),
    ],
)
def test_inner_engine_modes_light_exactly_their_engines_even_when_the_first_module_goes_blank(
    mode, lit_count, middle_lit, centre_lit
):
    reader = make_reader(lambda: FakeConn(sep_booster=True, sep_mode=mode, sep_thrust="7421.5", dead_first_module=True))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        sample = reader.snapshot().sample
        assert sample.engines_total == 33  # the cluster is not dropped when its first module reports nothing
        assert sample.engines_on == lit_count
        lit = sample.nozzles_lit
        assert sum(lit[:3]) == centre_lit and sum(lit[3:13]) == middle_lit and sum(lit[13:]) == (20 if lit_count == 33 else 0)
        assert sample.fuel_fraction == pytest.approx(1.0)  # still reads the booster's methalox tanks
    finally:
        reader.stop()


def test_a_normal_burn_with_the_part_window_closed_lights_all_33():
    """Recorded: the switch's Thrust field sat at 0 during a full-throttle burn while the engine module read 11.4 MN."""
    reader = make_reader(lambda: FakeConn(sep_booster=True, sep_mode="Outer Twenty", sep_thrust="0"))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        sample = reader.snapshot().sample
        assert sample.engines_on == 33  # the engine module's own thrust says it is burning
    finally:
        reader.stop()


@pytest.mark.parametrize("mode, lit_count", [("Middle Eight", 13), ("Middle Two", 5), ("Center Three", 3)])
def test_inner_modes_light_from_the_tanks_emptying_when_everything_else_reads_zero(mode, lit_count):
    factory = lambda: FakeConn(  # noqa: E731
        sep_booster=True, sep_mode=mode, sep_thrust="0", dead_first_module=True, fuel_burn_rate=3000.0
    )
    reader = make_reader(factory)
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None and reader.snapshot().sample.engines_on == lit_count)
    finally:
        reader.stop()


def test_nothing_burning_and_nothing_reading_means_all_dim():
    reader = make_reader(lambda: FakeConn(sep_booster=True, sep_mode="Middle Eight", sep_thrust="0", dead_first_module=True))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        time.sleep(0.6)  # long enough for a flow reading
        assert reader.snapshot().sample.engines_on == 0
    finally:
        reader.stop()


def test_a_cluster_with_no_thrust_shows_all_33_dim_whatever_its_mode():
    reader = make_reader(lambda: FakeConn(sep_booster=True, sep_mode="Middle Eight", sep_thrust="0", dead_first_module=True))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        sample = reader.snapshot().sample
        assert sample.engines_total == 33 and sample.engines_on == 0
    finally:
        reader.stop()


def test_an_unknown_mode_name_falls_back_to_estimating_from_thrust():
    reader = make_reader(lambda: FakeConn(sep_booster=True, sep_mode="Something New"))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        assert reader.snapshot().sample.engines_on == 33  # the recorded static-fire thrust works out to all 33
    finally:
        reader.stop()


def test_sep_booster_static_fire_lights_all_33():
    reader = make_reader(lambda: FakeConn(sep_booster=True))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        sample = reader.snapshot().sample
        assert sample.engines_total == 33 and sample.engines_on == 33
        assert sample.fuel_fraction == pytest.approx(1.0)
    finally:
        reader.stop()


def test_stage_propellants_follow_the_engines():
    assert stage_propellants([["LqdMethane", "Oxidizer"], ["Oxidizer", "LqdMethane"]]) == ["LqdMethane", "Oxidizer"]


def test_stage_propellants_fall_back_to_stock():
    assert stage_propellants([[]]) == ["LiquidFuel", "Oxidizer"]


def test_stage_propellants_use_the_rest_of_the_vessel_when_the_stage_reports_none():
    assert stage_propellants([[]], [[], ["LqdMethane", "Oxidizer"]]) == ["LqdMethane", "Oxidizer"]



BOOSTER_AND_SHIP = [(3, 2), (3, 2), (1, 0)]  # (activation stage, decouple stage) per engine


@pytest.mark.parametrize(
    "active, expected",
    [
        ([False, False, False], 2),  # on the pad: the group that ignites first
        ([True, True, False], 2),  # booster burning
        ([False, False, True], 0),  # after separation only the ship's engine burns
    ],
)
def test_current_stage_group(active, expected):
    assert current_stage_group(active, BOOSTER_AND_SHIP) == expected


def test_current_stage_group_without_engines():
    assert current_stage_group([], []) is None


class FakeConn:
    """Stands in for a kRPC connection: add_stream returns a callable that re-reads the value."""

    def __init__(
        self,
        fail_after: int | None = None,
        sep_booster: bool = False,
        sep_mode: str = "Outer Twenty",
        sep_thrust: str = "18903.29",
        dead_first_module: bool = False,
        fuel_burn_rate: float = 0.0,
        node_uts: tuple[float, ...] = (),
        orbit_km: tuple[float, float] = (-6000.0, 80.0),
    ):
        self.reads = 0
        self.sep_fields: dict[str, str] = {}
        started = time.monotonic()
        self.fail_after = fail_after
        self.closed = False

        def engine(active, has_fuel, activation, decouple, nozzles, propellants, rated=1e6, thrust=1e5, modules=()):
            part = SimpleNamespace(stage=activation, decouple_stage=decouple, modules=list(modules), title=f"Engine {activation}/{decouple}/{nozzles}")
            return SimpleNamespace(
                active=active,
                has_fuel=has_fuel,
                part=part,
                thrusters=[object()] * nozzles,
                propellant_names=propellants,
                max_vacuum_thrust=rated,
                max_thrust=rated,
                available_thrust=rated,
                thrust=thrust,
            )

        def tanks(contents):
            return SimpleNamespace(
                amount=lambda name: contents.get(name, (0.0, 0.0))[0],
                max=lambda name: contents.get(name, (0.0, 0.0))[1],
            )

        # Two-stage modded rocket on methalox: the booster is one 33-nozzle cluster part plus a
        # single engine that has flamed out; the ship's six engines are not lit yet.
        methalox = ["LqdMethane", "Oxidizer"]
        engines = [
            engine(True, True, 3, 2, 33, methalox),
            engine(True, False, 3, 2, 1, methalox),
            engine(False, True, 1, 0, 6, methalox),
            engine(True, True, 2, 2, 1, []),  # launch tower: registers as an engine, burns nothing
            engine(False, True, -1, 0, 6, methalox),  # ship core that staging never activates
        ]
        if sep_booster:
            # Your SEP booster as recorded during the pad static fire: the cluster part fires all
            # 33 while kRPC reads only its 20-engine first group; the core's 13 nozzles are a
            # 1 kN placeholder.
            fields = {"Thrust": sep_thrust, "Mode": sep_mode}
            self.sep_fields = fields  # a test can change the mode or the part window's thrust while the reader runs
            switch = SimpleNamespace(name="ModuleSEPEngineSwitch", get_field=lambda name: fields[name])
            if dead_first_module:
                # With the outer engines switched off, the module kRPC reads reports nothing at all: no
                # thrust, no rating, no propellants and not even "active".
                cluster = engine(False, False, 2, 0, 8, [], rated=0.0, thrust=0.0, modules=[switch])
            else:
                cluster = engine(True, True, 2, 0, 20, methalox, rated=11464202.0, thrust=11456537.0, modules=[switch])
            engines = [
                cluster,
                engine(False, True, 0, 0, 13, methalox, rated=1001.0),
                engine(False, True, 1, 1, 1, []),  # launch tower
            ]
        stage_tanks = {
            2: tanks({"LqdMethane": (300.0, 600.0), "Oxidizer": (150.0, 300.0), "LiquidFuel": (0.0, 0.0)}),
            0: tanks({"LqdMethane": (100.0, 100.0), "Oxidizer": (100.0, 100.0)}),
        }
        if sep_booster:
            stage_tanks[0] = tanks({"LqdMethane": (348919.0, 348919.0), "Oxidizer": (116306.0, 116306.0)})
            if fuel_burn_rate:  # the booster's tanks are emptying, as in a burn
                stage_tanks[0] = SimpleNamespace(
                    amount=lambda name: 348919.0 - fuel_burn_rate * (time.monotonic() - started)
                    if name == "LqdMethane"
                    else 116306.0,
                    max=lambda name: 348919.0 if name == "LqdMethane" else 116306.0,
                )
        whole = tanks({"LqdMethane": (400.0, 700.0), "Oxidizer": (250.0, 400.0)})
        surface_frame = object()
        body_frame = object()
        flights = {
            body_frame: SimpleNamespace(
                speed=120.0, surface_altitude=2500.0, mean_altitude=2570.0, pitch=10.0, heading=200.0, roll=33.0, latitude=28.5, longitude=-80.6
            ),
        }
        self.vessel = SimpleNamespace(
            name="Test Rocket",
            met=12.5,
            situation=SimpleNamespace(name="flying"),
            orbit=self._orbit(body_frame, *orbit_km),
            surface_reference_frame=surface_frame,
            rotation=lambda frame: quaternion_from_axes(*_axes_for(80.0, 96.4, -12.5)),
            resources=whole,
            resources_in_decouple_stage=lambda stage, cumulative: stage_tanks[stage],
            parts=SimpleNamespace(engines=engines),
            control=SimpleNamespace(current_stage=3, throttle=1.0, nodes=[SimpleNamespace(ut=u) for u in node_uts]),
            flight=lambda frame: flights[frame],
        )
        self.space_center = SimpleNamespace(active_vessel=self.vessel, ut=1000.0, warp_rate=1.0)
        self.krpc = SimpleNamespace(get_status=lambda: SimpleNamespace(version="0.6.0"))

    @staticmethod
    def _orbit(body_frame, periapsis_altitude_km: float, apoapsis_altitude_km: float):
        """A circular-ish orbit round a 600 km body, enough for the re-entry prediction: it crosses 85 km at UT 1500."""
        radius = 600_000.0
        return SimpleNamespace(
            body=SimpleNamespace(reference_frame=body_frame, equatorial_radius=radius),
            apoapsis_altitude=apoapsis_altitude_km * 1000.0,
            periapsis_altitude=periapsis_altitude_km * 1000.0,
            apoapsis=radius + apoapsis_altitude_km * 1000.0,
            periapsis=radius + periapsis_altitude_km * 1000.0,
            true_anomaly_at_radius=lambda r: 1.0,
            ut_at_true_anomaly=lambda anomaly: 1500.0,
        )

    def add_stream(self, func, *args):
        def read():
            self.reads += 1
            if self.fail_after is not None and self.reads > self.fail_after:
                raise ConnectionError("connection dropped")
            return func(*args)

        return read

    def close(self):
        self.closed = True


def wait_for(predicate, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def make_reader(connect_fn, **kwargs):
    return KrpcReader(connect_fn=connect_fn, poll_interval=0.01, retry_seconds=0.05, **kwargs)


def test_reads_a_live_sample():
    reader = make_reader(lambda: FakeConn())
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        status = reader.snapshot()
        assert status.state is ConnState.CONNECTED
        sample = status.sample
        assert sample.met == 12.5
        assert sample.speed_ms == 120.0
        assert sample.altitude_m == 2500.0
        assert sample.speed_ms == 120.0  # surface speed from the planet frame
        assert sample.fuel_fraction == pytest.approx(0.5)  # booster methalox only, not the whole vessel
        assert (sample.latitude_deg, sample.longitude_deg) == (28.5, -80.6)
        assert sample.pitch_deg == pytest.approx(80.0)  # above the local horizon, not the planet-frame value
        assert sample.heading_deg == pytest.approx(96.4) and sample.roll_deg == pytest.approx(-12.5)  # from the vessel's rotation
        assert sample.engines_on == 33 and sample.engines_total == 34  # nozzles, not parts; tower left out
        assert sample.nozzles_lit == (False,) + (True,) * 33  # smaller engine group first (inner rings)
        assert sample.situation == "flying"
    finally:
        reader.stop()


def test_altitude_mode_picks_ground_or_sea_level():
    reader = make_reader(lambda: FakeConn())
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        assert reader.snapshot().sample.altitude_m == 2500.0
        reader.altitude_mode = "sea"
        assert wait_for(lambda: reader.snapshot().sample.altitude_m == 2570.0)
    finally:
        reader.stop()


def test_server_version_is_reported_once_connected():
    reader = make_reader(lambda: FakeConn())
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        assert reader.snapshot().server_version == "0.6.0"
    finally:
        reader.stop()


def test_unreachable_server_is_reported_not_hidden():
    def refuse():
        raise ConnectionRefusedError("refused")

    reader = make_reader(refuse)
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().error is not None)
        status = reader.snapshot()
        assert status.state is ConnState.CONNECTING
        assert status.sample is None
        assert "kRPC server" in status.error
    finally:
        reader.stop()


def test_dropped_connection_is_lost_and_old_sample_ages():
    attempts = []

    def connect():
        attempts.append(1)
        if len(attempts) > 1:
            raise ConnectionRefusedError("server gone")
        return FakeConn(fail_after=35)  # a few samples, then the connection drops

    reader = make_reader(connect)
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().state is ConnState.LOST)
        status = reader.snapshot()
        assert "ConnectionError" in status.error
        assert status.sample is not None  # kept, but its age keeps growing so the UI can grey it out
        first_age = status.age
        time.sleep(0.05)
        assert reader.snapshot().age > first_age
    finally:
        reader.stop()


def test_stale_flag_follows_sample_age():
    now = [100.0]
    reader = KrpcReader(connect_fn=lambda: FakeConn(), clock=lambda: now[0], poll_interval=0.01, retry_seconds=0.05)
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        reader.stop()
        reader._state = ConnState.CONNECTED  # the feed is considered up but silent
        now[0] += STALE_AFTER_SECONDS + 0.5
        assert reader.snapshot().stale
        now[0] = reader.snapshot().sample.received_at + 0.1
        assert not reader.snapshot().stale
    finally:
        reader.stop()


def _axes_for(pitch, heading, roll):
    m = body_to_world(pitch, heading, roll)
    return tuple(m[:, 0]), tuple(m[:, 1]), tuple(m[:, 2])


def test_reads_maneuver_nodes_and_the_orbit():
    reader = make_reader(lambda: FakeConn(node_uts=(1900.0, 1200.0), orbit_km=(110.0, 150.0)))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        sample = reader.snapshot().sample
        assert sample.node_uts == (1200.0, 1900.0)  # soonest first
        assert (sample.apoapsis_km, sample.periapsis_km) == (150.0, 110.0)
        assert sample.reentry_ut is None  # the orbit stays above 85 km
    finally:
        reader.stop()


def test_predicts_when_a_dipping_orbit_comes_down_through_85_km():
    reader = make_reader(lambda: FakeConn(orbit_km=(-6000.0, 150.0)))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        assert reader.snapshot().sample.reentry_ut == 1500.0
    finally:
        reader.stop()


def test_no_nodes_and_no_orbit_figures_are_just_empty():
    reader = make_reader(lambda: FakeConn(orbit_km=(float("nan"), float("nan"))))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        sample = reader.snapshot().sample
        assert sample.node_uts == () and sample.apoapsis_km is None and sample.reentry_ut is None
    finally:
        reader.stop()


RECORDED_FIRST_GROUP_THRUST_N = 11456537.0  # the static fire: the 20 engines kRPC reads, at full throttle
RECORDED_FIRST_GROUP_RATED_N = 11464202.0
RECORDED_CLUSTER_TOTAL_KN = 18903.29  # what the part window's Thrust field said for all 33


def test_a_plain_rocket_reports_the_thrust_of_its_current_stage_and_the_throttle():
    reader = make_reader(lambda: FakeConn())
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        sample = reader.snapshot().sample
        assert sample.thrust_n == pytest.approx(2 * 1e5) and sample.max_thrust_n == pytest.approx(2 * 1e6)  # the two engines of the stage
        assert sample.throttle == 1.0
    finally:
        reader.stop()


def test_the_booster_cluster_thrust_comes_out_at_the_recorded_total_for_all_33():
    reader = make_reader(lambda: FakeConn(sep_booster=True))
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        sample = reader.snapshot().sample
        assert sample.thrust_n / 1000.0 == pytest.approx(RECORDED_CLUSTER_TOTAL_KN, rel=1e-4)  # 33 engines worked out from the 20 kRPC reads
        assert sample.max_thrust_n == pytest.approx(33 * RECORDED_FIRST_GROUP_RATED_N / 20)
    finally:
        reader.stop()


def test_a_cluster_that_is_off_has_zero_thrust_but_still_a_full_throttle_rating():
    conn = FakeConn(sep_booster=True, sep_thrust="0")
    engine = conn.vessel.parts.engines[0]
    engine.thrust, engine.active = 0.0, False  # on the pad, not lit
    reader = make_reader(lambda: conn)
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        time.sleep(0.4)
        sample = reader.snapshot().sample
        assert sample.engines_on == 0 and sample.thrust_n == 0.0
        assert sample.max_thrust_n == pytest.approx(33 * RECORDED_FIRST_GROUP_RATED_N / 20)  # what 100 % would give, so the gauge has a scale
    finally:
        reader.stop()


def test_inner_modes_with_the_first_module_blank_report_no_thrust_rather_than_a_guess():
    factory = lambda: FakeConn(sep_booster=True, sep_mode="Middle Eight", sep_thrust="0", dead_first_module=True, fuel_burn_rate=3000.0)  # noqa: E731
    reader = make_reader(factory)
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None and reader.snapshot().sample.engines_on == 13)
        sample = reader.snapshot().sample
        assert sample.thrust_n is None and sample.max_thrust_n is None  # burning, but nothing says how hard
    finally:
        reader.stop()


def test_inner_modes_use_the_part_windows_total_when_it_is_open():
    factory = lambda: FakeConn(sep_booster=True, sep_mode="Middle Eight", sep_thrust="7421.5", dead_first_module=True)  # noqa: E731
    reader = make_reader(factory)
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None and reader.snapshot().sample.engines_on == 13)
        assert reader.snapshot().sample.thrust_n == pytest.approx(7421.5 * 1000.0)
    finally:
        reader.stop()


def test_a_full_throttle_rating_seen_earlier_is_kept_for_the_inner_modes():
    conn = FakeConn(sep_booster=True, fuel_burn_rate=3000.0)  # all 33 burning, first group readable
    reader = make_reader(lambda: conn)
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None and reader.snapshot().sample.max_thrust_n is not None)
        engine = conn.vessel.parts.engines[0]  # now the outer engines go off and the module reads nothing
        conn.sep_fields["Mode"], conn.sep_fields["Thrust"] = "Middle Eight", "0"
        engine.thrust = engine.available_thrust = engine.max_thrust = 0.0
        engine.active = engine.has_fuel = False
        per_engine = RECORDED_FIRST_GROUP_RATED_N / 20
        assert wait_for(lambda: reader.snapshot().sample.engines_on == 13 and reader.snapshot().sample.thrust_n is not None)
        sample = reader.snapshot().sample
        assert sample.thrust_n == pytest.approx(13 * per_engine * 1.0)  # 13 engines, full throttle
        assert sample.max_thrust_n == pytest.approx(33 * per_engine)
    finally:
        reader.stop()


def test_zero_throttle_means_zero_thrust():
    conn = FakeConn(sep_booster=True, sep_thrust="0")  # the part window reads zero too
    conn.vessel.control.throttle = 0.0
    engine = conn.vessel.parts.engines[0]
    engine.thrust = 0.0
    reader = make_reader(lambda: conn)
    reader.start()
    try:
        assert wait_for(lambda: reader.snapshot().sample is not None)
        time.sleep(0.4)
        sample = reader.snapshot().sample
        assert sample.thrust_n == 0.0 and sample.throttle == 0.0
    finally:
        reader.stop()
