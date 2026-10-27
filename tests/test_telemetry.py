import pytest

from ground_station.source import DataSource
from ground_station.telemetry import MOCK_BURN_SECONDS, MOCK_FULL_THRUST_N, mock_pad_telemetry


def test_the_mock_static_fire_is_labelled_mock_and_stands_still_on_the_pad():
    for t in (-30.0, 0.0, 5.0, 40.0):
        tel = mock_pad_telemetry(t)
        assert tel.source is DataSource.MOCK
        assert tel.speed_kmh == 0.0 and tel.altitude_km == 0.0 and tel.pitch_deg == 0.0  # upright, not moving


def test_before_ignition_nothing_burns_but_the_gauge_has_its_full_scale():
    tel = mock_pad_telemetry(-10.0)
    assert (tel.engines_on, tel.thrust_n, tel.throttle) == (0, 0.0, 0.0)
    assert tel.max_thrust_n == MOCK_FULL_THRUST_N and tel.fuel_fraction == 1.0


def test_engines_light_one_after_another_and_thrust_builds_up_to_full():
    counts = [mock_pad_telemetry(t).engines_on for t in (0.0, 0.3, 0.6, 1.0, 1.2, 3.0)]
    assert counts == sorted(counts) and counts[0] == 0 and counts[-1] == 33
    thrust = [mock_pad_telemetry(t).thrust_n for t in (0.5, 1.5, 2.5, 5.0)]
    assert thrust == sorted(thrust) and thrust[-1] == pytest.approx(MOCK_FULL_THRUST_N)
    assert mock_pad_telemetry(5.0).throttle == 1.0


def test_shutdown_ends_the_burn_and_the_propellant_stays_spent():
    during = mock_pad_telemetry(MOCK_BURN_SECONDS - 0.1)
    after = mock_pad_telemetry(MOCK_BURN_SECONDS + 5.0)
    assert during.engines_on == 33 and during.throttle == 1.0
    assert (after.engines_on, after.thrust_n, after.throttle) == (0, 0.0, 0.0)
    assert after.fuel_fraction < 1.0 and after.fuel_fraction == pytest.approx(mock_pad_telemetry(MOCK_BURN_SECONDS + 50.0).fuel_fraction)
