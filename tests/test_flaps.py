import dataclasses
import math
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ground_station.bar import FLAP_STEP, TelemetryBar
from ground_station.flaps import AFT_FOLD_SCALE, FLAPS, FORWARD_FOLD_SCALE, MODULE_NAME, FlapTracker, fold_degrees
from ground_station.render3d import ModelRenderer
from ground_station.starship_model import starship_stack
from ground_station.telemetry import mock_telemetry

OUT = {"Deploy": "False", "Deploy Angle": "50", "Authority Limiter": "40", "Pitch": "True", "Yaw": "True", "Roll": "True"}  # on the pad, flaps out; the axes read True here = the flap does not answer them
RETRACTED = {**OUT, "Deploy": "True"}  # the game's Deploy field is True while the flaps are retracted


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# what the game reports -> how far in a flap is
def test_flaps_out_are_the_pose_the_model_is_drawn_in_and_retracting_folds_each_by_the_deploy_angle():
    for forward in (True, False):
        assert fold_degrees(OUT, forward, True, 0, 0, 0) == 0.0
    assert fold_degrees(RETRACTED, False, True, 0, 0, 0) == pytest.approx(50.0 * AFT_FOLD_SCALE) == pytest.approx(47.0)
    assert fold_degrees(RETRACTED, True, True, 0, 0, 0) == 50.0 * FORWARD_FOLD_SCALE == 30.0  # the forward flaps swing less far


def test_the_stick_moves_only_the_flaps_that_answer_that_axis():
    assert fold_degrees(RETRACTED, True, True, 1.0, 0, 0) == 30.0  # pitch is off for this flap: the stick does nothing
    pitching = {**RETRACTED, "Pitch": "False"}  # False = the flap answers pitch
    forward, aft = fold_degrees(pitching, True, True, 1.0, 0, 0), fold_degrees(pitching, False, True, 1.0, 0, 0)
    assert forward == pytest.approx(6.0) and aft == pytest.approx(90.0 * AFT_FOLD_SCALE)  # forward and aft go against each other; full stick is the authority limiter (40)
    rolling = {**RETRACTED, "Roll": "False"}
    assert fold_degrees(rolling, True, True, 0, 0, 1.0) != fold_degrees(rolling, True, False, 0, 0, 1.0)  # left and right go against each other


def test_the_fold_is_kept_within_sensible_limits():
    wild = {"Deploy": "False", "Deploy Angle": "500", "Authority Limiter": "40", "Pitch": "True"}
    assert fold_degrees({**wild, "Deploy": "True", "Pitch": "False"}, False, True, 0, 0, 0) == 90.0
    assert fold_degrees({**wild, "Deploy": "True", "Deploy Angle": "-500", "Pitch": "False"}, False, True, 0, 0, 0) == -90.0
    assert fold_degrees({"Deploy Angle": "x"}, True, True, 0, 0, 0) == 0.0  # unreadable numbers count as nothing, not a crash


# finding the flaps and reading them
class FakePart:
    def __init__(self, name, fields):
        self.modules = [SimpleNamespace(name="Other", fields={}), SimpleNamespace(name=MODULE_NAME, fields=fields)]
        self.name = name


class FakeVessel:
    def __init__(self, fields=None, missing=()):
        fields = fields if fields is not None else OUT
        self.control = SimpleNamespace(pitch=0.0, yaw=0.0, roll=0.0)
        self.parts = SimpleNamespace(with_name=lambda name: [] if name in missing else [FakePart(name, dict(fields))])


def conn_with(vessel):
    return SimpleNamespace(space_center=SimpleNamespace(active_vessel=vessel))


def test_the_four_flaps_are_read_in_order():
    tracker = FlapTracker()
    assert tracker.update(0.0, conn_with(FakeVessel(RETRACTED))) == (30.0, 30.0, 47.0, 47.0)
    assert len(FLAPS) == 4


def test_a_vessel_without_the_four_flaps_gives_nothing_and_is_looked_at_again_later():
    tracker = FlapTracker()
    broken = FakeVessel(missing={FLAPS[0][0]})
    assert tracker.update(0.0, conn_with(broken)) is None
    assert tracker.update(1.0, conn_with(FakeVessel())) is None  # not rescanned yet
    assert tracker.update(10.0, conn_with(FakeVessel())) == (0.0,) * 4


def test_readings_are_not_asked_for_more_than_a_few_times_a_second():
    tracker = FlapTracker()
    vessel = FakeVessel(OUT)
    assert tracker.update(0.0, conn_with(vessel)) == (0.0,) * 4
    vessel.parts = SimpleNamespace(with_name=lambda name: [FakePart(name, dict(RETRACTED))])
    assert tracker.update(0.05, conn_with(vessel)) == (0.0,) * 4  # too soon: the old reading
    tracker.reset()
    assert tracker.update(0.3, conn_with(vessel)) == (30.0, 30.0, 47.0, 47.0)


