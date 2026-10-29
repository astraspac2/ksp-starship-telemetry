from types import SimpleNamespace

from ground_station.booster import (
    FIND_SECONDS,
    LOST_AFTER_SECONDS,
    NO_DATA_SECONDS,
    PARTS_EVERY_SECONDS,
    READ_EVERY_SECONDS,
    BoosterTracker,
)
from ground_station.layout import Layout, layout_for


class FakeFlight:
    def __init__(self, vessel):
        self._vessel = vessel

    def _read(self, value):
        self._vessel.calls += 1
        if self._vessel.fail:
            raise RuntimeError("gone")
        return value

    @property
    def speed(self):
        return self._read(self._vessel.speed)

    @property
    def surface_altitude(self):
        return self._read(self._vessel.altitude)

    @property
    def mean_altitude(self):
        return self._read(self._vessel.sea)


class FakeVessel:
    def __init__(self, distance, speed=800.0, altitude=60_000.0, sea=60_500.0):
        self.distance, self.speed, self.altitude, self.sea, self.fail = distance, speed, altitude, sea, False
        self.unloaded, self.calls, self.parts_calls = False, 0, 0
        self.reference_frame = "frame"
        self.orbit = SimpleNamespace(body=SimpleNamespace(reference_frame="body"))
        self.situation = SimpleNamespace(name="flying")

    def position(self, frame):
        return (self.distance, 0.0, 0.0)

    def flight(self, frame=None):
        return FakeFlight(self)

    @property
    def parts(self):
        self.parts_calls += 1
        return SimpleNamespace(all=[] if self.unloaded else [0] * 10)


class FakeConn:
    """add_stream hands back a callable that reads the attribute when it is called, as a kRPC stream's latest value does."""

    def __init__(self):
        self.streams = []

    def add_stream(self, fn, obj, attr):
        stream = lambda: fn(obj, attr)  # noqa: E731
        stream.remove = lambda: self.streams.remove(stream)
        self.streams.append(stream)
        return stream


def centre_with(ship, *others):
    return SimpleNamespace(active_vessel=ship, vessels=[ship, *others])


def separated(tracker, centre, now=0.0, conn=None):
    tracker.update(now, centre, True, "surface", conn)  # the stack, with the booster's cluster
    return tracker.update(now + 1.0, centre, False, "surface", conn)  # now the ship alone


def test_the_booster_is_found_after_the_separation_and_read():
    ship, booster, far = FakeVessel(0.0), FakeVessel(150.0), FakeVessel(900_000.0)
    reading = separated(BoosterTracker(), centre_with(ship, far, booster))
    assert reading.live and (reading.speed_ms, reading.altitude_m) == (800.0, 60_000.0)


def test_nothing_is_looked_for_when_the_app_starts_after_the_separation():
    tracker = BoosterTracker()
    centre = centre_with(FakeVessel(0.0), FakeVessel(150.0))
    assert not tracker.update(0.0, centre, False).live  # never saw the stack: it cannot say which vessel is the booster


def test_a_vessel_further_than_5_km_is_not_taken_for_the_booster():
    assert not separated(BoosterTracker(), centre_with(FakeVessel(0.0), FakeVessel(8000.0))).live


def test_the_booster_is_only_looked_for_for_a_minute():
    tracker = BoosterTracker()
    ship = FakeVessel(0.0)
    centre = centre_with(ship)
    separated(tracker, centre)
    centre.vessels.append(FakeVessel(100.0))
    assert not tracker.update(1.0 + FIND_SECONDS + 5.0, centre, False).live


def test_sea_level_altitude_when_that_is_the_setting():
    tracker = BoosterTracker()
    centre = centre_with(FakeVessel(0.0), FakeVessel(100.0))
    tracker.update(0.0, centre, True)
    assert tracker.update(1.0, centre, False, "sea").altitude_m == 60_500.0


def test_without_a_stream_readings_are_taken_a_few_times_a_second_not_on_every_call():
    ship, booster = FakeVessel(0.0), FakeVessel(100.0)
    tracker = BoosterTracker()
    centre = centre_with(ship, booster)
    separated(tracker, centre)
    booster.speed = 500.0
    assert tracker.update(1.0 + READ_EVERY_SECONDS / 2, centre, False).speed_ms == 800.0
    assert tracker.update(1.0 + READ_EVERY_SECONDS * 1.1, centre, False).speed_ms == 500.0


def test_with_streams_every_call_picks_up_the_newest_value_without_asking_the_game():
    ship, booster, conn = FakeVessel(0.0), FakeVessel(100.0), FakeConn()
    tracker = BoosterTracker()
    centre = centre_with(ship, booster)
    separated(tracker, centre, conn=conn)
    assert len(conn.streams) == 2  # speed and altitude
    booster.speed = 700.0
    assert tracker.update(1.01, centre, False, "surface", conn).speed_ms == 700.0  # 10 ms later: already the new value
    booster.speed = 650.0
    assert tracker.update(1.02, centre, False, "surface", conn).speed_ms == 650.0
    asked = booster.parts_calls
    for step in range(30):  # a second and a half of readings at 20 a second
        tracker.update(1.05 + step * 0.05, centre, False, "surface", conn)
    assert booster.parts_calls - asked <= 2  # the parts are only looked at about once a second


