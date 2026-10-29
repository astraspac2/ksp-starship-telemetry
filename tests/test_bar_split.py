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


def gauge_ink(bar, centre_x):
    image = bar.grab().toImage()
    total = 0
    for y in range(int(GAUGE_Y) - 20, int(GAUGE_Y) + 20):
        for x in range(int(centre_x) - 50, int(centre_x) + 50):
            c = image.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
    return total


def test_a_booster_that_cannot_be_read_says_no_data_in_both_gauges(qapp):
    from ground_station.bar import GAUGE_RADIUS

    numbers = staged_bar(True, booster=(1269.0, 26.0))
    nothing = staged_bar(True)
    nothing.set_telemetry(dataclasses.replace(nothing._telemetry, booster_speed_kmh=None, booster_altitude_km=None))
    nothing.grab()
    nothing._changed_at -= 10.0
    for centre_x in (ENGINE_CENTER_X, DIAL_CENTER_X):
        assert gauge_ink(nothing, centre_x) > 0  # words are drawn
        assert gauge_ink(nothing, centre_x) < gauge_ink(numbers, centre_x)  # smaller than the numbers
    # and the words stay inside the ring
    image = nothing.grab().toImage()
    inside = sum(image.pixelColor(int(ENGINE_CENTER_X) + dx, int(GAUGE_Y)).red() for dx in range(-int(GAUGE_RADIUS * 0.7), int(GAUGE_RADIUS * 0.7)))
    assert inside > 0


def at_progress(seconds_in):
    """The bar part way through the change from the stage-sep layout to the split one: `seconds_in` after it began."""
    import time

    base = dataclasses.replace(mock_telemetry(150.0, 143.0), separated_at=143.0, heading_deg=90.0, pitch_deg=80.0, roll_deg=0.0)
    bar = TelemetryBar()
    bar.set_telemetry(base)
    bar.grab()
    bar._changed_at -= 10.0
    bar.set_telemetry(dataclasses.replace(base, t=300.0, booster_live=True, booster_speed_kmh=1792.0, booster_altitude_km=88.7))
    bar.grab()  # notices the change and starts its clock
    bar._changed_at = time.monotonic() - seconds_in
    return bar


def region_ink(bar, x0, x1, y0, y1):
    image = bar.grab().toImage()
    return sum(
        image.pixelColor(x, y).red() + image.pixelColor(x, y).green() + image.pixelColor(x, y).blue()
        for y in range(int(y0), int(y1))
        for x in range(int(x0), int(x1))
    )


def test_a_leaving_engine_cluster_loses_its_dots_before_its_ring(qapp):
    from ground_station.bar import GAUGE_RADIUS

    r = GAUGE_RADIUS
    inside = (ENGINE_CENTER_X - r * 0.6, ENGINE_CENTER_X + r * 0.6, GAUGE_Y - r * 0.6, GAUGE_Y + r * 0.6)  # the dots
    top_ring = (ENGINE_CENTER_X - 10, ENGINE_CENTER_X + 10, GAUGE_Y - r - 4, GAUGE_Y - r + 4)  # the top of the ring
    start, middle = at_progress(0.0), at_progress(0.28)  # a little over half way through the leaving
    assert region_ink(middle, *inside) < region_ink(start, *inside) * 0.25  # the dots are nearly gone
    assert region_ink(middle, *top_ring) > region_ink(start, *top_ring) * 0.5  # while the ring is still there


def test_an_arriving_gauge_shows_its_label_before_its_number(qapp):
    from ground_station.bar import GAUGE_RADIUS

    r = GAUGE_RADIUS
    label = (ENGINE_CENTER_X - 40, ENGINE_CENTER_X + 40, GAUGE_Y - r * 0.575 - 2, GAUGE_Y - r * 0.575 + 16)  # SPEED
    number = (ENGINE_CENTER_X - 55, ENGINE_CENTER_X + 55, GAUGE_Y - 22, GAUGE_Y + 22)
    early, done = at_progress(0.75), at_progress(1.5)  # the arrival starts at 0.56 s
    assert region_ink(early, *label) > 0.3 * region_ink(done, *label)  # the label is already coming in
    assert region_ink(early, *number) < 0.3 * region_ink(done, *number)  # the number is not yet


def test_the_3d_dial_shrinks_away(qapp):
    from ground_station.bar import DIAL_RADIUS

    whole = (DIAL_CENTER_X - DIAL_RADIUS, DIAL_CENTER_X + DIAL_RADIUS, GAUGE_Y - DIAL_RADIUS, GAUGE_Y + DIAL_RADIUS)
    edge = (DIAL_CENTER_X + DIAL_RADIUS * 0.75, DIAL_CENTER_X + DIAL_RADIUS + 2, GAUGE_Y - 8, GAUGE_Y + 8)  # near its right rim
    start, middle = at_progress(0.0), at_progress(0.28)
    assert region_ink(middle, *edge) < region_ink(start, *edge) * 0.7  # the rim has pulled in
    assert region_ink(middle, *whole) < region_ink(start, *whole)
