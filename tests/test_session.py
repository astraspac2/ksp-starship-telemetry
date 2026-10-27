import pytest

from ground_station.clock import ClockState
from ground_station.krpc_source import ConnState, LiveSample, ReaderStatus
from ground_station.session import Session
from ground_station.settings import Settings
from ground_station.source import DataSource


class FakeReader:
    instances = []

    def __init__(self, address, rpc_port, stream_port):
        self.args = (address, rpc_port, stream_port)
        self.started = False
        self.stopped = False
        self.status = ReaderStatus(ConnState.CONNECTING, None, None, "waiting")
        FakeReader.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def snapshot(self):
        return self.status


def live_sample(ut, met=0.0, situation="pre_launch"):
    return LiveSample(met, 0.0, 28.0, 1.0, 90.0, 0, 33, situation, 0.0, ut=ut)


@pytest.fixture(autouse=True)
def _clear():
    FakeReader.instances.clear()


def make_session(source="LIVE", clock_source=None, **kwargs):
    settings = Settings(source=source, countdown_seconds=60.0, address=" 10.0.0.2 ", **kwargs)
    return Session(settings, reader_factory=FakeReader, game_time=clock_source or (lambda: 0.0))


def test_not_connected_is_stated_not_hidden():
    tel = make_session().telemetry()
    assert tel.status == "NOT CONNECTED"
    assert tel.speed_kmh is None and tel.source is DataSource.LIVE


def test_connect_starts_a_reader_with_the_settings_and_disconnect_stops_it():
    session = make_session()
    session.connect()
    reader = FakeReader.instances[0]
    assert reader.started and reader.args == ("10.0.0.2", 50000, 50001)
    session.connect()  # a second click must not open a second connection
    assert len(FakeReader.instances) == 1
    session.disconnect()
    assert reader.stopped and not session.connected


def test_live_countdown_waits_for_start_then_follows_game_time():
    session = make_session()
    session.connect()
    reader = FakeReader.instances[0]
    reader.status = ReaderStatus(ConnState.CONNECTED, live_sample(1000.0), 0.0, None)
    assert session.telemetry().t == -60.0  # idle until started
    session.start_countdown()
    session.telemetry()
    reader.status = ReaderStatus(ConnState.CONNECTED, live_sample(1015.0), 0.0, None)
    assert session.telemetry().t == pytest.approx(-45.0)


def test_mock_source_is_labelled_and_runs_through_zero():
    now = [100.0]
    session = make_session(source="MOCK", clock_source=lambda: now[0])
    session.set_countdown_seconds(10.0)
    session.start_countdown()
    session.telemetry()
    now[0] = 125.0
    tel = session.telemetry()
    assert tel.source is DataSource.MOCK
    assert tel.t == pytest.approx(15.0)


def test_switching_source_resets_the_clock():
    session = make_session()
    session.start_countdown()
    session.set_source(DataSource.MOCK)
    assert session.clock.state is ClockState.IDLE
    assert session.settings.source == "MOCK"


def test_countdown_time_can_only_change_while_idle():
    session = make_session()
    session.set_countdown_seconds(120.0)
    assert session.settings.countdown_seconds == 120.0
    session.start_countdown()
    session.set_countdown_seconds(30.0)
    assert session.settings.countdown_seconds == 120.0


def test_markers_are_stamped_manual_at_the_current_time_and_sorted_in():
    session = make_session()
    session.connect()
    reader = FakeReader.instances[0]
    session.start_countdown()
    for ut in (1000.0, 1040.0):
        reader.status = ReaderStatus(ConnState.CONNECTED, live_sample(ut), 0.0, None)
        session.telemetry()
    marker = session.add_marker("  clamp release  ")
    assert marker.name == "CLAMP RELEASE" and marker.manual and marker.time == pytest.approx(-20.0)
    names = [m.name for m in session.milestones()]
    assert names == ["CLAMP RELEASE", "LIFTOFF", "MAX Q", "STAGE SEP"]
    assert session.add_marker("   ") is None
    session.remove_marker(0)
    assert session.markers == []


def test_abort_scrubs_the_countdown_and_says_so_on_the_display():
    session = make_session(source="MOCK", clock_source=lambda: 100.0)
    session.start_countdown()
    session.telemetry()
    session.abort_countdown()
    tel = session.telemetry()
    assert session.clock.state is ClockState.ABORTED
    assert tel.status == "COUNTDOWN ABORTED"
    session.reset_countdown()
    assert session.telemetry().status is None


