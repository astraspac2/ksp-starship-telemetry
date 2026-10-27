import pytest

from ground_station.clock import COUNTDOWN_HOLD, ClockState, CountdownClock


def test_idle_clock_does_not_count():
    clock = CountdownClock(60.0)
    assert clock.state is ClockState.IDLE
    assert clock.advance(1000.0, False, 0.0) == -60.0
    assert clock.advance(1030.0, False, 0.0) == -60.0


def test_start_counts_on_game_time():
    clock = CountdownClock(60.0)
    clock.advance(1000.0, False, 0.0)
    clock.start()
    assert clock.advance(1000.0, False, 0.0) == pytest.approx(-60.0)
    assert clock.advance(1010.0, False, 0.0) == pytest.approx(-50.0)


def test_hold_freezes_and_resume_continues_from_the_held_value():
    clock = CountdownClock(60.0)
    clock.start()
    clock.advance(1000.0, False, 0.0)
    assert clock.advance(1020.0, False, 0.0) == pytest.approx(-40.0)
    clock.hold()
    assert clock.state is ClockState.HELD
    assert clock.advance(1500.0, False, 0.0) == pytest.approx(-40.0)  # game time passes while held
    clock.resume()
    assert clock.advance(1500.0, False, 0.0) == pytest.approx(-40.0)  # re-anchored at the held value
    assert clock.advance(1505.0, False, 0.0) == pytest.approx(-35.0)


def test_hold_and_resume_are_ignored_in_the_wrong_state():
    clock = CountdownClock(60.0)
    clock.hold()
    clock.resume()
    assert clock.state is ClockState.IDLE


def test_reset_rearms_at_a_new_time():
    clock = CountdownClock(60.0)
    clock.start()
    clock.advance(1000.0, False, 0.0)
    clock.advance(1030.0, False, 0.0)
    clock.reset(120.0)
    assert clock.state is ClockState.IDLE
    assert clock.advance(1040.0, False, 0.0) == -120.0
    assert clock.countdown_seconds == 120.0


def test_holds_at_zero_waiting_for_the_game_to_launch():
    clock = CountdownClock(10.0)
    clock.start()
    clock.advance(1000.0, False, 0.0)
    assert clock.advance(1100.0, False, 0.0) == COUNTDOWN_HOLD


def test_demo_clock_runs_on_through_zero():
    clock = CountdownClock(10.0, hold_at_zero=False)
    clock.start()
    clock.advance(1000.0, False, 0.0)
    assert clock.advance(1025.0, False, 0.0) == pytest.approx(15.0)


def test_launch_switches_to_mission_time_even_while_idle():
    clock = CountdownClock(60.0)
    assert clock.advance(1000.0, True, 8.0) == 8.0


def test_abort_freezes_the_countdown_until_reset():
    clock = CountdownClock(60.0)
    clock.start()
    clock.advance(1000.0, False, 0.0)
    clock.advance(1020.0, False, 0.0)
    clock.abort()
    assert clock.state is ClockState.ABORTED
    assert clock.advance(1080.0, False, 0.0) == pytest.approx(-40.0)
    clock.start()  # start does nothing from an abort
    assert clock.state is ClockState.ABORTED
    clock.reset()
    assert clock.state is ClockState.IDLE


def test_abort_is_ignored_when_idle_or_after_liftoff():
    clock = CountdownClock(60.0)
    clock.abort()
    assert clock.state is ClockState.IDLE
    clock.start()
    clock.advance(1000.0, True, 5.0)  # launched
    clock.abort()
    assert clock.state is ClockState.RUNNING


def test_time_warp_follows_game_time_by_default():
    clock = CountdownClock(60.0)
    clock.start()
    clock.advance(1000.0, False, 0.0)
    assert clock.advance(1100.0, False, 0.0, warping=True) == pytest.approx(-0.5)  # held at the T-1 stop


def test_time_warp_can_hold_the_countdown():
    clock = CountdownClock(600.0, hold_in_warp=True)
    clock.start()
    clock.advance(1000.0, False, 0.0)
    assert clock.advance(1010.0, False, 0.0) == pytest.approx(-590.0)
    assert clock.advance(5000.0, False, 0.0, warping=True) == pytest.approx(-590.0)  # 4000 s of warped game time
    assert clock.advance(9000.0, False, 0.0, warping=True) == pytest.approx(-590.0)
    assert clock.advance(9005.0, False, 0.0, warping=False) == pytest.approx(-590.0)  # re-anchors when warp ends
    assert clock.advance(9015.0, False, 0.0) == pytest.approx(-580.0)


def test_no_game_time_means_no_progress():
    clock = CountdownClock(60.0)
    clock.start()
    clock.advance(1000.0, False, 0.0)
    clock.advance(1010.0, False, 0.0)
    assert clock.advance(None, False, 0.0) == pytest.approx(-50.0)
