import math

import pytest

from ground_station.auto_markers import (
    LANDING,
    NODE,
    NODE_STABLE_SECONDS,
    REENTRY,
    AutoMarker,
    AutoMarkerTracker,
    auto_markers_from_dicts,
    auto_markers_to_dicts,
    seconds_to_reach,
)


def node_tick(tracker, wall, t=720.0, ut=1000.0, nodes=()):
    tracker.update(wall, t, ut, nodes, 10.0, None)


def test_a_new_node_is_asked_about_only_once_it_has_stayed_put():
    tracker = AutoMarkerTracker([])
    node_tick(tracker, 0.0, nodes=(1600.0,))
    node_tick(tracker, NODE_STABLE_SECONDS - 0.5, nodes=(1600.0,))
    assert tracker.pending is None
    node_tick(tracker, NODE_STABLE_SECONDS + 0.1, nodes=(1600.0,))
    assert tracker.pending is not None
    assert tracker.pending.ahead == pytest.approx(600.0)
    assert tracker.pending.time == pytest.approx(1320.0)  # T+00:12:00 plus ten minutes: T+00:22:00


def test_a_node_being_dragged_is_not_asked_about_until_it_stops():
    tracker = AutoMarkerTracker([])
    for step in range(10):
        node_tick(tracker, step * 0.5, nodes=(1600.0 + step * 20,))
    assert tracker.pending is None
    for step in range(10, 16):
        node_tick(tracker, step * 0.5, nodes=(1780.0,))
    assert tracker.pending is not None


def test_naming_the_node_puts_it_on_the_timeline():
    markers = []
    tracker = AutoMarkerTracker(markers)
    for wall in (0.0, 3.0):
        node_tick(tracker, wall, nodes=(1600.0,))
    marker = tracker.accept("  Circularize ")
    assert marker == AutoMarker("Circularize", 1320.0, NODE)
    assert markers == [marker] and tracker.pending is None and tracker.take_changed()
    node_tick(tracker, 10.0, nodes=(1600.0,))
    assert tracker.pending is None  # already named


def test_a_blank_name_adds_nothing():
    markers = []
    tracker = AutoMarkerTracker(markers)
    for wall in (0.0, 3.0):
        node_tick(tracker, wall, nodes=(1600.0,))
    assert tracker.accept("   ") is None and markers == []


def test_a_declined_node_is_not_asked_about_again_even_when_moved():
    tracker = AutoMarkerTracker([])
    for wall in (0.0, 3.0):
        node_tick(tracker, wall, nodes=(1600.0,))
    tracker.decline()
    node_tick(tracker, 6.0, nodes=(1600.0,))
    node_tick(tracker, 9.0, nodes=(1650.0,))
    node_tick(tracker, 12.0, nodes=(1650.0,))
    assert tracker.pending is None


def test_the_marker_follows_the_node_while_it_is_dragged():
    markers = [AutoMarker("Burn", 1320.0, NODE, node_ut=1600.0)]
    tracker = AutoMarkerTracker(markers)
    node_tick(tracker, 0.0, nodes=(1700.0,))
    assert markers[0].time == pytest.approx(1420.0) and markers[0].node_ut == 1700.0 and tracker.take_changed()


def test_when_the_node_is_gone_the_marker_stays_where_it_was():
    markers = [AutoMarker("Burn", 1320.0, NODE, node_ut=1600.0)]
    tracker = AutoMarkerTracker(markers)
    node_tick(tracker, 0.0, nodes=())
    node_tick(tracker, 1.0, nodes=(5000.0,))  # a different node later is not this marker's
    assert markers[0].time == 1320.0 and markers[0].node_ut is None


def test_a_node_in_the_past_is_ignored():
    tracker = AutoMarkerTracker([])
    for wall in (0.0, 3.0):
        node_tick(tracker, wall, nodes=(900.0,))
    assert tracker.pending is None


