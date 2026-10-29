import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from ground_station.fonts import load_bundled_fonts
from ground_station.gauges import draw_engine_cluster
from ground_station.theme import STARSHIP

RADIUS = 70.0


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    load_bundled_fonts()
    return app


def dots_ink(grow, total=33, between=(0.0, 1.0)):
    """Brightness of the engine dots between two distances from the centre (as shares of the cluster radius)."""
    image = QImage(200, 200, QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    draw_engine_cluster(painter, QPointF(100, 100), RADIUS, 0.5, total, total, STARSHIP, (True,) * total, grow)
    painter.end()
    low, high = between
    return sum(
        image.pixelColor(x, y).red()
        for y in range(200)
        for x in range(200)
        if low * RADIUS <= math.hypot(x - 100, y - 100) < high * RADIUS
    )


def test_a_cluster_arriving_swells_in_from_the_centre_outwards(qapp):
    centre, middle, outer = (0.0, 0.3), (0.3, 0.5), (0.58, 0.76)  # the 3 centre engines, the ring of 10, the 20 outer ones
    early = (dots_ink(0.3, between=centre), dots_ink(0.3, between=middle), dots_ink(0.3, between=outer))
    assert early[0] > 0 and early[1] == 0 and early[2] == 0  # only the centre has come in
    later = (dots_ink(0.7, between=middle), dots_ink(0.7, between=outer))
    assert later[0] > 0 and 0 < later[1] < dots_ink(1.0, between=outer)  # the middle ring is there, the outer still coming
    assert dots_ink(1.0, between=outer) > 0


def test_the_ships_big_outer_engines_come_after_its_centre_three(qapp):
    centre, outer = (0.0, 0.3), (0.3, 0.8)
    assert dots_ink(0.2, total=6, between=centre) > 0 and dots_ink(0.2, total=6, between=outer) == 0
    assert dots_ink(0.8, total=6, between=outer) > 0
