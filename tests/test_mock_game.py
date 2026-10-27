import pytest

from ground_station.mock_game import MockGame


def make():
    now = [100.0]
    return MockGame(now=lambda: now[0], start_ut=1000.0), now


def test_game_time_follows_real_time_by_default():
    game, now = make()
    now[0] = 110.0
    assert game.ut() == pytest.approx(1010.0)


def test_pause_stops_game_time():
    game, now = make()
    game.paused = True
    now[0] = 130.0
    assert game.ut() == pytest.approx(1000.0)
    game.paused = False
    now[0] = 135.0
    assert game.ut() == pytest.approx(1005.0)


def test_time_warp_multiplies_game_time():
    game, now = make()
    game.warp = 10.0
    now[0] = 105.0
    assert game.ut() == pytest.approx(1050.0)
    assert game.warping


def test_lag_spike_freezes_the_game_for_a_while():
    game, now = make()
    now[0] = 102.0
    game.freeze(5.0)
    assert game.frozen
    now[0] = 106.0
    assert game.ut() == pytest.approx(1002.0)  # nothing advanced during the freeze
    now[0] = 109.0
    assert game.ut() == pytest.approx(1004.0)  # 2 s of the 3 s elapsed were after the freeze ended
    assert not game.frozen


def test_jump_moves_game_time_without_losing_the_present():
    game, now = make()
    now[0] = 110.0
    game.jump(-60.0)
    assert game.ut() == pytest.approx(950.0)
    now[0] = 112.0
    assert game.ut() == pytest.approx(952.0)