def orbit_tick(tracker, t, ut, altitude, reentry_ut=None):
    tracker.update(float(t), t, ut, (), altitude, reentry_ut)


def reentries(markers):
    return [m for m in markers if m.kind == REENTRY]


def test_reentry_needs_the_vessel_to_have_been_above_70_km_first():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 100, 1000.0, 69.0, reentry_ut=1300.0)  # a low hop: never above 70 km
    orbit_tick(tracker, 101, 1001.0, 68.0)
    orbit_tick(tracker, 102, 1002.0, 60.0)
    assert reentries(markers) == []


def test_the_threshold_is_70_km():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 1, 1001.0, 71.0)
    orbit_tick(tracker, 2, 1002.0, 71.0, reentry_ut=1100.0)
    assert len(reentries(markers)) == 1


def test_a_suborbital_flight_above_70_km_gets_a_reentry_marker():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 100, 1000.0, 60.0)
    orbit_tick(tracker, 200, 1100.0, 120.0)  # went above 70 km, no orbit at all
    orbit_tick(tracker, 300, 1200.0, 95.0)
    orbit_tick(tracker, 310, 1210.0, 69.0)
    assert [m.time for m in reentries(markers)] == [310.0]


def test_reentry_is_predicted_after_a_deorbit_burn_and_set_when_70_km_is_crossed():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 5000, 8000.0, 155.0)  # in orbit
    orbit_tick(tracker, 5100, 8100.0, 155.0, reentry_ut=8900.0)  # after the deorbit burn
    assert reentries(markers) == [AutoMarker("Re-entry", 5900.0, REENTRY)]
    orbit_tick(tracker, 5110, 8110.0, 150.0, reentry_ut=8900.0)
    assert reentries(markers)[0].time == 5900.0  # same prediction, no jitter
    for t, alt in ((5880, 80.0), (5890, 72.0), (5901, 69.0)):
        orbit_tick(tracker, t, 8000.0 + t - 5000, alt)
    assert len(reentries(markers)) == 1 and reentries(markers)[0].time == 5901.0  # the real crossing
    orbit_tick(tracker, 5950, 8950.0, 60.0)
    assert reentries(markers)[0].time == 5901.0


def test_reentry_without_a_prediction_is_still_marked_when_70_km_is_crossed():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 5000, 8000.0, 155.0)
    orbit_tick(tracker, 6000, 9000.0, 80.0)
    orbit_tick(tracker, 6010, 9010.0, 69.0)
    assert [m.time for m in reentries(markers)] == [6010.0]


def test_the_marker_is_not_made_again_after_the_crossing_when_the_operator_deletes_it():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 1, 1001.0, 120.0)
    orbit_tick(tracker, 2, 1002.0, 90.0)
    orbit_tick(tracker, 3, 1003.0, 69.0)
    assert len(reentries(markers)) == 1
    markers.clear()  # the operator deletes it
    orbit_tick(tracker, 4, 1004.0, 60.0, reentry_ut=1100.0)
    orbit_tick(tracker, 5, 1005.0, 40.0)
    assert reentries(markers) == []


def test_a_second_flight_gets_its_own_reentry_after_dropping_below_70_km():
    markers = []
    tracker = AutoMarkerTracker(markers)
    for t, alt in ((1, 120.0), (2, 90.0), (3, 69.0), (4, 60.0), (5, 100.0), (6, 90.0), (7, 69.0)):
        orbit_tick(tracker, t, 1000.0 + t, alt)
    assert len(reentries(markers)) == 1 and reentries(markers)[0].time == 7.0  # the old marker is reused and moved


def test_a_low_hop_after_a_finished_reentry_is_not_marked():
    markers = []
    tracker = AutoMarkerTracker(markers)
    for t, alt in ((1, 120.0), (2, 90.0), (3, 69.0), (4, 68.0), (5, 60.0)):  # re-entry done, back low
        orbit_tick(tracker, t, 1000.0 + t, alt)
    orbit_tick(tracker, 6, 1006.0, 50.0, reentry_ut=1100.0)  # the next hop never gets above 70 km
    assert [m.time for m in reentries(markers)] == [3.0]  # still the first flight's crossing, not moved to the new prediction


