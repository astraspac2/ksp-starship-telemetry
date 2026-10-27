import pytest

from ground_station.countdown import PILL_FADE_DURATION, PILL_HIDE_AT, format_clock, pill_state


@pytest.mark.parametrize(
    "t, expected",
    [
        (-36.0, ("T-", "00:00:36")),
        (-35.2, ("T-", "00:00:36")),  # still 36 whole seconds remaining until -35.0
        (-35.0, ("T-", "00:00:35")),
        (-0.4, ("T-", "00:00:01")),
        (0.0, ("T+", "00:00:00")),
        (0.9, ("T+", "00:00:00")),
        (143.0, ("T+", "00:02:23")),
        (-173.0, ("T-", "00:02:53")),
        (3725.0, ("T+", "01:02:05")),
    ],
)
def test_format_clock(t, expected):
    assert format_clock(t) == expected


def test_pill_fully_visible_before_t_minus_30():
    state = pill_state(-60.0)
    assert state.visible and state.opacity == 1.0 and state.x_offset == 0.0


def test_pill_starts_fading_at_t_minus_30():
    state = pill_state(PILL_HIDE_AT)
    assert state.visible and state.opacity == pytest.approx(1.0)


def test_pill_halfway_through_fade():
    state = pill_state(PILL_HIDE_AT + PILL_FADE_DURATION / 2)
    assert state.opacity == pytest.approx(0.5)
    assert state.x_offset < 0.0


def test_pill_hidden_after_fade():
    state = pill_state(PILL_HIDE_AT + PILL_FADE_DURATION)
    assert not state.visible and state.opacity == 0.0
    assert not pill_state(-5.0).visible
    assert not pill_state(100.0).visible