def test_a_game_that_stops_answering_gives_nothing_instead_of_old_flaps():
    class Dying(FakeVessel):
        @property
        def control(self):
            raise RuntimeError("gone")

        @control.setter
        def control(self, _):
            pass

    tracker = FlapTracker()
    assert tracker.update(0.0, conn_with(Dying())) is None


# the model's flaps
def test_the_ship_model_carries_its_four_flaps_as_hinged_parts():
    rigs = starship_stack().flaps
    assert sorted((r.forward, r.mirror) for r in rigs) == [(False, -1), (False, 1), (True, -1), (True, 1)]
    assert all(r.count > 0 for r in rigs)


def flap_vertices(renderer, rig):
    return renderer._vertices[rig.first:rig.first + rig.count]


def test_folding_swings_only_the_flaps_vertices_about_their_hinge():
    mesh = starship_stack()
    renderer = ModelRenderer(mesh, 64)
    rest = renderer._vertices.copy()
    assert renderer.set_flap_folds((0.0, 0.0, 0.0, 0.0)) and np.allclose(renderer._vertices, rest)  # fold 0 is the pose as built
    assert renderer.set_flap_folds((50.0, 0.0, 0.0, 0.0))
    moved = np.flatnonzero(np.abs(renderer._vertices - rest).max(axis=1) > 1e-9)
    first = mesh.flaps[0]  # forward, mirror +1 : the first of the four
    assert set(moved) <= set(range(first.first, first.first + first.count)) and len(moved) > 0
    assert np.allclose(renderer._vertices[:, 1], rest[:, 1])  # a swing about a vertical hinge never changes a height
    before = np.hypot(*(rest[moved][:, [0, 2]] - first.pivot).T)
    after = np.hypot(*(renderer._vertices[moved][:, [0, 2]] - first.pivot).T)
    assert np.allclose(before, after)  # every point keeps its distance from the hinge: it is turned, not stretched


def test_the_two_sides_swing_opposite_ways():
    mesh = starship_stack()
    renderer = ModelRenderer(mesh, 64)
    renderer.set_flap_folds((0.0, 0.0, 40.0, 40.0))
    left, right = mesh.flaps[1], mesh.flaps[3]
    assert (left.forward, left.mirror, right.mirror) == (False, 1, -1)
    rest = ModelRenderer(mesh, 64)._vertices

    def turned(rig):
        """The angle, round the hinge, the flap's tip has turned through (counter-clockwise seen from +Y is positive)."""
        tip = rig.first + 2  # the outer lower corner of the upper outline
        before = rest[tip][[0, 2]] - rig.pivot
        after = renderer._vertices[tip][[0, 2]] - rig.pivot
        return math.atan2(before[0] * after[1] - before[1] * after[0], float(before @ after))

    assert turned(left) * turned(right) < 0 and abs(abs(turned(left)) - math.radians(40)) < 1e-6  # equal turns, opposite ways


def test_putting_the_folds_back_restores_the_model_and_a_repeat_changes_nothing():
    renderer = ModelRenderer(starship_stack(), 64)
    rest = renderer._vertices.copy()
    assert renderer.set_flap_folds((30.0, 30.0, 30.0, 30.0)) is True
    assert renderer.set_flap_folds((30.0, 30.0, 30.0, 30.0)) is False
    assert renderer.set_flap_folds(None) is True
    assert np.allclose(renderer._vertices, rest)


def test_a_model_without_flaps_ignores_the_folds():
    from ground_station.mesh import builtin_rocket

    assert ModelRenderer(builtin_rocket(), 64).set_flap_folds((10.0, 10.0, 10.0, 10.0)) is False


# the dial
def tilted(folds):
    tel = dataclasses.replace(mock_telemetry(300.0, 143.0), separated_at=143.0, heading_deg=90.0, pitch_deg=60.0, roll_deg=0.0, flap_folds_deg=folds)
    return tel