def test_a_deleted_reentry_marker_stays_deleted():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 5000, 8000.0, 155.0)
    orbit_tick(tracker, 5100, 8100.0, 155.0, reentry_ut=8900.0)
    markers.clear()
    orbit_tick(tracker, 5101, 8101.0, 154.0, reentry_ut=8899.0)
    assert reentries(markers) == []


def test_a_new_flight_reuses_the_old_reentry_marker():
    markers = [AutoMarker("Re-entry", 100.0, REENTRY)]
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 5000, 8000.0, 155.0)
    orbit_tick(tracker, 5100, 8100.0, 155.0, reentry_ut=8900.0)
    assert len(reentries(markers)) == 1 and reentries(markers)[0].time == 5900.0


def test_a_missing_or_unknown_altitude_does_nothing():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 1, 1001.0, float("nan"))
    orbit_tick(tracker, 2, 1002.0, None, reentry_ut=1100.0)
    assert markers == []


def test_markers_round_trip_through_the_settings_and_bad_rows_are_skipped():
    markers = [AutoMarker("Burn", 1320.0, NODE, enabled=False), AutoMarker("Re-entry", 5800.0, REENTRY)]
    rows = auto_markers_to_dicts(markers) + [{"name": "", "time": 1, "kind": NODE}, {"name": "x", "time": "nan", "kind": NODE}, {"name": "y", "time": 1, "kind": "other"}, 5]
    assert auto_markers_from_dicts(rows) == markers
    assert auto_markers_from_dicts("nonsense") == []


def landing_markers(markers):
    return [m for m in markers if m.kind == LANDING]


def sink(tracker, readings, t0=1000.0):
    """Feed (seconds, kilometres) readings; flight clock and game time both advance with the seconds."""
    for seconds, km in readings:
        tracker.update(float(seconds), t0 + seconds, 5000.0 + seconds, (), km, None)


def test_landing_burn_is_marked_when_800_m_is_crossed_on_the_way_down():
    markers = []
    tracker = AutoMarkerTracker(markers)
    sink(tracker, [(0, 0.1), (60, 75.0), (120, 90.0), (200, 20.0), (260, 3.0), (270, 1.0), (272, 0.79)])
    assert [(m.name, m.time) for m in landing_markers(markers)] == [("Landing burn", 1272.0)]


def fall(h0, speed, k, until, step=0.5, gravity=9.81, scale=5600.0):
    """A vessel sinking from `h0` metres at `speed` m/s with drag k * density * speed^2, worked out in tiny steps.

    Returns the readings (seconds, kilometres) every `step` seconds until `until`, and the second it reaches 800 m."""
    readings, arrival = [], None
    h, v, t, next_reading, dt = h0, speed, 0.0, 0.0, 0.005
    while t <= until or arrival is None:
        if t >= next_reading and t <= until:
            readings.append((round(t, 3), h / 1000.0))
            next_reading += step
        h -= v * dt
        v += (gravity - k * math.exp(-h / scale) * v * v) * dt
        t += dt
        if arrival is None and h <= 800.0:
            arrival = t
        if t > 2000.0:
            break
    return readings, arrival



def test_landing_burn_is_placed_as_soon_as_the_vessel_is_falling_and_set_at_the_real_crossing():
    markers = []
    tracker = AutoMarkerTracker(markers)
    readings, arrival = fall(100_000.0, 300.0, 0.0, 10.0)  # no air at all: a plain fall
    sink(tracker, [(0, 100.0)] + readings[1:])
    (marker,) = landing_markers(markers)
    assert marker.time == pytest.approx(1000.0 + arrival, abs=0.5)
    sink(tracker, [(int(arrival) + 5, 1.0), (int(arrival) + 6, 0.7)])
    assert [m.time for m in landing_markers(markers)] == [1000.0 + int(arrival) + 6]  # the real crossing


