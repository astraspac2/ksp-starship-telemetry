import dataclasses

import pytest

from ground_station.recording import FILE_NAME, HOLD_AFTER_SECONDS, FlightRecorder, Recording, load_latest, save_recording
from ground_station.session import Session
from ground_station.settings import Settings
from ground_station.source import DataSource
from ground_station.telemetry import mock_telemetry


def recorded(seconds=60):
    recorder = FlightRecorder()
    for i in range(seconds + 1):
        recorder.add(float(i), 1000.0 - 10.0 * i, 80.0 - i, 0.5, 13, 33)
    return recorder.finish()


def test_a_recording_plays_back_between_its_readings():
    recording = recorded()
    middle = recording.at(10.5)
    assert middle.speed_kmh == pytest.approx(895.0) and middle.altitude_km == pytest.approx(69.5)
    assert middle.engines_on == 13 and middle.engines_total == 33


def test_a_playback_holds_the_last_reading_a_moment_then_ends():
    recording = recorded(60)
    assert recording.at(-5.0).speed_kmh == pytest.approx(1000.0)  # before it starts: the first reading
    assert recording.at(60.0 + HOLD_AFTER_SECONDS - 0.1).altitude_km == pytest.approx(20.0)
    assert recording.at(60.0 + HOLD_AFTER_SECONDS + 0.1) is None


def test_the_recorder_keeps_a_reading_a_quarter_second_apart_and_nothing_before_the_separation():
    recorder = FlightRecorder()
    recorder.add(-1.0, 1.0, 1.0, 1.0, 1, 1)
    recorder.add(0.0, 1.0, 1.0, 1.0, 1, 1)
    recorder.add(0.1, 1.0, 1.0, 1.0, 1, 1)
    recorder.add(0.3, 1.0, 1.0, 1.0, 1, 1)
    assert [s[0] for s in recorder.samples] == [0.0, 0.3]


def test_a_recording_needs_two_readings_to_count():
    recorder = FlightRecorder()
    recorder.add(0.0, 1.0, 1.0, 1.0, 1, 1)
    assert recorder.finish() is None


def test_a_recording_is_saved_and_loaded_again(tmp_path):
    recording = recorded()
    save_recording(recording, tmp_path)
    assert (tmp_path / FILE_NAME).exists() and len(list(tmp_path.glob("booster-2*.json"))) == 1
    assert load_latest(tmp_path).samples == [tuple(s) for s in recording.samples]


def test_a_missing_or_broken_recording_is_just_none(tmp_path):
    assert load_latest(tmp_path) is None and load_latest(None) is None
    (tmp_path / FILE_NAME).write_text("{not json")
    assert load_latest(tmp_path) is None
    assert Recording.from_dict({"version": 1, "samples": [[0, 1, 1, 1, 1, 1]]}) is None  # one reading only
    assert Recording.from_dict({"version": 99, "samples": []}) is None


def flying(session, t, sep, on_booster, booster_live=False):
    session.separation.separated_at = sep
    base = dataclasses.replace(mock_telemetry(t), on_booster=on_booster, booster_live=booster_live)
    return session._record_and_replay(dataclasses.replace(base, separated_at=sep))


def make_session(tmp_path, use_recording):
    session = Session(Settings(use_recording=use_recording), recordings=tmp_path)
    session.source = DataSource.LIVE
    return session


def test_flying_the_booster_records_it_and_stopping_saves_it(tmp_path):
    session = make_session(tmp_path, False)
    session.start_recording()
    for second in range(0, 30):
        flying(session, 150.0 + second, 150.0, on_booster=True)
    recording = session.stop_recording()
    assert recording is not None and recording.length == pytest.approx(29.0, abs=0.5)
    assert (tmp_path / FILE_NAME).exists() and session.replay is recording


def test_flying_the_ship_records_nothing(tmp_path):
    session = make_session(tmp_path, False)
    session.start_recording()
    for second in range(0, 30):
        flying(session, 150.0 + second, 150.0, on_booster=False)
    assert session.stop_recording() is None


def test_the_booster_is_filled_in_from_the_recording_only_when_asked_and_when_it_cannot_be_read(tmp_path):
    session = make_session(tmp_path, True)
    session.replay = recorded()
    out = flying(session, 160.0, 150.0, on_booster=False)  # the ship is flown, 10 s after the separation
    assert out.booster_replay and out.booster_live and out.booster_speed_kmh == pytest.approx(900.0) and session.replay_in_use
    assert not flying(session, 160.0, 150.0, on_booster=False, booster_live=True).booster_replay  # really readable: the game wins
    assert not flying(session, 150.0 + 200.0, 150.0, on_booster=False).booster_replay  # the recording has ended
    off = make_session(tmp_path, False)
    off.replay = recorded()
    assert not flying(off, 160.0, 150.0, on_booster=False).booster_replay  # not asked for


def test_no_playback_before_the_separation_or_while_the_feed_is_bad(tmp_path):
    session = make_session(tmp_path, True)
    session.replay = recorded()
    assert not session._record_and_replay(dataclasses.replace(mock_telemetry(100.0), separated_at=None)).booster_replay
    bad = dataclasses.replace(mock_telemetry(160.0), separated_at=150.0, status="SIGNAL LOST")
    assert not session._record_and_replay(bad).booster_replay
