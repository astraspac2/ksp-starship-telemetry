import pytest

from ground_station.events import (
    Event,
    event_status,
    events_from_dicts,
    events_to_dicts,
    format_clock_text,
    next_event_index,
    parse_clock,
    sorted_events,
)


@pytest.mark.parametrize(
    "text, seconds",
    [
        ("T-00:00:30", -30.0),
        ("t+00:01:50", 110.0),
        ("T-10:00", -600.0),
        ("T+1:05", 65.0),
        ("-30", -30.0),
        ("+0", 0.0),
        ("T-01:00:00", -3600.0),
    ],
)
def test_parse_clock(text, seconds):
    assert parse_clock(text) == seconds


@pytest.mark.parametrize("text", ["", "30", "T 30", "T-00:61", "T-00:00:75", "T-abc", "T--5"])
def test_parse_clock_rejects_bad_text(text):
    assert parse_clock(text) is None


@pytest.mark.parametrize("t", [-3600.0, -30.0, 0.0, 110.0, 3725.0])
def test_format_and_parse_round_trip(t):
    assert parse_clock(format_clock_text(t)) == t


def test_format_clock_text():
    assert format_clock_text(-30.0) == "T-00:00:30"
    assert format_clock_text(110.0) == "T+00:01:50"


EVENTS = [Event(-60.0, "Final countdown"), Event(0.0, "Liftoff"), Event(70.0, "Max Q", enabled=False), Event(143.0, "Stage Sep")]


def test_next_event_skips_disabled_and_past_events():
    assert next_event_index(EVENTS, -100.0) == 0
    assert next_event_index(EVENTS, -30.0) == 1
    assert next_event_index(EVENTS, 10.0) == 3  # Max Q is disabled
    assert next_event_index(EVENTS, 200.0) is None


def test_event_status_text():
    assert event_status(EVENTS, 0, -100.0) == "NEXT in 40s"
    assert event_status(EVENTS, 1, -100.0) == "upcoming"
    assert event_status(EVENTS, 0, -30.0) == "done"
    assert event_status(EVENTS, 2, 0.0) == "disabled"


def test_sorting_orders_by_time():
    shuffled = [Event(10.0, "b"), Event(-5.0, "a"), Event(3.0, "c")]
    assert [e.label for e in sorted_events(shuffled)] == ["a", "c", "b"]


def test_saved_rows_round_trip_and_bad_rows_are_dropped():
    assert events_from_dicts(events_to_dicts(EVENTS)) == EVENTS
    rows = [{"time": 5, "label": "ok"}, {"time": "x", "label": "bad time"}, {"label": "no time"}, {"time": 1, "label": " "}, 7]
    assert [e.label for e in events_from_dicts(rows)] == ["ok"]
    assert events_from_dicts("not a list") == []
