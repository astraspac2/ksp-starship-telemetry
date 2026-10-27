"""The pad / static-fire view: its clock, its own events and label, its bar arrangement and the panel switch."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dataclasses

import pytest
from PySide6.QtWidgets import QApplication

from ground_station import settings as settings_io
from ground_station.bar import (
    ALTITUDE_CENTER_X,
    BAR_HEIGHT,
    BAR_WIDTH,
    GAUGE_RADIUS,
    GAUGE_Y,
    PAD_ENGINE_X,
    PAD_HEIGHT,
    PAD_SCALE,
    PAD_THROTTLE_X,
    PAD_THRUST_X,
    PAD_TOP,
    PAD_WIDTH,
    SPEED_CENTER_X,
    TelemetryBar,
)
from ground_station.clock import COUNTDOWN_HOLD, ClockState
from ground_station.fonts import load_bundled_fonts
from ground_station.krpc_source import ConnState, LiveSample, ReaderStatus
from ground_station.layout import Layout
from ground_station.panel import COL_LABEL, ControlPanel
from ground_station.session import Session
from ground_station.settings import Settings
from ground_station.source import DataSource
from ground_station.telemetry import MOCK_FULL_THRUST_N, mock_pad_telemetry, mock_telemetry
from ground_station.timeline import Milestone


class FakeReader:
    instances = []

    def __init__(self, *args):
        self.status = ReaderStatus(ConnState.CONNECTING, None, None, "waiting")
        FakeReader.instances.append(self)

    def start(self):
        pass

    def stop(self):
        pass

    def snapshot(self):
        return self.status


def static_fire_sample(ut, thrust_n=0.0, throttle=0.0, lit=0):
    """What KSP reported during the recorded static fire: mission time stuck at 0 on the pad, with engines burning."""
    return LiveSample(
        0.0, 0.0, 28.0, 0.98, 90.0, lit, 33, "pre_launch", 0.0,
        ut=ut, thrust_n=thrust_n, max_thrust_n=18_915_933.0, throttle=throttle, nozzles_lit=(True,) * lit + (False,) * (33 - lit),
    )


@pytest.fixture(autouse=True)
def _clear():
    FakeReader.instances.clear()


def live_session(view_mode="flight"):
    session = Session(Settings(source="LIVE", countdown_seconds=10.0, view_mode=view_mode), reader_factory=FakeReader)
    session.connect()
    return session, FakeReader.instances[-1]


def feed(session, reader, ut, **kwargs):
    reader.status = ReaderStatus(ConnState.CONNECTED, static_fire_sample(ut, **kwargs), 0.0, None)
    return session.telemetry()


# the clock
def test_on_the_pad_the_clock_runs_on_through_zero_although_mission_time_stays_at_zero():
    session, reader = live_session("pad")
    feed(session, reader, 1000.0)
    session.start_countdown()
    feed(session, reader, 1000.0)
    assert feed(session, reader, 1008.0).t == pytest.approx(-2.0)
    tel = feed(session, reader, 1016.0, thrust_n=18_900_000.0, throttle=1.0, lit=33)  # KSP still says met=0, pre_launch
    assert tel.t == pytest.approx(6.0)
    assert tel.thrust_n == 18_900_000.0 and tel.engines_on == 33


def test_in_flight_view_the_same_samples_hold_the_clock_at_zero_as_before():
    session, reader = live_session("flight")
    feed(session, reader, 1000.0)
    session.start_countdown()
    feed(session, reader, 1000.0)
    assert feed(session, reader, 1016.0).t == COUNTDOWN_HOLD  # waiting for KSP to report the launch


def test_switching_to_the_pad_while_the_flight_clock_waits_at_zero_lets_it_carry_on():
    session, reader = live_session("flight")
    feed(session, reader, 1000.0)
    session.start_countdown()
    feed(session, reader, 1000.0)
    assert feed(session, reader, 1014.0).t == COUNTDOWN_HOLD
    session.set_view_mode("pad")
    assert feed(session, reader, 1015.0).t == pytest.approx(5.0)  # the count had been going on behind the hold
    session.set_view_mode("flight")
    assert feed(session, reader, 1016.0).t == COUNTDOWN_HOLD


def test_a_real_launch_still_takes_over_with_mission_time_in_the_pad_view():
    session, reader = live_session("pad")
    feed(session, reader, 1000.0)
    session.start_countdown()
    feed(session, reader, 1000.0)
    sample = dataclasses.replace(static_fire_sample(1020.0), met=3.0, situation="flying")
    reader.status = ReaderStatus(ConnState.CONNECTED, sample, 0.0, None)
    assert session.telemetry().t == 3.0


# events and labels
def test_each_view_has_its_own_events_and_label():
    session = Session(Settings(), reader_factory=FakeReader)
    assert [e.label for e in session.events] == ["Liftoff", "Max Q", "Stage Sep"]
    session.set_view_mode("pad")
    assert session.pad_mode and [e.label for e in session.events] == ["Ignition", "Shutdown"]
    assert session.settings.mission_label == "STATIC FIRE"
    assert [m.name for m in session.milestones()] == ["IGNITION", "SHUTDOWN"]
    session.set_view_mode("flight")
    assert not session.pad_mode and session.settings.mission_label == "FLIGHT 1"


def test_editing_the_pad_events_leaves_the_flight_events_alone_and_vice_versa():
    from ground_station.events import Event

    session = Session(Settings(), reader_factory=FakeReader)
    session.set_view_mode("pad")
    session.set_events([Event(0.0, "Ignition"), Event(4.0, "Throttle down"), Event(12.0, "Shutdown")])
    assert [e["label"] for e in session.settings.pad_events] == ["Ignition", "Throttle down", "Shutdown"]
    assert [e["label"] for e in session.settings.events] == ["Liftoff", "Max Q", "Stage Sep"]
    session.set_view_mode("flight")
    session.set_events([Event(0.0, "Liftoff")])
    assert [e["label"] for e in session.settings.pad_events] == ["Ignition", "Throttle down", "Shutdown"]


def test_the_view_is_remembered_when_the_app_restarts(tmp_path):
    path = tmp_path / "s.json"
    session = Session(Settings(), reader_factory=FakeReader)
    session.set_view_mode("pad")
    settings_io.save(session.settings, path)
    again = Session(settings_io.load(path), reader_factory=FakeReader)
    assert again.pad_mode and [e.label for e in again.events] == ["Ignition", "Shutdown"]


def test_an_unknown_view_is_refused():
    session = Session(Settings(), reader_factory=FakeReader)
    session.set_view_mode("warp drive")
    assert session.settings.view_mode == "flight"


# what the pad view leaves out
def test_the_pad_view_never_reports_a_stage_separation():
    """A change of engine count after T-0 is a separation in flight; on the pad it must not make one (no stage to drop)."""
    from ground_station.separation import SeparationDetector

    def run(view_mode, make_sample):
        wall = [0.0]
        session, reader = live_session(view_mode)
        session.separation = SeparationDetector(lambda: wall[0])
        session.set_countdown_seconds(10.0)
        feed(session, reader, 1000.0)
        session.start_countdown()
        feed(session, reader, 1000.0)
        for step, (ut, engines) in enumerate(((1012.0, 33), (1013.0, 33), (1014.0, 6), (1015.0, 6), (1016.0, 6))):
            wall[0] += 0.3 * step
            reader.status = ReaderStatus(ConnState.CONNECTED, make_sample(ut, engines), 0.0, None)
            tel = session.telemetry()
        return session, tel

    pad_sample = lambda ut, engines: dataclasses.replace(static_fire_sample(ut), engines_total=engines)  # noqa: E731
    flying = lambda ut, engines: dataclasses.replace(  # noqa: E731
        static_fire_sample(ut), engines_total=engines, met=ut - 1010.0, situation="flying"
    )
    flight_session, flight_tel = run("flight", flying)
    assert flight_session.separation.separated_at is not None and flight_tel.separated_at is not None  # the control: it does fire
    pad_session, pad_tel = run("pad", pad_sample)
    assert pad_session.separation.separated_at is not None  # the detector saw the change of count ...
    assert pad_tel.separated_at is None  # ... and the pad view does not act on it


def test_the_pad_view_ignores_maneuver_nodes_and_leaves_automatic_markers_off_the_timeline():
    from ground_station.auto_markers import NODE, AutoMarker

    session, reader = live_session("pad")
    session.auto_markers.append(AutoMarker("Burn", 100.0, NODE))
    session._auto_clock = lambda: 100.0
    for wall in (0.0, 3.0):
        session._auto_clock = lambda wall=wall: wall
        sample = dataclasses.replace(static_fire_sample(1000.0), node_uts=(1600.0,))
        reader.status = ReaderStatus(ConnState.CONNECTED, sample, 0.0, None)
        session.telemetry()
    assert session.pending_node is None
    assert "BURN" not in [m.name for m in session.milestones()]
    session.set_view_mode("flight")
    assert "BURN" in [m.name for m in session.milestones()]


def test_the_mock_source_in_the_pad_view_is_a_labelled_static_fire():
    now = [100.0]
    session = Session(Settings(source="MOCK", countdown_seconds=10.0, view_mode="pad"), reader_factory=FakeReader, game_time=lambda: now[0])
    session.start_countdown()
    session.telemetry()
    now[0] = 110.0 + 5.0  # five seconds after T-0
    tel = session.telemetry()
    assert tel.source is DataSource.MOCK and tel.t == pytest.approx(5.0)
    assert tel.engines_on == 33 and tel.thrust_n == pytest.approx(MOCK_FULL_THRUST_N) and tel.speed_kmh == 0.0


# the bar
def test_the_pad_arrangement_is_just_engines_thrust_and_throttle():
    from ground_station.bar import ELEMENTS

    assert ELEMENTS[Layout.PAD] == {PAD_ENGINE_X: "booster", PAD_THRUST_X: "thrust", PAD_THROTTLE_X: "throttle"}  # no 3D dial, no speed, no altitude


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    load_bundled_fonts()
    return app


def pad_bar(**kwargs):
    """A pad bar drawn at exactly its drawing size (the HUD scale undoes the small bar's own shrinking), so pixels are drawing units."""
    bar = TelemetryBar(**kwargs)
    bar.set_smoothing(False)
    bar.set_view_mode("pad")
    bar.set_scale(1.0 / PAD_SCALE)
    return bar


def settle(bar):
    bar.grab()
    bar._changed_at -= 10.0  # let any fade finish
    return bar.grab().toImage()


def region_brightness(image, centre_x, top=0.0):
    r = int(GAUGE_RADIUS)
    total = 0
    for y in range(int(GAUGE_Y - top) - r, int(GAUGE_Y - top) + r, 2):
        for x in range(int(centre_x) - r, int(centre_x) + r, 2):
            c = image.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
    return total


def test_the_pad_bar_ignores_stage_sep_the_map_and_separation(qapp):
    bar = TelemetryBar(milestones=[Milestone("LIFTOFF", 0.0), Milestone("STAGE SEP", 143.0)])
    bar.set_smoothing(False)
    bar.set_view_mode("pad")
    bar.set_show_map(True)
    tel = dataclasses.replace(mock_pad_telemetry(200.0), separated_at=143.0)  # long past the Stage Sep marker, "separated"
    bar.set_telemetry(tel)
    settle(bar)
    assert bar._shown == {PAD_ENGINE_X: "booster", PAD_THRUST_X: "thrust", PAD_THROTTLE_X: "throttle"}


def test_going_back_to_the_flight_bar_brings_back_speed_and_altitude(qapp):
    bar = TelemetryBar()
    bar.set_smoothing(False)
    bar.set_view_mode("pad")
    bar.set_telemetry(mock_pad_telemetry(5.0))
    settle(bar)
    bar.set_view_mode("flight")
    bar.set_telemetry(mock_telemetry(30.0))
    settle(bar)
    assert bar._shown[SPEED_CENTER_X] == "speed" and bar._shown[ALTITUDE_CENTER_X] == "altitude"


def test_the_thrust_ring_follows_the_thrust_and_the_throttle_ring_the_throttle(qapp):
    bar = pad_bar()
    bar.set_telemetry(mock_pad_telemetry(-5.0))
    off = settle(bar)
    bar.set_telemetry(mock_pad_telemetry(5.0))
    full = settle(bar)
    for x in (PAD_THRUST_X, PAD_THROTTLE_X):
        assert region_brightness(full, x, PAD_TOP) > region_brightness(off, x, PAD_TOP) * 1.05  # the bright part of the ring and the numbers are there


def test_thrust_that_is_not_known_is_shown_as_a_dash_not_a_number(qapp):
    bar = pad_bar()
    known = dataclasses.replace(mock_pad_telemetry(5.0), thrust_n=9_000_000.0)
    unknown = dataclasses.replace(known, thrust_n=None)
    bar.set_telemetry(known)
    with_number = settle(bar)
    bar.set_telemetry(unknown)
    with_dash = settle(bar)
    assert region_brightness(with_dash, PAD_THRUST_X, PAD_TOP) < region_brightness(with_number, PAD_THRUST_X, PAD_TOP)  # a dash and an empty ring
    assert region_brightness(with_dash, PAD_THROTTLE_X, PAD_TOP) == pytest.approx(region_brightness(with_number, PAD_THROTTLE_X, PAD_TOP), rel=0.01)


def test_the_pad_bar_survives_every_kind_of_missing_data(qapp):
    bar = TelemetryBar()
    bar.set_view_mode("pad")
    empty = dataclasses.replace(
        mock_pad_telemetry(3.0), thrust_n=None, max_thrust_n=None, throttle=None, fuel_fraction=None, speed_kmh=None, altitude_km=None,
        pitch_deg=None, heading_deg=None, latitude_deg=None, longitude_deg=None, status="NO SIGNAL",
    )
    bar.set_telemetry(empty)
    assert not bar.grab().toImage().isNull()
    bar.set_telemetry(dataclasses.replace(mock_pad_telemetry(3.0), max_thrust_n=0.0))  # a zero full-scale must not divide by zero
    assert not bar.grab().toImage().isNull()


def test_the_pad_bar_is_a_small_window_that_follows_the_scale_and_goes_back_to_full_size(qapp):
    bar = TelemetryBar()
    assert (bar.width(), bar.height()) == (BAR_WIDTH, BAR_HEIGHT)
    bar.set_view_mode("pad")
    assert (bar.width(), bar.height()) == (round(PAD_WIDTH * PAD_SCALE), round(PAD_HEIGHT * PAD_SCALE))
    assert bar.width() < 0.35 * BAR_WIDTH  # well under half the width of the launch bar
    bar.set_scale(0.5)
    assert (bar.width(), bar.height()) == (round(PAD_WIDTH * PAD_SCALE * 0.5), round(PAD_HEIGHT * PAD_SCALE * 0.5))
    bar.set_view_mode("flight")
    assert (bar.width(), bar.height()) == (round(BAR_WIDTH * 0.5), round(BAR_HEIGHT * 0.5))


def test_the_small_bar_has_no_timeline_and_no_dial_but_a_plate_clock_and_gauges(qapp):
    bar = pad_bar(milestones=[Milestone("IGNITION", 0.0), Milestone("SHUTDOWN", 10.0)])
    bar.set_telemetry(mock_pad_telemetry(5.0))
    image = settle(bar)
    assert image.size().width() == PAD_WIDTH and image.size().height() == PAD_HEIGHT
    assert region_brightness(image, PAD_ENGINE_X, PAD_TOP) > 0 and region_brightness(image, PAD_THRUST_X, PAD_TOP) > 0
    # nothing is drawn where the flight bar's timeline line and 3D dial would be: the top strip above the clock is just the plate
    strip = [image.pixelColor(x, 6) for x in range(200, 480, 20)]
    assert all(abs(c.red() - strip[0].red()) < 12 for c in strip)
    plate = image.pixelColor(PAD_WIDTH // 2, PAD_HEIGHT - 8)
    assert plate.alpha() > 0  # the one rounded plate fills the window


@pytest.mark.parametrize("t", [-90.0, -40.0, -25.0, -8.0])
def test_everything_on_the_small_bar_is_visible_from_the_start(qapp, t):
    """No fade in at T-30, no gauges rising at T-10: the plate, clock and both gauges are there at once, even long before the count."""
    bar = pad_bar()
    bar.set_telemetry(mock_pad_telemetry(t))
    image = bar.grab().toImage()  # the very first picture, with nothing settled or waited for
    assert region_brightness(image, PAD_ENGINE_X, PAD_TOP) > 0
    ready = pad_bar()
    ready.set_telemetry(mock_pad_telemetry(-8.0))
    reference = settle(ready)
    for x in (PAD_ENGINE_X, PAD_THRUST_X, PAD_THROTTLE_X):
        assert region_brightness(image, x, PAD_TOP) == pytest.approx(region_brightness(reference, x, PAD_TOP), rel=0.05)
    clock = max(image.pixelColor(x, int(102 - PAD_TOP)).red() for x in range(200, 480))
    assert clock > 200  # the white clock digits are there
    plate = image.pixelColor(PAD_WIDTH // 2, PAD_HEIGHT - 8).alpha()
    assert plate > 30 and plate == reference.pixelColor(PAD_WIDTH // 2, PAD_HEIGHT - 8).alpha()  # and the plate is as strong as ever, not half faded in


def test_switching_to_the_small_bar_shows_it_at_once_without_a_fade(qapp):
    bar = TelemetryBar()
    bar.set_smoothing(False)
    bar.set_telemetry(mock_telemetry(30.0))
    bar.grab()
    bar.set_view_mode("pad")
    bar.set_scale(1.0 / PAD_SCALE)
    bar.set_telemetry(mock_pad_telemetry(-8.0))
    first = bar.grab().toImage()  # the first picture after the switch
    settled = settle(bar)
    for x in (PAD_ENGINE_X, PAD_THRUST_X, PAD_THROTTLE_X):
        assert region_brightness(first, x, PAD_TOP) == pytest.approx(region_brightness(settled, x, PAD_TOP), rel=0.05)


# where it sits
def test_the_pad_bar_goes_to_the_bottom_right_corner_and_the_flight_bar_stays_bottom_centre():
    from ground_station.app import CORNER_GAP, hud_positions

    width, height = round(PAD_WIDTH * PAD_SCALE), round(PAD_HEIGHT * PAD_SCALE)
    _, corner = hud_positions(0, 0, 1920, 1080, width, height, 1.0, corner=True)
    assert corner == (1920 - width - CORNER_GAP, 1080 - height - CORNER_GAP)
    _, corner_second_screen = hud_positions(1920, -219, 1920, 1080, width, height, 1.0, corner=True)  # a screen to the right and higher up
    assert corner_second_screen == (1920 + 1920 - width - CORNER_GAP, -219 + 1080 - height - CORNER_GAP)
    _, centre = hud_positions(0, 0, 1920, 1080, BAR_WIDTH, BAR_HEIGHT, 1.0)
    assert centre == (0, 1080 - BAR_HEIGHT)


def test_the_corner_gap_grows_with_the_hud_scale():
    from ground_station.app import CORNER_GAP, hud_positions

    _, corner = hud_positions(0, 0, 1920, 1080, 600, 120, 2.0, corner=True)
    assert corner == (1920 - 600 - 2 * CORNER_GAP, 1080 - 120 - 2 * CORNER_GAP)


def test_the_pill_is_hidden_in_the_pad_view_whatever_the_setting_says():
    from ground_station.app import pill_visible

    assert pill_visible(True, "flight") and not pill_visible(False, "flight")
    assert not pill_visible(True, "pad") and not pill_visible(False, "pad")


# the panel
class PadPanelFixture:
    pass


@pytest.fixture
def panel(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_io, "default_path", lambda: tmp_path / "settings.json")
    session = Session(Settings(), reader_factory=FakeReader, game_time=lambda: 100.0)
    changed = []
    widget = ControlPanel(session, lambda: changed.append(1), preview_source=lambda: None)
    widget.changed, widget.session, widget.saved = changed, session, tmp_path / "settings.json"
    return widget


def test_the_hud_tab_switches_the_bar_to_the_pad_view_and_back(panel):
    assert panel._view_mode.currentIndex() == 0 and panel._table.rowCount() == 3
    panel._view_mode.setCurrentIndex(1)
    assert panel.session.pad_mode and panel.changed  # the display windows are told
    assert panel._table.rowCount() == 2
    assert [panel._table.item(r, COL_LABEL).text() for r in range(2)] == ["Ignition", "Shutdown"]
    assert "Pad / static-fire events" in panel._events_box.title()
    assert panel._subtitle.text() == "STATIC FIRE"
    assert panel._pad_action.isChecked()
    assert settings_io.load(panel.saved).view_mode == "pad"
    panel._view_mode.setCurrentIndex(0)
    assert [panel._table.item(r, COL_LABEL).text() for r in range(3)] == ["Liftoff", "Max Q", "Stage Sep"]
    assert panel._subtitle.text() == "FLIGHT 1" and not panel._pad_action.isChecked()


def test_the_view_menu_entry_switches_the_view_too(panel):
    panel._pad_action.trigger()
    assert panel.session.pad_mode and panel._view_mode.currentIndex() == 1
    panel._pad_action.trigger()
    assert not panel.session.pad_mode and panel._view_mode.currentIndex() == 0


def test_the_label_and_events_typed_in_the_pad_view_belong_to_the_pad_view(panel):
    panel._view_mode.setCurrentIndex(1)
    panel._subtitle.setText("STARSHIP STATIC FIRE 1")
    panel._subtitle.editingFinished.emit()
    assert panel.session.settings.pad_subtitle == "STARSHIP STATIC FIRE 1" and panel.session.settings.subtitle == "FLIGHT 1"
    panel._add_event()
    assert panel._table.rowCount() == 3
    panel._view_mode.setCurrentIndex(0)
    assert panel._table.rowCount() == 3 and [e.label for e in panel.session.events][-1] == "Stage Sep"  # the flight list is untouched
    assert [e["label"] for e in settings_io.load(panel.saved).pad_events][-1] == "New event"


def test_the_thrust_unit_is_chosen_in_the_hud_tab_and_saved(panel):
    panel._thrust_unit.setCurrentIndex(3)
    assert panel.session.settings.thrust_unit == "tf" and settings_io.load(panel.saved).thrust_unit == "tf"


def test_broadcast_lock_stops_the_view_being_changed_from_the_menu(panel):
    panel._lock.setChecked(True)
    assert not panel._view_menu.isEnabled() and not panel._tabs.isEnabled()
