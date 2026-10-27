import pytest

from ground_station.timeline import (
    PX_PER_SECOND,
    Milestone,
    bar_state,
    milestone_x,
    nearest_milestone,
    panels_state,
)

MILESTONES = [Milestone("Liftoff", 0.0), Milestone("Max Q", 70.0), Milestone("Stage Sep", 143.0)]


def test_bar_hidden_before_pill_leaves_then_fades_in():
    assert bar_state(-40.0).opacity == 0.0
    assert bar_state(-30.0).opacity == 0.0
    assert bar_state(-29.75).opacity == pytest.approx(0.5)
    assert bar_state(-10.0).opacity == 1.0


def test_panels_rise_from_t_minus_10():
    assert panels_state(-12.0).opacity == 0.0 and panels_state(-12.0).offset == 1.0
    mid = panels_state(-9.5)
    assert 0.0 < mid.opacity < 1.0 and 0.0 < mid.offset < 1.0
    done = panels_state(-5.0)
    assert done.opacity == 1.0 and done.offset == 0.0


def test_milestone_scrolls_left_as_time_passes():
    assert milestone_x(0.0, -19.0, 960.0) == pytest.approx(960 + 19 * PX_PER_SECOND)
    assert milestone_x(0.0, 0.0, 960.0) == 960.0
    assert milestone_x(0.0, 143.0, 960.0) < 960.0


def test_milestone_spacing_follows_time_gaps():
    gap_a = milestone_x(70.0, 0.0, 960.0) - milestone_x(0.0, 0.0, 960.0)
    gap_b = milestone_x(143.0, 0.0, 960.0) - milestone_x(70.0, 0.0, 960.0)
    assert gap_b / gap_a == pytest.approx(73.0 / 70.0)


@pytest.mark.parametrize("now, expected", [(-19.0, 0), (30.0, 0), (45.0, 1), (130.0, 2), (999.0, 2)])
def test_nearest_milestone(now, expected):
    assert nearest_milestone(now, MILESTONES) == expected


def test_curve_is_straight_on_the_pad_and_full_at_120_km():
    from ground_station.timeline import curve_amount

    assert curve_amount(None) == 0.0 and curve_amount(0.0) == 0.0 and curve_amount(-3.0) == 0.0
    assert curve_amount(60.0) == pytest.approx(0.5)
    assert curve_amount(120.0) == 1.0 and curve_amount(400.0) == 1.0


def test_curve_unbends_on_the_way_down():
    from ground_station.timeline import curve_amount

    assert curve_amount(90.0) == curve_amount(90.0)
    assert curve_amount(30.0) < curve_amount(90.0)


def test_sag_keeps_the_centre_level_and_drops_the_ends():
    from ground_station.timeline import MAX_SAG_PX, sag

    assert sag(960, 960, 510, 1.0) == 0.0
    assert sag(450, 960, 510, 1.0) == pytest.approx(MAX_SAG_PX) == sag(1470, 960, 510, 1.0)
    assert sag(450, 960, 510, 0.0) == 0.0


def test_labels_tilt_along_the_curve():
    from ground_station.timeline import tilt_degrees

    assert tilt_degrees(960, 960, 510, 1.0) == 0.0  # level at the centre
    assert tilt_degrees(700, 960, 510, 0.0) == 0.0  # straight line, no tilt
    left, right = tilt_degrees(700, 960, 510, 1.0), tilt_degrees(1220, 960, 510, 1.0)
    assert left < 0 < right and left == pytest.approx(-right)  # the line rises toward the centre, then falls away


def test_dot_turns_white_over_a_short_animation_once_passed():
    from ground_station.timeline import FILL_DURATION, passed_progress

    assert passed_progress(142.9, 143.0) == 0.0
    assert passed_progress(143.0, 143.0) == 0.0
    assert 0.0 < passed_progress(143.0 + FILL_DURATION / 2, 143.0) < 1.0
    assert passed_progress(143.0 + FILL_DURATION, 143.0) == pytest.approx(1.0)
    assert passed_progress(500.0, 143.0) == 1.0  # joining late: just a finished white dot
