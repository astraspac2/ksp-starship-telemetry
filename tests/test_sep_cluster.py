import pytest

from ground_station.sep_cluster import (
    CLUSTER_ENGINES,
    GROUPS,
    cluster_thrust_n,
    engines_burning,
    is_producing,
    lit_for_mode,
    lit_groups,
    lit_pattern,
    parse_thrust_kn,
    per_engine_rated_n,
)

# Recorded on the pad during the static fire: the switch showed 18903.29 kN total while kRPC
# read 11456537 N from the 20-engine first group.
STATIC_FIRE_TOTAL_KN = 18903.29
STATIC_FIRE_FIRST_N = 11456537.0


def test_groups_cover_every_engine_once():
    positions = [p for group in GROUPS.values() for p in group]
    assert sorted(positions) == list(range(CLUSTER_ENGINES))


def test_static_fire_reads_as_all_33():
    engines = engines_burning(STATIC_FIRE_TOTAL_KN, STATIC_FIRE_FIRST_N, 20, 11464202.0, 1.0)
    assert engines == pytest.approx(33, abs=0.01)
    assert lit_pattern(lit_groups(engines)) == (True,) * 33


def test_boostback_without_the_outer_ring_uses_rated_thrust_and_throttle():
    per_engine_n = 11464202.0 / 20
    total_kn = 13 * per_engine_n * 0.6 / 1000  # 13 engines at 60 % throttle, outer group off
    engines = engines_burning(total_kn, 0.0, 20, 11464202.0, 0.6)
    assert set(lit_groups(engines)) == {"Center Three", "Middle Two", "Middle Eight"}


def test_landing_burn_is_the_centre_three():
    pattern = lit_pattern(lit_groups(3.2))
    assert pattern[:3] == (True, True, True) and sum(pattern) == 3


@pytest.mark.parametrize("mode, count", [("Outer Twenty", 33), ("Middle Eight", 13), ("Middle Two", 5), ("Center Three", 3)])
def test_each_mode_lights_its_ring_and_everything_inside_it(mode, count):
    assert sum(lit_for_mode(mode, True)) == count


def test_a_cluster_that_is_not_burning_lights_nothing_and_an_unknown_mode_is_not_guessed():
    assert sum(lit_for_mode("Middle Eight", False)) == 0
    assert lit_for_mode("Mystery", True) is None
    assert sum(lit_for_mode(" Center Three ", True)) == 3  # stray spaces in the field do not matter


@pytest.mark.parametrize(
    "field_kn, module_n, fuel_flow, expected",
    [
        (18903.0, 0.0, 0.0, True),  # the switch's Thrust field is showing
        (0.0, 11456537.0, 0.0, True),  # the part window is closed (field stuck at 0) but the engine module has thrust
        (0.0, 0.0, 1250.0, True),  # both read nothing but the tanks are emptying
        (0.0, 0.0, 0.0, False),  # sitting on the pad
        (0.0, 0.0, 2.0, False),  # a trickle (slosh or a leak) is not a burn
    ],
)
def test_is_producing_uses_any_of_three_signs(field_kn, module_n, fuel_flow, expected):
    assert is_producing(field_kn, module_n, fuel_flow) is expected


def test_no_thrust_means_nothing_lit():
    assert engines_burning(0.0, 0.0, 20, 11464202.0, 1.0) == 0.0
    assert sum(lit_pattern(lit_groups(0.0))) == 0


@pytest.mark.parametrize("field, expected", [("18903.29", 18903.29), ("0", 0.0), ("", 0.0), ("1,234.5 kN", 1234.5)])
def test_parse_thrust_kn(field, expected):
    assert parse_thrust_kn(field) == pytest.approx(expected)


# Thrust of the cluster (recorded static fire: 20 engines read 11,456,537 N, the part window said 18903.29 kN for all 33).
def test_a_rated_engine_comes_from_the_first_group_and_is_remembered_when_it_goes_blank():
    assert per_engine_rated_n(11464202.0, 20, None) == pytest.approx(573210.1)
    assert per_engine_rated_n(0.0, 20, 573210.1) == pytest.approx(573210.1)  # the outer engines are off: keep what was seen
    assert per_engine_rated_n(0.0, 20, None) is None


@pytest.mark.parametrize(
    "lit, producing, first_n, first_engines, switch_kn, rated_each, throttle, expected",
    [
        (33, True, 11456537.0, 20, 0.0, None, 1.0, 18903286.0),  # the first group's thrust per engine, times all 33
        (33, True, 11456537.0, 20, 18903.29, 573210.1, 1.0, 18903286.0),  # trusted over the part window: it needs nothing else
        (13, True, 0.0, 20, 7421.5, None, 1.0, 7421500.0),  # outer engines off: the part window's total
        (13, True, 0.0, 20, 0.0, 573210.1, 0.5, 13 * 573210.1 * 0.5),  # nothing else: the rating times the throttle, an estimate
        (13, True, 0.0, 20, 0.0, None, 1.0, None),  # burning but no way to know how hard
        (0, False, 0.0, 20, 0.0, 573210.1, 1.0, 0.0),  # not burning
        (33, False, 0.0, 20, 0.0, None, 0.0, 0.0),
    ],
)
def test_cluster_thrust(lit, producing, first_n, first_engines, switch_kn, rated_each, throttle, expected):
    result = cluster_thrust_n(lit, producing, first_n, first_engines, switch_kn, rated_each, throttle)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected, rel=1e-6)


def test_the_estimate_from_the_first_group_matches_the_recorded_part_window_total():
    thrust = cluster_thrust_n(33, True, 11456537.0, 20, 0.0, None, 1.0)
    assert thrust / 1000.0 == pytest.approx(18903.29, rel=1e-4)
