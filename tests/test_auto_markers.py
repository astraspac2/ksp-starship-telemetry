import pytest

from ground_station.auto_markers import (
    NODE,
    NODE_STABLE_SECONDS,
    REENTRY,
    AutoMarker,
    AutoMarkerTracker,
    auto_markers_from_dicts,
    auto_markers_to_dicts,
)


def node_tick(tracker, wall, t=720.0, ut=1000.0, nodes=()):
    tracker.update(wall, t, ut, nodes, None, None, 10.0, None)


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


def orbit_tick(tracker, t, ut, apo, peri, altitude, reentry_ut=None):
    tracker.update(float(t), t, ut, (), apo, peri, altitude, reentry_ut)


def test_reentry_needs_an_orbit_above_100_km_first():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 100, 1000.0, 150.0, 90.0, 120.0, reentry_ut=1300.0)  # periapsis only 90 km: not an orbit yet
    orbit_tick(tracker, 101, 1001.0, 150.0, 90.0, 100.0)
    orbit_tick(tracker, 102, 1002.0, 150.0, 90.0, 80.0)
    assert markers == []


def test_reentry_is_predicted_after_a_deorbit_burn_and_set_when_85_km_is_crossed():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 5000, 8000.0, 160.0, 150.0, 155.0)  # in orbit
    orbit_tick(tracker, 5100, 8100.0, 160.0, -30.0, 155.0, reentry_ut=8900.0)  # after the deorbit burn
    assert markers == [AutoMarker("Re-entry", 5900.0, REENTRY)]
    orbit_tick(tracker, 5110, 8110.0, 160.0, -30.0, 150.0, reentry_ut=8900.0)
    assert markers[0].time == 5900.0  # same prediction, no jitter
    for t, alt in ((5880, 90.0), (5890, 86.0), (5901, 84.0)):
        orbit_tick(tracker, t, 8000.0 + t - 5000, 160.0, -30.0, alt)
    assert len(markers) == 1 and markers[0].time == 5901.0  # the real crossing
    orbit_tick(tracker, 5950, 8950.0, 160.0, -30.0, 60.0)
    assert markers[0].time == 5901.0


def test_reentry_without_a_prediction_is_still_marked_when_85_km_is_crossed():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 5000, 8000.0, 160.0, 150.0, 155.0)
    orbit_tick(tracker, 6000, 9000.0, 160.0, -30.0, 90.0)
    orbit_tick(tracker, 6010, 9010.0, 160.0, -30.0, 84.0)
    assert [m.time for m in markers] == [6010.0]


def test_a_deleted_reentry_marker_stays_deleted():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 5000, 8000.0, 160.0, 150.0, 155.0)
    orbit_tick(tracker, 5100, 8100.0, 160.0, -30.0, 155.0, reentry_ut=8900.0)
    markers.clear()
    orbit_tick(tracker, 5101, 8101.0, 160.0, -30.0, 154.0, reentry_ut=8899.0)
    assert markers == []


def test_a_new_orbit_reuses_the_old_reentry_marker():
    markers = [AutoMarker("Re-entry", 100.0, REENTRY)]
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 5000, 8000.0, 160.0, 150.0, 155.0)
    orbit_tick(tracker, 5100, 8100.0, 160.0, -30.0, 155.0, reentry_ut=8900.0)
    assert len(markers) == 1 and markers[0].time == 5900.0


def test_a_hyperbolic_or_missing_orbit_does_nothing():
    markers = []
    tracker = AutoMarkerTracker(markers)
    orbit_tick(tracker, 1, 1001.0, float("nan"), float("nan"), 200.0)
    orbit_tick(tracker, 2, 1002.0, None, None, 90.0)
    assert markers == []


def test_markers_round_trip_through_the_settings_and_bad_rows_are_skipped():
    markers = [AutoMarker("Burn", 1320.0, NODE, enabled=False), AutoMarker("Re-entry", 5800.0, REENTRY)]
    rows = auto_markers_to_dicts(markers) + [{"name": "", "time": 1, "kind": NODE}, {"name": "x", "time": "nan", "kind": NODE}, {"name": "y", "time": 1, "kind": "other"}, 5]
    assert auto_markers_from_dicts(rows) == markers
    assert auto_markers_from_dicts("nonsense") == []