def test_the_prediction_works_out_how_thickening_air_slows_the_vessel():
    k = 3e-3  # slows to about 57 m/s near the ground
    readings, arrival = fall(50_000.0, 1500.0, k, 80.0)
    window = [(t, km * 1000.0) for t, km in readings if 60.0 <= t <= 70.0]
    now = window[-1][0]
    assert seconds_to_reach(window, 800.0) == pytest.approx(arrival - now, rel=0.06)
    straight_on = (window[-1][1] - 800.0) / ((window[0][1] - window[-1][1]) / (window[-1][0] - window[0][0]))
    assert abs(straight_on - (arrival - now)) > 2 * abs(seconds_to_reach(window, 800.0) - (arrival - now))  # better than constant speed


def test_a_plain_fall_with_no_air_is_predicted_exactly():
    readings, arrival = fall(30_000.0, 100.0, 0.0, 8.0)
    window = [(t, km * 1000.0) for t, km in readings]
    assert seconds_to_reach(window, 800.0) == pytest.approx(arrival - window[-1][0], abs=0.1)


def test_no_prediction_without_enough_readings_or_when_not_sinking():
    assert seconds_to_reach([(0.0, 5000.0), (1.0, 4000.0)], 800.0) is None
    assert seconds_to_reach([(0.0, 5000.0), (1.0, 5000.0), (2.0, 5000.0)], 800.0) is None
    assert seconds_to_reach([(0.0, 5000.0), (1.0, 5500.0), (2.0, 6000.0)], 800.0) is None


def test_a_vessel_that_would_stop_above_the_target_does_not_give_nonsense():
    readings, _ = fall(20_000.0, 1000.0, 5e-2, 6.0)  # braked to a near stop
    seconds = seconds_to_reach([(t, km * 1000.0) for t, km in readings], 800.0)
    assert seconds is None or seconds > 0


def test_a_launch_through_800_m_is_not_a_landing_burn():
    markers = []
    tracker = AutoMarkerTracker(markers)
    sink(tracker, [(0, 0.0), (10, 0.5), (20, 0.9), (30, 3.0), (60, 9.0)])
    assert landing_markers(markers) == []


def test_a_hop_that_never_got_above_70_km_is_not_marked():
    markers = []
    tracker = AutoMarkerTracker(markers)
    sink(tracker, [(0, 0.0), (20, 30.0), (40, 69.0), (60, 4.0), (80, 1.0), (85, 0.7)])
    assert landing_markers(markers) == []


def test_the_landing_marker_is_not_made_again_after_the_crossing():
    markers = []
    tracker = AutoMarkerTracker(markers)
    sink(tracker, [(0, 80.0), (50, 5.0), (60, 0.7)])
    sink(tracker, [(70, 0.5), (80, 0.3), (90, 0.4), (100, 0.2)])
    assert [m.time for m in landing_markers(markers)] == [1060.0]


def test_a_deleted_landing_marker_stays_deleted_for_that_flight():
    markers = []
    tracker = AutoMarkerTracker(markers)
    sink(tracker, [(0, 80.0), (50, 9.0), (52, 8.0), (54, 7.0)])
    assert len(landing_markers(markers)) == 1
    markers.clear()
    sink(tracker, [(56, 6.0), (58, 5.0), (60, 4.0), (70, 0.7)])
    assert landing_markers(markers) == []


def test_a_new_flight_reuses_the_old_landing_marker():
    markers = [AutoMarker("Landing burn", 100.0, LANDING)]
    tracker = AutoMarkerTracker(markers)
    sink(tracker, [(0, 80.0), (50, 5.0), (60, 0.7)])
    assert [m.time for m in landing_markers(markers)] == [1060.0] and markers[0].kind == LANDING