def test_the_streams_follow_the_altitude_setting_and_are_dropped_when_the_booster_is_done():
    ship, booster, conn = FakeVessel(0.0), FakeVessel(100.0), FakeConn()
    tracker = BoosterTracker()
    centre = centre_with(ship, booster)
    separated(tracker, centre, conn=conn)
    assert tracker.update(2.0, centre, False, "sea", conn).altitude_m == 60_500.0
    assert len(conn.streams) == 2  # the old pair was replaced, not added to
    booster.unloaded = True
    tracker.update(3.0 + PARTS_EVERY_SECONDS, centre, False, "surface", conn)
    tracker.update(4.0 + NO_DATA_SECONDS + PARTS_EVERY_SECONDS, centre, False, "surface", conn)
    assert conn.streams == []


def test_an_unloaded_booster_says_no_data_for_a_while_and_then_the_gauges_come_off():
    ship, booster = FakeVessel(0.0), FakeVessel(100.0)
    tracker = BoosterTracker()
    centre = centre_with(ship, booster)
    separated(tracker, centre)
    booster.unloaded = True  # KSP stops simulating it: no parts, though speed and altitude still read
    start = 2.0 + PARTS_EVERY_SECONDS
    reading = tracker.update(start, centre, False)
    assert reading.live and reading.speed_ms is None and reading.altitude_m is None  # the gauges show NO DATA
    assert tracker.update(start + NO_DATA_SECONDS - 1.0, centre, False).live
    assert not tracker.update(start + NO_DATA_SECONDS + 0.5, centre, False).live
    booster.unloaded = False
    assert not tracker.update(start + NO_DATA_SECONDS + 5.0, centre, False).live  # and it does not come back


def test_the_booster_is_lost_when_the_game_stops_reporting_it():
    ship, booster = FakeVessel(0.0), FakeVessel(100.0)
    tracker = BoosterTracker()
    centre = centre_with(ship, booster)
    separated(tracker, centre)
    booster.fail = True
    assert tracker.update(2.0, centre, False).speed_ms == 800.0  # one failed reading is not the end: the last good one stays
    reading = tracker.update(2.0 + LOST_AFTER_SECONDS + 0.5, centre, False)
    assert reading.live and reading.speed_ms is None  # NO DATA first
    assert not tracker.update(2.0 + LOST_AFTER_SECONDS + NO_DATA_SECONDS + 1.0, centre, False).live
    booster.fail = False
    assert not tracker.update(60.0, centre, False).live


def test_a_stack_again_clears_what_was_followed():
    tracker = BoosterTracker()
    centre = centre_with(FakeVessel(0.0), FakeVessel(100.0))
    separated(tracker, centre)
    assert not tracker.update(5.0, centre, True).live


def test_the_split_arrangement_replaces_flight_only_while_the_booster_is_read():
    assert layout_for(300.0, 143.0, 143.0, True) is Layout.SPLIT
    assert layout_for(300.0, 143.0, 143.0, False) is Layout.FLIGHT
    assert layout_for(145.0, 143.0, 143.0, True) is Layout.STAGE_SEP  # the separation itself is unchanged
    assert layout_for(100.0, 143.0, None, True) is Layout.STAGE_1


def test_when_the_booster_is_lost_a_record_of_its_last_moments_is_written(tmp_path):
    ship, booster = FakeVessel(0.0), FakeVessel(100.0, speed=1269.0, altitude=26_100.0)
    log = tmp_path / "booster-loss.csv"
    tracker = BoosterTracker(log)
    centre = centre_with(ship, booster)
    separated(tracker, centre)
    booster.fail = True
    tracker.update(2.0, centre, False)
    assert not log.exists()  # it is only written once the booster is really lost
    tracker.update(2.0 + LOST_AFTER_SECONDS + 0.5, centre, False)
    text = log.read_text(encoding="utf-8")
    assert "1269.0,26100.0" in text  # the last good reading
    assert "RuntimeError: gone" in text  # what the game said
    assert "still in the game's vessel list: yes" in text  # and whether the game still has it


def test_no_record_is_written_without_a_path_and_a_bad_path_does_not_stop_anything(tmp_path):
    booster = FakeVessel(100.0)
    for tracker in (BoosterTracker(), BoosterTracker(tmp_path / "missing-folder" / "x.csv")):
        centre = centre_with(FakeVessel(0.0), booster)
        separated(tracker, centre)
        booster.fail = True
        tracker.update(2.0, centre, False)
        tracker.update(2.0 + LOST_AFTER_SECONDS + 0.5, centre, False)
        assert not tracker.update(60.0, centre, False).live
        booster.fail = False
