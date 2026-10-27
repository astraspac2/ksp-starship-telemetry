import pytest

from ground_station.krpc_source import ConnState, LiveSample, ReaderStatus
from ground_station.live import COUNTDOWN_HOLD, CountdownClock, live_telemetry, status_text
from ground_station.source import DataSource


def sample(met=0.0, situation="pre_launch", speed=0.0, altitude=75.0, pitch=90.0, ut=1000.0):
    return LiveSample(
        met=met,
        speed_ms=speed,
        altitude_m=altitude,
        fuel_fraction=1.0,
        pitch_deg=pitch,
        engines_on=0,
        engines_total=33,
        situation=situation,
        received_at=0.0,
        ut=ut,
    )


def status(state=ConnState.CONNECTED, s=None, age=0.05, error=None):
    return ReaderStatus(state, s, age, error)


def running_clock(seconds=60.0):
    clock = CountdownClock(seconds)
    clock.start()
    return clock


def test_countdown_follows_game_time():
    clock = running_clock()
    assert clock.t(status(s=sample(ut=1000.0))) == pytest.approx(-60.0)
    assert clock.t(status(s=sample(ut=1042.5))) == pytest.approx(-17.5)


def test_game_lag_slows_the_countdown_instead_of_overshooting():
    clock = running_clock()
    clock.t(status(s=sample(ut=1000.0)))
    stalled = status(s=sample(ut=1010.0), age=7.0)  # 7 real seconds since the last game update
    assert clock.t(stalled) == pytest.approx(-50.0)  # only 10 s of game time have passed


def test_paused_game_freezes_the_countdown():
    clock = running_clock()
    clock.t(status(s=sample(ut=1000.0)))
    assert clock.t(status(s=sample(ut=1030.0))) == pytest.approx(-30.0)
    assert clock.t(status(s=sample(ut=1030.0), age=45.0)) == pytest.approx(-30.0)


def test_countdown_holds_if_ksp_has_not_launched():
    clock = running_clock()
    clock.t(status(s=sample(ut=1000.0)))
    assert clock.t(status(s=sample(ut=1075.0))) == COUNTDOWN_HOLD


def test_clock_follows_ksp_met_after_launch_without_extrapolating():
    clock = running_clock()
    clock.t(status(s=sample(ut=1000.0)))
    launched = sample(met=12.0, situation="flying", ut=1072.0)
    assert clock.t(status(s=launched, age=3.0)) == 12.0  # a 3 s old sample is not advanced by 3 s


def test_clock_freezes_when_the_feed_is_lost():
    clock = running_clock()
    clock.t(status(s=sample(ut=1000.0)))
    last = clock.t(status(s=sample(ut=1020.0)))
    assert clock.t(status(ConnState.LOST, None, None)) == last


def test_no_connection_yet_shows_the_start_of_the_countdown():
    assert CountdownClock(60.0).t(status(ConnState.CONNECTING, None, None)) == -60.0


def test_units_are_converted_for_display():
    clock = running_clock()
    live = sample(met=10.0, situation="flying", speed=100.0, altitude=2500.0, pitch=80.0)
    tel = live_telemetry(clock, status(s=live))
    assert tel.source is DataSource.LIVE
    assert tel.t == 10.0
    assert tel.speed_kmh == pytest.approx(360.0)
    assert tel.altitude_km == pytest.approx(2.5)
    assert tel.pitch_deg == pytest.approx(10.0)
    assert tel.heading_deg is None  # this sample carried no heading
    assert tel.status is None


def test_no_connection_shows_no_values():
    tel = live_telemetry(CountdownClock(30.0), status(ConnState.CONNECTING, None, None))
    assert tel.t == -30.0
    assert tel.speed_kmh is None and tel.altitude_km is None and tel.fuel_fraction is None
    assert tel.status == "NO SIGNAL"


@pytest.mark.parametrize(
    "st, expected",
    [
        (status(age=0.1), None),
        (status(age=2.34), "STALE 2.3S"),
        (status(ConnState.LOST, age=5.0), "SIGNAL LOST"),
        (status(ConnState.CONNECTING, age=None), "NO SIGNAL"),
    ],
)
def test_status_text(st, expected):
    assert status_text(st) == expected