def test_disabled_events_stay_off_the_timeline():
    from ground_station.events import Event

    session = make_session()
    session.set_events([Event(0.0, "Liftoff"), Event(-120.0, "Poll", enabled=False), Event(70.0, "Max Q")])
    assert [m.name for m in session.milestones()] == ["LIFTOFF", "MAX Q"]
    assert [e["label"] for e in session.settings.events] == ["Liftoff", "Poll", "Max Q"]  # kept for saving


def test_warp_policy_reaches_the_clock():
    session = make_session()
    session.set_warp_policy("hold")
    assert session.clock.hold_in_warp and session.settings.warp_policy == "hold"
    session.set_source(DataSource.MOCK)
    assert session.clock.hold_in_warp  # a new clock for the other source keeps the policy


def test_game_ut_is_none_without_data():
    assert make_session().game_ut() is None


def test_mock_lag_spike_slows_the_countdown_not_the_wall_clock():
    now = [100.0]
    session = make_session(source="MOCK", clock_source=lambda: now[0])
    session.set_countdown_seconds(60.0)
    session.start_countdown()
    session.telemetry()
    now[0] = 110.0
    assert session.telemetry().t == pytest.approx(-50.0)
    session.mock_game.freeze(5.0)  # the simulated game stalls for 5 s of real time
    now[0] = 118.0
    assert session.telemetry().t == pytest.approx(-47.0)  # 10 s elapsed but only 3 s of game time advanced


def test_mock_link_loss_freezes_the_clock_and_says_signal_lost():
    now = [100.0]
    session = make_session(source="MOCK", clock_source=lambda: now[0])
    session.start_countdown()
    session.telemetry()
    now[0] = 120.0
    before = session.telemetry().t
    session.mock_game.link_lost = True
    now[0] = 140.0
    lost = session.telemetry()
    assert lost.t == pytest.approx(before) and lost.status == "SIGNAL LOST"
    session.mock_game.link_lost = False
    now[0] = 141.0
    back = session.telemetry()
    assert back.status is None and back.t == pytest.approx(before + 21.0)  # the game ran on while the link was down


def test_mock_time_warp_can_hold_the_countdown():
    now = [100.0]
    session = make_session(source="MOCK", clock_source=lambda: now[0])
    session.set_warp_policy("hold")
    session.start_countdown()
    session.telemetry()
    now[0] = 110.0
    session.telemetry()
    session.mock_game.warp = 100.0
    now[0] = 130.0
    assert session.telemetry().t == pytest.approx(-50.0)


def test_altitude_mode_reaches_the_reader():
    session = make_session()
    session.connect()
    session.set_altitude_mode("sea")
    assert FakeReader.instances[0].altitude_mode == "sea" and session.settings.altitude_mode == "sea"


def test_reconnect_opens_a_fresh_connection():
    session = make_session()
    session.connect()
    session.reconnect()
    assert len(FakeReader.instances) == 2 and FakeReader.instances[0].stopped and session.connected


def test_the_last_telemetry_is_kept_for_the_panel():
    session = make_session()
    assert session.last is None
    session.telemetry()
    assert session.last is not None


def test_shutdown_closes_the_connection():
    session = make_session()
    session.connect()
    session.shutdown()
    assert FakeReader.instances[0].stopped


def test_hud_sits_in_the_corner_and_on_the_bottom_edge():
    from ground_station.app import PILL_TOP_GAP, hud_positions
    from ground_station.pill import MARGIN

    pill, bar = hud_positions(0, 0, 1920, 1080, 1920, 195, 1.0)
    assert pill == (-MARGIN, -MARGIN + PILL_TOP_GAP)  # the drawn pill is flush left and a little below the top
    assert bar == (0, 1080 - 195)  # flush with the bottom edge, below the taskbar line
    pill, bar = hud_positions(1920, -219, 1920, 1080, 1920, 195, 1.0)  # a screen to the right and higher up
    assert pill == (1920 - MARGIN, -219 - MARGIN + PILL_TOP_GAP) and bar == (1920, -219 + 1080 - 195)


class _StubReader:
    started = 0

    def __init__(self, *args):
        pass

    def start(self):
        _StubReader.started += 1

    def stop(self):
        pass


