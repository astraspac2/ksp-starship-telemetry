import dataclasses
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ground_station.bar import GLOW_STEP, TelemetryBar
from ground_station.heating import COOL_RATE, DESCENT_FROM, GLOW_FULL, GLOW_STARTS, HEAT_RATE, eased_glow, glow_target
from ground_station.render3d import ModelRenderer, body_to_world, glow_colour
from ground_station.starship_model import starship_stack
from ground_station.telemetry import mock_telemetry


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_the_shield_stays_dark_in_thin_air_and_on_the_way_up():
    assert glow_target(100.0, 2000.0, -200.0) == 0.0  # thin air: no glow
    assert glow_target(30_000.0, 500.0, 300.0) == 0.0  # max-Q on the climb, going up
    assert glow_target(30_000.0, 500.0, -DESCENT_FROM + 1) == 0.0  # barely sinking
    assert glow_target(None, 2000.0, -200.0) == glow_target(1000.0, None, -200.0) == glow_target(1000.0, 2000.0, None) == 0.0  # unknown: dark


def test_the_glow_grows_with_the_heating_and_tops_out():
    steps = [glow_target(q, 1500.0, -250.0) for q in (200.0, 2000.0, 6000.0, 12000.0, 40000.0)]
    assert steps == sorted(steps) and steps[0] == 0.0 and steps[-1] == 1.0
    assert glow_target(GLOW_STARTS / 1500.0, 1500.0, -250.0) == pytest.approx(0.0)
    assert glow_target(GLOW_FULL / 1500.0, 1500.0, -250.0) == pytest.approx(1.0)


def test_the_glow_heats_up_quickly_and_cools_slowly():
    up = eased_glow(0.0, 1.0, 1.0)
    down = 1.0 - eased_glow(1.0, 0.0, 1.0)
    assert up == pytest.approx(HEAT_RATE) and down == pytest.approx(COOL_RATE) and up > down
    assert eased_glow(0.5, 0.5, 1.0) == 0.5 and eased_glow(0.9, 1.0, 10.0) == 1.0  # it never overshoots


def test_the_heat_shield_faces_are_marked_and_the_steel_is_not():
    mesh = starship_stack()
    assert mesh.face_heat is not None and len(mesh.face_heat) == len(mesh.faces)
    share = float((mesh.face_heat > 0).mean())
    assert 0.05 < share < 0.6  # the tiles and the flaps' black faces: a part of the ship, not all of it
    assert float(mesh.face_heat[: 1].max()) >= 0.0 and mesh.face_heat.max() == 1.0


def red_minus_blue(renderer, glow):
    image = renderer.render_matrix(body_to_world(75, 20, 0), 1.0, False, glow).convertToFormat(renderer_format())
    ptr = image.constBits()
    array = np.frombuffer(ptr, dtype=np.uint8).reshape(image.height(), image.width(), 4).astype(float)
    visible = array[:, :, 3] > 0
    return float((array[:, :, 2][visible] - array[:, :, 0][visible]).mean())  # BGRA: red channel is index 2


def renderer_format():
    from PySide6.QtGui import QImage

    return QImage.Format_ARGB32


def test_a_glowing_shield_is_redder_and_the_glow_colour_runs_from_red_to_white(qapp):
    renderer = ModelRenderer(starship_stack(), 200)
    cold, hot = red_minus_blue(renderer, 0.0), red_minus_blue(renderer, 0.7)
    assert hot - cold > 5.0  # more red against blue over the ship (the steel stays steel)
    low, mid, high = glow_colour(0.0), glow_colour(0.55), glow_colour(1.0)
    assert low[0] > low[1] > low[2] and mid[0] == 1.0 and high[2] > mid[2] + 0.4  # red, orange, then white-hot


def test_the_dial_draws_the_glow_only_when_asked_and_eases_it(qapp, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("ground_station.bar.time.monotonic", lambda: clock[0])
    base = dataclasses.replace(mock_telemetry(300.0, 143.0), separated_at=143.0, heading_deg=90.0, pitch_deg=60.0, roll_deg=0.0)
    bar = TelemetryBar()
    bar.set_telemetry(dataclasses.replace(base, heat_glow=0.0))
    cold = bar._rocket_image(bar._telemetry)
    bar.set_telemetry(dataclasses.replace(base, heat_glow=1.0))
    clock[0] += 0.2
    bar._rocket_image(bar._telemetry)
    assert 0.0 < bar._glow_shown < 1.0  # on its way up, not a jump
    for _ in range(10):
        clock[0] += 0.25
        hot = bar._rocket_image(bar._telemetry)
    assert bar._glow_shown == pytest.approx(1.0) and hot is not cold
    bar.set_reentry_glow(False)  # switched off: it cools away
    for _ in range(40):
        clock[0] += 0.25
        bar._rocket_image(bar._telemetry)
    assert bar._glow_shown == 0.0 and GLOW_STEP > 0


def alpha_outside_the_ship(image, cold_image):
    """How much of the picture is lit where the ship itself is not."""
    def alpha(img):
        img = img.convertToFormat(renderer_format())
        return np.frombuffer(img.constBits(), dtype=np.uint8).reshape(img.height(), img.width(), 4)[:, :, 3].astype(float)

    outside = alpha(cold_image) == 0
    return float(alpha(image)[outside].sum())


def test_a_glowing_shield_has_a_halo_round_it_and_a_cold_one_has_none(qapp):
    renderer = ModelRenderer(starship_stack(), 200)
    axes = body_to_world(75, 20, 0)
    cold = renderer.render_matrix(axes, 1.0, False, 0.0)
    hot = renderer.render_matrix(axes, 1.0, False, 0.9)
    assert alpha_outside_the_ship(cold, cold) == 0.0
    assert alpha_outside_the_ship(hot, cold) > 2000.0  # light spills past the ship's outline


def test_the_shield_flickers_from_tick_to_tick_but_a_tick_always_looks_the_same(qapp):
    renderer = ModelRenderer(starship_stack(), 200)
    axes = body_to_world(75, 20, 0)
    first = renderer.render_matrix(axes, 1.0, False, 0.8, 4)
    again = renderer.render_matrix(axes, 1.0, False, 0.8, 4)
    other = renderer.render_matrix(axes, 1.0, False, 0.8, 5)
    steady = renderer.render_matrix(axes, 1.0, False, 0.8, 0)
    assert first == again and first != other and first != steady


def test_the_dial_redraws_for_a_new_flicker_tick_only_while_the_shield_is_hot_enough(qapp, monkeypatch):
    from ground_station.bar import FLICKER_FROM, FLICKER_HZ

    clock = [100.0]
    monkeypatch.setattr("ground_station.bar.time.monotonic", lambda: clock[0])
    base = dataclasses.replace(mock_telemetry(300.0, 143.0), separated_at=143.0, heading_deg=90.0, pitch_deg=60.0, roll_deg=0.0)
    bar = TelemetryBar()
    bar.set_telemetry(dataclasses.replace(base, heat_glow=0.0))
    picture = bar._rocket_image(bar._telemetry)
    clock[0] += 1.0
    assert bar._rocket_image(bar._telemetry) is picture  # cold: nothing changes
    bar._glow_shown = 0.5
    bar.set_telemetry(dataclasses.replace(base, heat_glow=0.5))
    first = bar._rocket_image(bar._telemetry)
    clock[0] += 1.0 / FLICKER_HZ + 0.01
    assert bar._rocket_image(bar._telemetry) is not first  # hot: a new tick, a new picture
    assert FLICKER_FROM < 0.5
