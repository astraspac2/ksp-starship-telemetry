"""Smoke tests: drive the real panel widgets headlessly and check they operate the session."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ground_station import settings as settings_io
from ground_station import theme
from ground_station.clock import ClockState
from ground_station.panel import COL_LABEL, COL_ON, COL_TIME, ControlPanel, build_style
from ground_station.session import Session
from ground_station.settings import Settings
from ground_station.source import DataSource


class FakeReader:
    instances = []

    def __init__(self, *args):
        self.args = args
        self.stopped = False
        FakeReader.instances.append(self)

    def start(self):
        pass

    def stop(self):
        self.stopped = True

    def snapshot(self):
        from ground_station.krpc_source import ConnState, ReaderStatus

        return ReaderStatus(ConnState.CONNECTING, None, None, "waiting")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from ground_station.fonts import load_bundled_fonts

    load_bundled_fonts()  # a headless machine may have no system fonts at all
    return app


@pytest.fixture
def panel(qapp, tmp_path, monkeypatch):
    FakeReader.instances.clear()
    monkeypatch.setattr(settings_io, "default_path", lambda: tmp_path / "settings.json")
    now = [100.0]
    session = Session(Settings(), reader_factory=FakeReader, game_time=lambda: now[0])
    changed = []
    widget = ControlPanel(session, lambda: changed.append(1), preview_source=lambda: None)
    widget.changed = changed
    widget.session = session
    widget.now = now
    widget.saved = tmp_path / "settings.json"
    return widget


def test_theme_names_in_settings_match_the_real_themes():
    assert list(settings_io.THEMES) == [t.name for t in theme.THEMES]


def test_every_panel_look_builds_a_complete_style_sheet():
    for name in settings_io.PANEL_THEMES:
        assert "@" not in build_style(name)  # every colour token was filled in


def test_opening_the_panel_does_not_rewrite_the_saved_settings(panel):
    assert panel.changed == []
    assert not panel.saved.exists()


# connection and data source
def test_apply_and_connect_connects_afresh_and_disconnect_stops(panel):
    panel._source_combo.setCurrentIndex(0)
    panel._apply_and_connect()
    assert panel.session.connected and panel._disconnect_button.isEnabled()
    panel._apply_and_connect()
    assert len(FakeReader.instances) == 2 and FakeReader.instances[0].stopped
    panel._disconnect_button.click()
    assert not panel.session.connected


def test_mock_source_is_badged_and_enables_the_simulator(panel):
    assert not panel._mock_group.isEnabled()
    panel._source_combo.setCurrentIndex(1)
    assert panel.session.source is DataSource.MOCK
    assert "MOCK" in panel._badge.text() and "MOCK DATA" in panel._source_label.text()
    assert not panel._connect_button.isEnabled() and panel._mock_group.isEnabled()


def test_mock_simulator_controls_drive_the_simulated_game(panel):
    panel._source_combo.setCurrentIndex(1)
    panel._paused.setChecked(True)
    panel._warp_rate.setCurrentIndex(3)
    panel._link_loss.setChecked(True)
    game = panel.session.mock_game
    assert game.paused and game.warp == 50.0 and game.link_lost
    before = game.ut()
    panel._jump_back.click()
    assert game.ut() == pytest.approx(before - 60.0)
    panel._jump_forward.click()
    assert game.ut() == pytest.approx(before + 60.0)
    panel._lag_seconds.setValue(3.0)
    panel._lag_button.click()
    assert game.frozen


def test_altitude_mode_choice_is_saved(panel):
    panel._altitude_mode.setCurrentIndex(1)
    assert panel.session.settings.altitude_mode == "sea"
    assert settings_io.load(panel.saved).altitude_mode == "sea"


# countdown
def test_countdown_buttons_follow_the_clock_state(panel):
    assert panel._start_button.isEnabled() and not panel._hold_button.isEnabled()
    assert panel._state_label.text() == "STANDBY"
    panel._start_button.click()
    panel.refresh()
    assert panel.session.clock.state is ClockState.RUNNING
    assert not panel._start_button.isEnabled() and panel._hold_button.isEnabled()
    panel._hold_button.click()
    panel.refresh()
    assert panel.session.clock.state is ClockState.HELD and panel._resume_button.isEnabled()
    assert panel._state_label.text() == "HOLD"
    panel._resume_button.click()
    panel._reset_button.click()
    panel.refresh()
    assert panel.session.clock.state is ClockState.IDLE


def test_abort_asks_first_and_only_scrubs_the_display(panel, monkeypatch):
    panel.session.set_source(DataSource.MOCK)
    panel._start_button.click()
    panel.session.telemetry()
    panel.refresh()
    assert panel._abort_button.isEnabled()
    monkeypatch.setattr(panel, "_confirm_abort", lambda: False)
    panel._abort_button.click()
    assert panel.session.clock.state is ClockState.RUNNING
    monkeypatch.setattr(panel, "_confirm_abort", lambda: True)
    panel._abort_button.click()
    assert panel.session.clock.state is ClockState.ABORTED
    assert panel._state_label.text() == "ABORTED"
    assert not panel._abort_button.isEnabled()


def test_abort_is_unavailable_when_nothing_is_counting(panel):
    assert not panel._abort_button.isEnabled()


def test_broadcast_lock_freezes_settings_but_keeps_hold_and_abort(panel):
    panel.session.set_source(DataSource.MOCK)
    panel._start_button.click()
    panel.session.telemetry()
    panel._lock.setChecked(True)
    panel.refresh()
    assert not panel._tabs.isEnabled()
    assert not panel._reset_button.isEnabled() and not panel._start_button.isEnabled()
    assert panel._hold_button.isEnabled() and panel._abort_button.isEnabled()
    panel._hold_button.click()
    panel.refresh()
    assert not panel._resume_button.isEnabled()
    panel._lock.setChecked(False)
    panel.refresh()
    assert panel._tabs.isEnabled() and panel._resume_button.isEnabled()


def test_countdown_start_is_typed_as_a_clock_time(panel):
    panel._start_text.setText("T-00:02:30")
    panel._store_countdown_start()
    assert panel.session.settings.countdown_seconds == 150.0
    panel._start_text.setText("T+00:01:00")
    panel._store_countdown_start()
    assert panel.session.settings.countdown_seconds == 150.0
    assert panel._start_text.text() == "T-00:02:30"


def test_time_warp_choice_reaches_the_clock_and_is_saved(panel):
    panel._warp.setCurrentIndex(1)
    assert panel.session.clock.hold_in_warp
    assert settings_io.load(panel.saved).warp_policy == "hold"


def test_header_readout_shows_live_numbers(panel):
    panel.session.set_source(DataSource.MOCK)
    panel.session.set_countdown_seconds(30.0)
    panel.session.start_countdown()
    panel.session.telemetry()
    panel.now[0] = 140.0  # 40 s on: 10 s past liftoff
    panel.session.telemetry()
    panel.refresh()
    assert "SPEED" in panel._readout.text() and "KM/H" in panel._readout.text() and "ENGINES 33/33" in panel._readout.text()


# HUD tab
def test_hud_checkboxes_are_saved_and_announced(panel):
    panel._badge_check.setChecked(True)
    panel._click_through.setChecked(False)
    panel._show_pill.setChecked(False)
    s = panel.session.settings
    assert s.show_badge and not s.click_through and not s.show_pill
    assert not panel._pill_action.isChecked()  # the View menu follows
    assert panel.changed
    saved = settings_io.load(panel.saved)
    assert saved.show_badge and not saved.click_through


def test_show_hide_button_toggles_the_bar(panel):
    assert panel.session.settings.show_bar
    panel._show_bar.setChecked(False)
    assert not panel.session.settings.show_bar and not panel._bar_action.isChecked()


def test_hud_numbers_and_choices_are_saved(panel):
    panel._scale.setValue(1.5)
    panel._nodes.setValue(3)
    panel._speed_unit.setCurrentIndex(2)
    panel._altitude_unit.setCurrentIndex(1)
    panel._background.setCurrentIndex(1)
    panel._font.setCurrentIndex(1)
    s = panel.session.settings
    assert s.hud_scale == 1.5 and s.timeline_nodes == 3 and s.speed_unit == "mph" and s.altitude_unit == "km"
    assert s.background == "solid" and s.font != ""
    assert panel._background_button.isEnabled()
    panel._font.setCurrentIndex(0)
    assert panel.session.settings.font == ""


def test_accent_colour_can_be_picked_and_reset(panel, monkeypatch):
    monkeypatch.setattr(panel, "_choose_color", lambda initial: "#00FF88")
    panel._accent_button.click()
    assert panel.session.settings.accent == "#00FF88" and "#00FF88" in panel._accent_button.text()
    panel._set_accent("")
    assert panel.session.settings.accent == "" and "own colour" in panel._accent_button.text()
    monkeypatch.setattr(panel, "_choose_color", lambda initial: None)  # cancelled dialog changes nothing
    panel._accent_button.click()
    assert panel.session.settings.accent == ""


def test_opacity_slider_overrides_the_look_and_reset_restores_it(panel):
    default = round(theme.STARSHIP.plate_alpha / 255 * 100)
    assert panel._opacity.value() == default and panel.session.settings.panel_opacity is None
    panel._opacity.setValue(80)
    assert panel.session.settings.panel_opacity == 0.8
    panel._reset_opacity()
    assert panel.session.settings.panel_opacity is None and panel._opacity.value() == default


def test_3d_model_must_load(panel, tmp_path):
    panel._set_vessel(str(tmp_path / "missing.obj"))
    assert panel.session.settings.vessel_model == ""  # refused, and not remembered
    assert "could not be used" in panel.statusBar().currentMessage()
    model = tmp_path / "rocket.obj"
    model.write_text(
        "v -0.1 0 0\nv 0.1 0 0\nv 0 0 0.1\nv 0 1 0\nf 1 2 4\nf 2 3 4\nf 3 1 4\nf 1 3 2\n"
    )
    panel._set_vessel(str(model))
    assert panel.session.settings.vessel_model == str(model)
    assert "4 triangles" in panel._model_note.text()
    panel._set_vessel("")
    assert panel.session.settings.vessel_model == "" and panel._model_note.text() == ""


def test_model_flip_is_saved(panel):
    panel._model_flip.setChecked(True)
    assert panel.session.settings.vessel_model_flip
    assert settings_io.load(panel.saved).vessel_model_flip


# appearance and panel look
def test_choosing_a_look_card_is_saved(panel):
    panel._theme_buttons["B - Glass"].click()
    assert panel.session.settings.theme == "B - Glass"
    assert panel._theme_buttons["B - Glass"].isChecked() and not panel._theme_buttons["A - Starship-accurate"].isChecked()
    assert "own colour" in panel._accent_button.text()


def test_accent_swatches_set_the_accent(panel):
    panel._set_accent("#8FD694")
    assert panel.session.settings.accent == "#8FD694"


def test_panel_look_switches_to_forest_and_back(panel):
    panel._panel_theme.setCurrentIndex(1)
    assert panel.session.settings.panel_theme == "forest"
    assert "rgba" in panel.styleSheet()
    pixmap = panel.grab()  # painting the forest must not fail
    assert not pixmap.isNull()
    panel._panel_theme.setCurrentIndex(0)
    assert panel.session.settings.panel_theme == "aerospace"


# timeline events
def test_event_table_lists_the_planned_events(panel):
    assert panel._table.rowCount() == 3
    panel.refresh()
    assert panel._table.item(0, COL_TIME).text() == "T+00:00:00"
    assert panel._table.item(0, 4).text().startswith("NEXT in")


def test_adding_editing_and_removing_events(panel):
    panel._add_event()
    assert panel._table.rowCount() == 4 and panel.session.events[-1].label == "New event"
    panel._table.item(3, COL_LABEL).setText("Boostback")
    panel._table.item(3, COL_TIME).setText("T+00:02:40")
    assert panel.session.events[3].label == "Boostback" and panel.session.events[3].time == 160.0
    assert [m.name for m in panel.session.milestones()][-1] == "BOOSTBACK"
    panel._table.selectRow(3)
    panel._remove_event()
    assert panel._table.rowCount() == 3
    assert panel.changed


def test_a_bad_time_keeps_the_old_one(panel):
    panel._table.item(1, COL_TIME).setText("soon")
    assert panel.session.events[1].time == 70.0
    assert panel._table.item(1, COL_TIME).text() == "T+00:01:10"


def test_unticking_hides_an_event_from_the_timeline(panel):
    panel._table.item(1, COL_ON).setCheckState(Qt.Unchecked)
    assert not panel.session.events[1].enabled
    assert "MAX Q" not in [m.name for m in panel.session.milestones()]


def test_move_and_sort(panel):
    panel._table.selectRow(0)
    panel._move_event(1)
    assert [e.label for e in panel.session.events][:2] == ["Max Q", "Liftoff"]
    panel._sort_events()
    assert [e.label for e in panel.session.events][:2] == ["Liftoff", "Max Q"]


def test_markers_tab_adds_and_removes(panel):
    panel._marker_text.setText("clamp release")
    panel._add_marker()
    assert panel._marker_list.count() == 1
    assert "[MANUAL]" in panel._marker_list.item(0).text()
    panel._marker_list.setCurrentRow(0)
    panel._remove_marker()
    assert panel._marker_list.count() == 0


def test_events_box_is_split_into_manual_events_and_automatic_markers(panel):
    assert panel._table.rowCount() == 3 and panel._auto_table.rowCount() == 0
    from ground_station.auto_markers import NODE, AutoMarker

    panel.session.auto_markers.append(AutoMarker("Burn", 1320.0, NODE))
    panel.session.sync_auto_markers()
    panel.refresh()
    assert panel._auto_table.rowCount() == 1
    assert panel._auto_table.item(0, 2).text() == "Burn" and panel._auto_table.item(0, 1).text() == "T+00:22:00"
    assert settings_io.load(panel.saved).auto_markers[0]["name"] == "Burn"  # saved when the station added it


def test_automatic_markers_can_be_hidden_renamed_and_deleted(panel):
    from ground_station.auto_markers import NODE, AutoMarker

    panel.session.auto_markers.append(AutoMarker("Burn", 1320.0, NODE))
    panel.session.sync_auto_markers()
    panel.refresh()
    panel._auto_table.item(0, 0).setCheckState(Qt.Unchecked)
    assert not panel.session.auto_markers[0].enabled and "BURN" not in [m.name for m in panel.session.milestones()]
    panel._auto_table.item(0, 2).setText("Circularize")
    assert panel.session.auto_markers[0].name == "Circularize"
    panel._auto_table.selectRow(0)
    panel._delete_auto_marker()
    assert panel._auto_table.rowCount() == 0 and panel.session.auto_markers == []
    assert settings_io.load(panel.saved).auto_markers == []


def test_a_new_node_makes_the_panel_ask_for_a_name(panel, monkeypatch):
    from ground_station import panel as panel_module
    from ground_station.auto_markers import NodeProposal

    asked = []
    monkeypatch.setattr(panel.session.auto, "pending", NodeProposal(1600.0, 1320.0, 600.0))
    monkeypatch.setattr(
        panel_module.QInputDialog, "getText", lambda *args, **kwargs: (asked.append(args[2]) or ("Circularize", True))
    )
    panel.refresh()
    assert "10m 00s" in asked[0] and "T+00:22:00" in asked[0]
    assert [m.name for m in panel.session.auto_markers] == ["Circularize"] and panel._auto_table.rowCount() == 1


def test_cancelling_the_name_prompt_leaves_the_node_off_the_timeline(panel, monkeypatch):
    from ground_station import panel as panel_module
    from ground_station.auto_markers import NodeProposal

    monkeypatch.setattr(panel.session.auto, "pending", NodeProposal(1600.0, 1320.0, 600.0))
    monkeypatch.setattr(panel_module.QInputDialog, "getText", lambda *args, **kwargs: ("", False))
    panel.refresh()
    assert panel.session.auto_markers == [] and panel.session.pending_node is None


def test_starship_model_toggle_is_saved(panel):
    assert panel.session.settings.starship_model  # on by default
    panel._starship_model.setChecked(False)
    assert not settings_io.load(panel.saved).starship_model
