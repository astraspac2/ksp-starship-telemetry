import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dataclasses

import pytest
from PySide6.QtWidgets import QApplication

from ground_station.bar import ALTITUDE_CENTER_X, DIAL_CENTER_X, ENGINE_CENTER_X, GAUGE_Y, SIDE_LABEL_Y, SPEED_CENTER_X, TelemetryBar
from ground_station.fonts import load_bundled_fonts
from ground_station.layout import Layout
from ground_station.telemetry import mock_telemetry


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    load_bundled_fonts()
    return app


def label_ink(bar, centre_x):
    """How much text-coloured ink sits in the strip where a side label would be, between the two gauges of a pair."""
    image = bar.grab().toImage()
    total = 0
    for y in range(int(SIDE_LABEL_Y) - 7, int(SIDE_LABEL_Y) + 7):
        for x in range(int(centre_x) - 45, int(centre_x) + 45):
            c = image.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
    return total


def staged_bar(booster_live, booster=(1500.0, 80.0)):
    bar = TelemetryBar()
    tel = dataclasses.replace(
        mock_telemetry(300.0, 143.0),
        separated_at=143.0,
        booster_live=booster_live,
        booster_speed_kmh=booster[0] if booster_live else None,
        booster_altitude_km=booster[1] if booster_live else None,
    )
    bar.set_telemetry(tel)
    bar.grab()
    bar._changed_at -= 10.0  # let any fade finish
    return bar


def test_the_names_and_the_booster_numbers_show_while_the_booster_is_read(qapp):
    with_booster, without = staged_bar(True), staged_bar(False)
    left, right = (ENGINE_CENTER_X + DIAL_CENTER_X) / 2, (SPEED_CENTER_X + ALTITUDE_CENTER_X) / 2
    assert label_ink(with_booster, left) > label_ink(without, left) * 1.5  # SUPER HEAVY
    assert label_ink(with_booster, right) > label_ink(without, right) * 1.5  # STARSHIP


def test_the_left_gauges_show_the_boosters_values_and_not_the_ships(qapp):
    bar = staged_bar(True, booster=(1500.0, 80.0))
    assert bar._shown[ENGINE_CENTER_X] == "booster_speed" and bar._shown[DIAL_CENTER_X] == "booster_altitude"
    flying = staged_bar(False)
    assert flying._shown[ENGINE_CENTER_X] == "speed" and flying._shown[DIAL_CENTER_X] == "altitude"


def test_the_names_fade_out_again_when_the_booster_is_gone(qapp):
    bar = staged_bar(True)
    left = (ENGINE_CENTER_X + DIAL_CENTER_X) / 2
    shown = label_ink(bar, left)
    bar.set_telemetry(dataclasses.replace(bar._telemetry, booster_live=False, booster_speed_kmh=None, booster_altitude_km=None))
    bar.grab()
    bar._changed_at -= 10.0
    assert label_ink(bar, left) < shown / 1.5


def booster_flying_bar():
    bar = TelemetryBar()
    lit = (True,) * 13 + (False,) * 20
    tel = dataclasses.replace(
        mock_telemetry(300.0),  # the vessel flown has the booster's 33 engines again, after the separation was seen
        engines_on=13, engines_total=33, engine_lit=lit, separated_at=143.0, on_booster=True,
        booster_live=True, booster_speed_kmh=1500.0, booster_altitude_km=80.0,
    )
    bar.set_telemetry(tel)
    bar.grab()
    bar._changed_at -= 10.0
    return bar


def test_flying_the_booster_after_the_separation_brings_back_its_own_arrangement(qapp):
    bar = booster_flying_bar()
    assert bar._flying_booster
    assert bar._shown[ENGINE_CENTER_X] == "booster" and bar._shown[DIAL_CENTER_X] == "dial"  # its engines and its dial
    assert bar._shown[SPEED_CENTER_X] == "speed" and bar._shown[ALTITUDE_CENTER_X] == "altitude"  # its own numbers
    assert bar._shown_arrangement is Layout.STAGE_1  # not the split one, so no SUPER HEAVY / STARSHIP names


def test_a_stack_before_the_separation_is_not_taken_for_the_booster(qapp):
    bar = TelemetryBar()
    tel = dataclasses.replace(mock_telemetry(100.0), engines_on=33, engines_total=33, on_booster=True)  # separated_at is None
    bar.set_telemetry(tel)
    bar.grab()
    assert not bar._flying_booster


def test_the_boosters_model_is_the_booster_alone(qapp):
    from ground_station.bar import TelemetryBar as Bar
    from ground_station.render3d import body_to_world

    bar = Bar()
    axes = body_to_world(80.0, 90.0, 0.0)
    stack = bar._renderer.render_matrix(axes, 0.0, False)
    booster = bar._renderer.render_matrix(axes, 0.0, True)

    def ink(image):
        return sum(1 for y in range(0, image.height(), 3) for x in range(0, image.width(), 3) if image.pixelColor(x, y).alpha() > 0)

    assert 0 < ink(booster) and ink(booster) != ink(stack)
