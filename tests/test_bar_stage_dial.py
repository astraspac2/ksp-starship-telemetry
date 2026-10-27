import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dataclasses

import pytest
from PySide6.QtWidgets import QApplication

from ground_station.bar import ENGINE_CENTER_X, GAUGE_RADIUS, GAUGE_Y, TelemetryBar
from ground_station.fonts import load_bundled_fonts
from ground_station.telemetry import mock_telemetry


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    load_bundled_fonts()
    return app


def brightness(bar):
    """Total brightness of the left-hand engine dial's area."""
    image = bar.grab().toImage()
    r = int(GAUGE_RADIUS)
    total = 0
    for y in range(int(GAUGE_Y) - r, int(GAUGE_Y) + r, 2):
        for x in range(int(ENGINE_CENTER_X) - r, int(ENGINE_CENTER_X) + r, 2):
            c = image.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
    return total


def test_booster_dial_keeps_its_lit_engines_after_separation_until_the_flight_layout(qapp):
    bar = TelemetryBar()
    lit = (True,) * 5 + (False,) * 28
    before = dataclasses.replace(mock_telemetry(140.0), engines_on=5, engines_total=33, engine_lit=lit, fuel_fraction=0.14)
    bar.set_telemetry(before)
    with_five_lit = brightness(bar)

    after = dataclasses.replace(mock_telemetry(146.0, 143.0), separated_at=143.0)  # the ship's readings: 6 engines
    bar.set_telemetry(after)
    bar._changed_at -= 10.0  # let any fade finish
    held = brightness(bar)
    assert held == pytest.approx(with_five_lit, rel=0.02)  # still the booster's five lit engines and its ring

    never_lit = TelemetryBar()
    never_lit.set_telemetry(dataclasses.replace(after))
    never_lit._changed_at -= 10.0
    assert brightness(never_lit) < with_five_lit  # with no memory of the booster, the dial is dark


def test_the_map_replaces_the_engine_dial_and_shows_the_vessel_dot(qapp):
    bar = TelemetryBar()
    tel = dataclasses.replace(mock_telemetry(60.0), engines_on=33, engines_total=33)
    bar.set_telemetry(tel)
    engines = brightness(bar)
    bar.set_show_map(True)
    bar.grab()  # the change begins here: the engine dial fades out and the map fades in
    bar._changed_at -= 10  # let the fade finish
    mapped = brightness(bar)
    assert mapped != engines  # a different picture is drawn in the dial
    bar._changed_at -= 10
    centre = bar.grab().toImage().pixelColor(int(ENGINE_CENTER_X), int(GAUGE_Y))
    assert centre.red() > 200 and centre.green() > 200  # the vessel's dot is bright at the centre of the map


def test_the_map_says_so_when_there_is_no_position(qapp):
    bar = TelemetryBar()
    bar.set_show_map(True)
    tel = dataclasses.replace(mock_telemetry(60.0), latitude_deg=None, longitude_deg=None)
    bar.set_telemetry(tel)
    image = bar.grab().toImage()
    above = image.pixelColor(int(ENGINE_CENTER_X), int(GAUGE_Y) - 25)
    assert above.red() < 120  # a plain dark face: no land, no vessel dot, only the "NO POSITION" note in the middle


def test_engine_dots_ease_between_lit_and_dim(qapp):
    bar = TelemetryBar()
    lit = (True,) * 5 + (False,) * 28
    off = (False,) * 33
    first = bar._levels_for("booster", 5, 33, lit)
    assert first[:5] == [1.0] * 5 and first[5] == 0.0  # the first look starts where it should be
    bar._dot_time["booster"] -= 0.12  # one fade time later, with the engines now off
    easing = bar._levels_for("booster", 0, 33, off)
    assert 0.3 < easing[0] < 0.4  # about a third of the way left: it dims instead of jumping
    bar._dot_time["booster"] -= 5.0
    assert bar._levels_for("booster", 0, 33, off)[0] < 0.01
    bar.set_smoothing(False)
    assert bar._levels_for("booster", 5, 33, lit) is None  # exact frames: dots jump


def test_the_3d_dial_turns_smoothly_rather_than_in_steps(qapp):
    import numpy as np
    from ground_station.render3d import body_to_world

    bar = TelemetryBar()
    steady = dataclasses.replace(mock_telemetry(60.0), pitch_deg=40.0, heading_deg=90.0, roll_deg=0.0)
    bar._rocket_image(steady)  # the dial starts at the real attitude
    turned = dataclasses.replace(steady, roll_deg=30.0)
    bar._attitude_time -= 0.07  # one ease time later
    bar._rocket_image(turned)
    shown, target = bar._attitude, body_to_world(50.0, 90.0, 30.0)
    start = body_to_world(50.0, 90.0, 0.0)
    assert not np.allclose(shown, target) and not np.allclose(shown, start)  # part way there, not at either end
    assert np.allclose(shown.T @ shown, np.eye(3), atol=1e-6)  # still a true rotation
    bar._attitude_time -= 0.3
    bar._rocket_image(turned)
    bar._attitude_time -= 5.0  # a long pause: the dial starts again from the real attitude
    bar._rocket_image(turned)
    assert np.allclose(bar._attitude, target)