def test_connects_by_itself_on_start_only_when_live_and_wanted():
    from ground_station.session import Session
    from ground_station.settings import Settings

    for source, auto, expected in (("LIVE", True, 1), ("LIVE", False, 0), ("MOCK", True, 0)):
        _StubReader.started = 0
        session = Session(Settings(source=source, auto_connect=auto), reader_factory=_StubReader)
        session.connect_on_start()
        assert _StubReader.started == expected and session.connected is bool(expected)


def test_session_notices_the_mock_stack_separating_and_forgets_it_on_reset():
    from ground_station.session import Session
    from ground_station.settings import Settings
    from ground_station.source import DataSource

    now = [0.0]
    session = Session(Settings(source="MOCK"), game_time=lambda: now[0])
    assert session.source is DataSource.MOCK
    session.start_countdown()
    seen = []
    for step in range(0, 23000):  # 230 s of game time (the countdown starts at T-60), past the default Stage Sep marker
        now[0] = step / 100.0 + 0.01
        session.separation._now = lambda: now[0]
        seen.append(session.telemetry())
    final = seen[-1]
    assert final.t > 143 and final.engines_total == 6
    assert final.separated_at == pytest.approx(143.0, abs=0.1)
    assert seen[0].separated_at is None
    session.reset_countdown()
    assert session.separation.separated_at is None


def flying_status(ut, nodes=(), apo=None, peri=None, reentry_ut=None):
    sample = LiveSample(
        100.0, 7000.0, 120_000.0, 0.5, 0.0, 6, 6, "orbiting", 0.0, ut=ut, node_uts=nodes, apoapsis_km=apo, periapsis_km=peri, reentry_ut=reentry_ut
    )
    return ReaderStatus(ConnState.CONNECTED, sample, 0.0, None)


def watching_session():
    wall = [0.0]
    session = make_session()
    session._auto_clock = lambda: wall[0]
    session.connect()
    return session, FakeReader.instances[0], wall


def test_a_planned_node_is_offered_then_named_onto_the_timeline_and_remembered():
    session, reader, wall = watching_session()
    for wall[0] in (0.0, 3.0):
        reader.status = flying_status(1000.0, nodes=(1600.0,))
        session.telemetry()
    proposal = session.pending_node
    assert proposal is not None and proposal.ahead == pytest.approx(600.0)
    marker = session.name_node("Circularize")
    assert marker.time == pytest.approx(session.t + 600.0, abs=0.2)
    assert session.take_auto_dirty() and not session.take_auto_dirty()
    assert session.settings.auto_markers[0]["name"] == "Circularize"
    assert [m.name for m in session.milestones() if m.name == "CIRCULARIZE"] == ["CIRCULARIZE"]


def test_hidden_and_deleted_automatic_markers_leave_the_timeline():
    session, reader, wall = watching_session()
    for wall[0] in (0.0, 3.0):
        reader.status = flying_status(1000.0, nodes=(1600.0,))
        session.telemetry()
    session.name_node("Burn")
    session.set_auto_marker(0, enabled=False)
    assert "BURN" not in [m.name for m in session.milestones()]
    session.set_auto_marker(0, enabled=True, name="Deorbit")
    assert "DEORBIT" in [m.name for m in session.milestones()]
    session.remove_auto_marker(0)
    assert session.auto_markers == [] and session.settings.auto_markers == []


def test_nothing_is_added_while_the_feed_is_stale_or_lost():
    session, reader, wall = watching_session()
    for wall[0] in (0.0, 3.0):
        reader.status = ReaderStatus(ConnState.LOST, flying_status(1000.0, nodes=(1600.0,)).sample, 5.0, "gone")
        session.telemetry()
    assert session.pending_node is None


def test_reentry_marker_is_added_from_the_orbit_the_game_reports():
    session, reader, wall = watching_session()
    reader.status = flying_status(1000.0, apo=160.0, peri=150.0)
    session.telemetry()
    reader.status = flying_status(1100.0, apo=160.0, peri=-30.0, reentry_ut=1900.0)
    session.telemetry()
    assert [m.name for m in session.auto_markers] == ["Re-entry"]
    assert session.auto_markers[0].time == pytest.approx(session.t + 800.0, abs=0.2)


def test_switching_source_forgets_a_question_that_was_waiting():
    session, reader, wall = watching_session()
    for wall[0] in (0.0, 3.0):
        reader.status = flying_status(1000.0, nodes=(1600.0,))
        session.telemetry()
    assert session.pending_node is not None
    session.set_source(DataSource.MOCK)
    assert session.pending_node is None
