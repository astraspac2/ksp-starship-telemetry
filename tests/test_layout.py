import pytest

from ground_station.layout import Layout, is_stage_sep, layout_for, stage_sep_time, staged
from ground_station.telemetry import mock_telemetry
from ground_station.timeline import Milestone


@pytest.mark.parametrize("name", ["Stage Sep", "STAGE SEP", "stage sep", "Stage Separation", "STAGE SEPARATION", "  stage   sep "])
def test_stage_sep_names_match_in_any_case(name):
    assert is_stage_sep(name)


@pytest.mark.parametrize("name", ["Staging", "Stage 2 ignition", "Max Q", "Sep"])
def test_other_names_do_not_match(name):
    assert not is_stage_sep(name)


def test_finds_the_marker_time_or_none():
    marks = [Milestone("LIFTOFF", 0.0), Milestone("STAGE SEP", 143.0)]
    assert stage_sep_time(marks) == 143.0
    assert stage_sep_time([Milestone("LIFTOFF", 0.0)]) is None


def test_arrangements_follow_the_marker():
    sep = 143.0
    assert layout_for(-30, sep) is Layout.STAGE_1
    assert layout_for(137.9, sep) is Layout.STAGE_1
    assert layout_for(138.0, sep) is Layout.STAGE_SEP  # five seconds before
    assert layout_for(152.9, sep) is Layout.STAGE_SEP
    assert layout_for(153.0, sep) is Layout.FLIGHT  # ten seconds after
    assert layout_for(400, sep) is Layout.FLIGHT


def test_without_a_marker_the_bar_never_changes():
    assert layout_for(500, None) is Layout.STAGE_1 and not staged(500, None)


def test_staged_only_once_the_separation_was_seen():
    assert not staged(500.0, None)  # the marker time alone never counts
    assert not staged(77.9, 78.0) and staged(78.0, 78.0)


def test_a_separation_earlier_than_planned_switches_the_bar_at_once():
    assert layout_for(70, 143.0) is Layout.STAGE_1
    assert layout_for(70, 143.0, 70.0) is Layout.STAGE_SEP
    assert layout_for(79.9, 143.0, 70.0) is Layout.STAGE_SEP
    assert layout_for(80.0, 143.0, 70.0) is Layout.FLIGHT  # ten seconds after the real separation, not the planned one


def test_a_separation_later_than_planned_keeps_the_stage_sep_arrangement_until_it_happens():
    assert layout_for(138, 143.0) is Layout.STAGE_SEP
    assert layout_for(160, 143.0) is Layout.FLIGHT  # without it, the planned time decides
    assert layout_for(160, 143.0, 158.0) is Layout.STAGE_SEP  # but once seen, ten seconds count from the real one
    assert layout_for(168.0, 143.0, 158.0) is Layout.FLIGHT


def test_a_separation_without_any_marker_still_changes_the_bar():
    assert layout_for(100, None) is Layout.STAGE_1
    assert layout_for(100, None, 100.0) is Layout.STAGE_SEP
    assert layout_for(110, None, 100.0) is Layout.FLIGHT


def test_mock_hands_over_to_the_upper_stage():
    before, after = mock_telemetry(140, 143.0), mock_telemetry(160, 143.0)
    assert before.engines_total == 33
    assert after.engines_total == 6 and after.engines_on == 6
    assert after.fuel_fraction > 0.9  # fresh tanks
    assert mock_telemetry(160).engines_total == 33  # no marker, no staging


def test_fade_runs_from_zero_to_one():
    from ground_station.layout import ARRANGEMENT_FADE, fade_progress

    assert fade_progress(10.0, 10.0) == 0.0
    assert fade_progress(10.0 + ARRANGEMENT_FADE / 2, 10.0) == pytest.approx(0.5)
    assert fade_progress(99.0, 10.0) == 1.0
    assert fade_progress(5.0, 10.0) == 0.0  # a clock that stepped back


def test_booster_memory_returns_what_it_showed_just_before_the_separation():
    from ground_station.layout import BoosterMemory

    memory = BoosterMemory()
    for t, reading in [(100.0, "five lit"), (105.0, "five lit"), (105.9, "three lit"), (106.0, "ship"), (106.2, "ship")]:
        memory.record(t, reading)
    assert memory.before(106.0) == "three lit"  # the ship's own readings do not replace it
    assert BoosterMemory().before(106.0) is None


def test_booster_memory_forgets_an_old_flight_when_time_runs_back():
    from ground_station.layout import BoosterMemory

    memory = BoosterMemory()
    memory.record(100.0, "old")
    memory.record(-30.0, "new")
    assert memory.before(500.0) == "new"