def test_the_dial_redraws_when_the_flaps_move_and_not_when_they_do_not(qapp, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("ground_station.bar.time.monotonic", lambda: clock[0])
    bar = TelemetryBar()
    bar.set_telemetry(tilted((0.0,) * 4))
    first = bar._rocket_image(bar._telemetry)
    assert bar._rocket_image(bar._telemetry) is first  # nothing moved: the same picture
    bar.set_telemetry(tilted((50.0,) * 4))
    clock[0] += 0.2
    assert bar._rocket_image(bar._telemetry) is not first  # the flaps started to fold in
    assert 0.0 < bar._flap_shown[0] < 50.0


def test_the_flaps_swing_toward_the_game_instead_of_jumping(qapp, monkeypatch):
    bar = TelemetryBar()
    clock = [100.0]
    monkeypatch.setattr("ground_station.bar.time.monotonic", lambda: clock[0])
    bar.set_telemetry(tilted((0.0,) * 4))
    bar._rocket_image(bar._telemetry)
    bar.set_telemetry(tilted((50.0,) * 4))
    clock[0] += 0.2
    bar._rocket_image(bar._telemetry)
    assert 0.0 < bar._flap_shown[0] < 50.0  # on its way
    for _ in range(10):
        clock[0] += 0.2
        bar._rocket_image(bar._telemetry)
    assert bar._flap_shown[0] == pytest.approx(50.0)


def test_before_any_reading_the_flaps_are_retracted_as_on_the_pad(qapp):
    from ground_station.bar import FLAP_STOWED_FOLDS

    bar = TelemetryBar()
    bar.set_telemetry(tilted(None))
    bar._rocket_image(bar._telemetry)
    assert bar._flap_shown == FLAP_STOWED_FOLDS == (0.0,) * 4  # straight out, as on the pad
    assert all(abs(fold - stowed) < FLAP_STEP for fold, stowed in zip(bar._renderer._folds, FLAP_STOWED_FOLDS))  # drawn in steps


def test_when_the_readings_stop_the_flaps_stay_as_they_were_last_seen(qapp):
    bar = TelemetryBar()
    bar.set_telemetry(tilted((0.0,) * 4))
    bar._rocket_image(bar._telemetry)
    bar.set_telemetry(tilted(None))
    bar._rocket_image(bar._telemetry)
    assert bar._flap_shown == (0.0,) * 4  # not snapped back to retracted
    assert FLAP_STEP > 0


def test_a_flap_whose_fields_read_false_for_the_axes_follows_the_stick_as_the_games_panel_says_active():
    as_in_the_game = {**RETRACTED, "Pitch": "False", "Yaw": "False", "Roll": "False"}  # what the recorded flaps read: "Active" in the panel
    assert fold_degrees(as_in_the_game, True, True, 1.0, 0, 0) != fold_degrees(as_in_the_game, True, True, 0.0, 0, 0)
    assert fold_degrees(as_in_the_game, True, True, 0, 0, 1.0) != fold_degrees(as_in_the_game, True, True, 0, 0, 0.0)


def test_yaw_works_the_diagonal_pairs_against_each_other_and_only_where_the_flap_answers_it():
    active = {**RETRACTED, "Yaw": "False"}
    fwd_left, fwd_right = fold_degrees(active, True, True, 0, 1.0, 0), fold_degrees(active, True, False, 0, 1.0, 0)
    aft_left, aft_right = fold_degrees(active, False, True, 0, 1.0, 0), fold_degrees(active, False, False, 0, 1.0, 0)
    assert fwd_left / FORWARD_FOLD_SCALE == pytest.approx(aft_right / AFT_FOLD_SCALE) and fwd_right / FORWARD_FOLD_SCALE == pytest.approx(aft_left / AFT_FOLD_SCALE)  # forward-left with aft-right
    assert fwd_left != fwd_right
    assert fold_degrees(RETRACTED, True, True, 0, 1.0, 0) == 30.0  # yaw is off for this flap: the stick does nothing


def test_a_flap_with_deploy_false_does_not_follow_the_stick():
    out = {**OUT, "Pitch": "False", "Yaw": "False", "Roll": "False"}
    assert fold_degrees(out, True, True, 1.0, 1.0, 1.0) == fold_degrees(out, True, True, 0, 0, 0) == 0.0


def test_the_tracker_logs_a_row_only_when_something_about_the_flaps_changes(tmp_path):
    log = tmp_path / "flap-trace.csv"
    tracker = FlapTracker(log)
    vessel = FakeVessel(OUT)
    tracker.update(0.0, conn_with(vessel))
    tracker.update(0.3, conn_with(vessel))  # nothing changed: no row
    vessel.control.pitch = 0.5
    tracker.update(0.6, conn_with(vessel))  # the stick moved: a row
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and lines[0].startswith("t,error,input_pitch")
    assert "fwd_left_Deploy" in lines[0] and ",0.5," in lines[2]


def test_a_failure_is_logged_with_its_reason(tmp_path):
    class Dying(FakeVessel):
        @property
        def control(self):
            raise RuntimeError("gone")

        @control.setter
        def control(self, _):
            pass

    log = tmp_path / "flap-trace.csv"
    FlapTracker(log).update(0.0, conn_with(Dying()))
    assert "RuntimeError: gone" in log.read_text(encoding="utf-8")
