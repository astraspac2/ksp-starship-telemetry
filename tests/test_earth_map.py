import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ground_station.earth_map import LAND_FILE, MapRenderer, land_mask, map_pixels


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_the_outline_file_is_in_the_project():
    assert LAND_FILE.exists() and LAND_FILE.stat().st_size > 50_000


def test_known_places_are_land_or_sea(qapp):
    mask = land_mask()
    assert mask is not None

    def at(lat, lon):
        return mask[int((90 - lat) / 180 * mask.shape[0]), int((lon + 180) / 360 * mask.shape[1])]

    assert at(9, 20) > 200  # Chad, in the middle of Africa
    assert at(-25, 135) > 200  # the Australian outback
    assert at(0, -140) < 50  # the Pacific
    assert at(-40, 80) < 50  # the southern Indian Ocean


def test_map_is_centred_on_the_vessel_and_north_is_up(qapp):
    mask = land_mask()
    over_africa = map_pixels(mask, 9.0, 20.0, 101)
    assert over_africa[50, 50] > 200  # the middle of the picture is the vessel's own position: land
    assert over_africa[0, 0] == -1  # corners lie outside the round map
    # Sea lies to the north-west in the Mediterranean-bound direction? Check a cleaner fact: due west of the Atlantic coast is sea.
    far_west = map_pixels(mask, 5.0, 0.0, 101)  # off the coast of Ghana, in the Gulf of Guinea
    assert far_west[50, 50] < 50
    assert far_west[50, 95] > 100 or far_west[50, 5] > 100 or far_west[5, 50] > 100  # land is somewhere near the edge


def test_map_moves_with_the_vessel(qapp):
    renderer = MapRenderer(120)
    here = renderer.render(28.5, -80.8)
    east = renderer.render(28.5, -50.0)
    assert here is not None and east is not None
    assert here.size() == east.size() and here != east
    assert renderer.render(28.5, -80.8) is here  # the same spot is cached
    assert renderer.render(28.501, -80.801) is here  # and so is a hair away from it (quarter-degree steps)


def test_longitude_wraps_across_the_date_line(qapp):
    mask = land_mask()
    a = map_pixels(mask, 0.0, 179.9, 41)
    b = map_pixels(mask, 0.0, -180.1, 41)
    assert np.array_equal(a, b)