def test_the_landing_marker_round_trips_through_the_settings():
    markers = [AutoMarker("Landing burn", 1060.0, LANDING)]
    assert auto_markers_from_dicts(auto_markers_to_dicts(markers)) == markers


def test_no_landing_marker_from_less_than_two_seconds_of_falling():
    markers = []
    tracker = AutoMarkerTracker(markers)
    sink(tracker, [(0, 100.0)] + fall(100_000.0, 300.0, 0.0, 1.5)[0][1:])
    assert landing_markers(markers) == []


def orbit_landing_tick(tracker, t, altitude, landing_ut=None):
    tracker.update(float(t), t, 5000.0 + t, (), altitude, None, landing_ut)


def test_landing_burn_marker_is_there_from_the_first_time_the_vessel_is_above_70_km():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_landing_tick(tracker, 100, 60.0, landing_ut=5600.0)  # not above 70 km yet: nothing
    assert landing_markers(markers) == []
    orbit_landing_tick(tracker, 110, 71.0, landing_ut=5600.0)  # first time above 70 km: the orbit says when 800 m comes
    assert [m.time for m in landing_markers(markers)] == [110.0 + (5600.0 - 5110.0)]
    orbit_landing_tick(tracker, 120, 90.0, landing_ut=5590.0)  # and it follows the orbit, smoothly
    (marker,) = landing_markers(markers)
    assert marker.time == pytest.approx(590.8, abs=0.05)  # eased from 600 toward the new 590, not jumping straight there


def test_without_an_orbit_prediction_there_is_no_landing_marker_yet():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_landing_tick(tracker, 110, 150.0)
    orbit_landing_tick(tracker, 120, 151.0)
    assert landing_markers(markers) == []


def test_in_the_air_the_speed_and_braking_replace_the_orbit_prediction():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_landing_tick(tracker, -60, 100.0)  # armed, well before the readings below
    readings, arrival = fall(50_000.0, 1500.0, 3e-3, 70.0)
    for seconds, km in readings:
        orbit = 9999.0 if seconds > 2.5 else None  # once the air is measured, a far-off orbit is ignored
        tracker.update(1.0 + seconds, 1.0 + seconds, 5001.0 + seconds, (), km, None, orbit)
    (marker,) = landing_markers(markers)
    assert marker.time == pytest.approx(1.0 + arrival, rel=0.05)


def test_a_game_that_repeats_each_reading_still_gives_a_prediction():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_landing_tick(tracker, -30, 100.0)
    readings, arrival = fall(30_000.0, 200.0, 0.0, 8.0, step=1.0)
    for seconds, km in readings:
        for _ in range(4):  # the same reading arrives several times
            tracker.update(1.0 + seconds, 1.0 + seconds, 5001.0 + seconds, (), km, None)
    (marker,) = landing_markers(markers)
    assert marker.time == pytest.approx(1.0 + arrival, abs=0.3)


def test_one_noisy_reading_barely_moves_the_landing_marker():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_landing_tick(tracker, -30, 100.0)
    readings, _ = fall(30_000.0, 200.0, 0.0, 12.0)
    for index, (seconds, km) in enumerate(readings):
        km += 0.05 if index == 18 else 0.0  # one reading 50 m high
        tracker.update(1.0 + seconds, 1.0 + seconds, 5001.0 + seconds, (), km, None)
        if index == 14:
            (before,) = [m.time for m in landing_markers(markers)]
    (after,) = [m.time for m in landing_markers(markers)]
    assert after == pytest.approx(before, abs=1.0)

def test_a_fall_on_a_small_world_is_predicted_with_its_gravity():
    readings, arrival = fall(30_000.0, 100.0, 0.0, 8.0, gravity=1.63)  # a small world
    window = [(t, km * 1000.0) for t, km in readings]
    assert seconds_to_reach(window, 800.0, gravity=1.63) == pytest.approx(arrival - window[-1][0], abs=0.2)
