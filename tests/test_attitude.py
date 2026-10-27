import math

import pytest

from ground_station.attitude import (
    MIN_LENGTH_RATIO,
    VIEW_ELEVATION_DEG,
    compass_point,
    nose_direction,
    rocket_view,
)


def test_a_standing_rocket_points_straight_up_on_the_screen():
    view = rocket_view(90.0, 0.0)
    assert view.angle_deg == pytest.approx(0.0, abs=1e-6)
    assert view.length_ratio == pytest.approx(1.0)


def test_heading_does_not_matter_for_a_standing_rocket():
    assert rocket_view(90.0, 200.0).angle_deg == pytest.approx(0.0, abs=1e-6)


def test_nose_direction_is_a_unit_vector_along_the_compass():
    east, north, up = nose_direction(0.0, 90.0)
    assert (east, north, up) == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)
    assert math.sqrt(sum(c * c for c in nose_direction(37.0, 211.0))) == pytest.approx(1.0)


def test_pitching_over_to_the_east_tilts_the_rocket_to_a_side():
    assert 0.0 < abs(rocket_view(45.0, 90.0).angle_deg) < 90.0


def test_opposite_headings_tilt_opposite_ways():
    east, west = rocket_view(45.0, 90.0), rocket_view(45.0, 270.0)
    assert east.angle_deg * west.angle_deg < 0


def test_pointing_at_the_camera_is_drawn_short_but_never_vanishes():
    towards_viewer = rocket_view(0.0, 180.0 + (-35.0))  # the horizon direction facing the camera
    assert towards_viewer.length_ratio >= MIN_LENGTH_RATIO


def test_compass_points_lie_on_the_squashed_horizon_ellipse():
    squash = math.sin(math.radians(VIEW_ELEVATION_DEG))
    for heading in (0, 45, 90, 180, 300):
        x, y = compass_point(heading)
        assert (x / 1.0) ** 2 + (y / squash) ** 2 == pytest.approx(1.0)


def test_north_sits_on_the_far_side_to_the_left():
    x, y = compass_point(0.0)
    assert x < 0.0 and y > 0.0
    xs, ys = compass_point(180.0)
    assert (xs, ys) == pytest.approx((-x, -y))


def _axes_for(pitch, heading, roll):
    from ground_station.render3d import body_to_world

    m = body_to_world(pitch, heading, roll)
    return tuple(m[:, 0]), tuple(m[:, 1]), tuple(m[:, 2])


@pytest.mark.parametrize("pitch, heading, roll", [(0, 0, 0), (35, 120, 40), (-20, 300, -150), (89.9, 10, 75), (90, 0, -30), (-90, 200, 10), (60, 359, 179)])
def test_attitude_from_rotation_round_trips_through_the_renderer_axes(pitch, heading, roll):
    from attitude_helpers import quaternion_from_axes
    from ground_station.attitude import attitude_from_rotation
    from ground_station.render3d import body_to_world
    import numpy as np

    right, nose, top = _axes_for(pitch, heading, roll)
    got = attitude_from_rotation(quaternion_from_axes(right, nose, top))
    assert np.allclose(body_to_world(*got), body_to_world(pitch, heading, roll), atol=1e-6)  # the same orientation, even at the pole
    if abs(pitch) < 89:
        assert got[0] == pytest.approx(pitch, abs=1e-6)
        assert got[1] == pytest.approx(heading % 360, abs=1e-6)
        assert got[2] == pytest.approx(roll, abs=1e-6)


def test_a_right_wing_dropping_is_a_negative_roll():
    from attitude_helpers import quaternion_from_axes
    from ground_station.attitude import attitude_from_rotation
    import math

    a = math.radians(30)
    nose = (0.0, 1.0, 0.0)  # level, heading north
    right = (math.cos(a), 0.0, -math.sin(a))  # the right wing is down
    top = (math.sin(a), 0.0, math.cos(a))  # the top leans to the right
    pitch, heading, roll = attitude_from_rotation(quaternion_from_axes(right, nose, top))
    assert (round(pitch, 3), round(heading, 3), round(roll, 3)) == (0.0, 0.0, -30.0)
