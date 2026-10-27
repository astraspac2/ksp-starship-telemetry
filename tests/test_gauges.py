import math

import pytest

from ground_station.gauges import _engine_positions


@pytest.mark.parametrize("total", [0, 1, 2, 3, 6, 7, 9, 13, 20, 33, 40])
def test_one_dot_per_engine_inside_the_circle(total):
    points = _engine_positions(total)
    assert len(points) == total
    assert all(math.hypot(x, y) <= 0.93 for x, y in points)
    assert len(set((round(x, 3), round(y, 3)) for x, y in points)) == total  # no two dots overlap


def test_super_heavy_layout():
    radii = sorted({round(math.hypot(x, y), 2) for x, y in _engine_positions(33)})
    assert len(radii) == 3  # 3 centre, 10 inner, 20 outer


def test_the_ship_has_three_small_centre_engines_and_three_large_ones_around_them():
    from ground_station.gauges import _engine_dot_scale, _engine_positions

    positions = _engine_positions(6)
    assert len(positions) == 6
    centre, outer = positions[:3], positions[3:]
    assert max(abs(x) + abs(y) for x, y in centre) < 0.35  # the small ones sit together in the middle
    left, right, below = outer
    assert left[0] < 0 < right[0] and left[1] == right[1] < 0 < below[1] and below[0] == 0  # upper left, upper right, down
    assert [_engine_dot_scale(6, i) for i in range(6)] == [1.05] * 3 + [2.6] * 3
    assert _engine_dot_scale(33, 5) == 1.0
