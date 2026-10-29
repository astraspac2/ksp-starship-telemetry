from types import SimpleNamespace

from ground_station.booster import FIND_SECONDS, LOST_AFTER_SECONDS, READ_EVERY_SECONDS, BoosterTracker
from ground_station.layout import Layout, layout_for


class FakeVessel:
    def __init__(self, distance, speed=800.0, altitude=60_000.0, sea=60_500.0):
        self.distance, self.speed, self.altitude, self.sea, self.fail = distance, speed, altitude, sea, False
        self.reference_frame = "frame"
        self.orbit = SimpleNamespace(body=SimpleNamespace(reference_frame="body"))

    def position(self, frame):
        return (self.distance, 0.0, 0.0)

    def flight(self, frame=None):
        if self.fail:
            raise RuntimeError("gone")
        return SimpleNamespace(speed=self.speed, surface_altitude=self.altitude, mean_altitude=self.sea)


def centre_with(ship, *others):
    return SimpleNamespace(active_vessel=ship, vessels=[ship, *others])


def separated(tracker, centre, now=0.0):
    tracker.update(now, centre, True)  # the stack, with the booster's cluster
    return tracker.update(now + 1.0, centre, False)  # now the ship alone


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


def test_readings_are_taken_a_few_times_a_second_not_on_every_call():
    ship, booster = FakeVessel(0.0), FakeVessel(100.0)
    tracker = BoosterTracker()
    centre = centre_with(ship, booster)
    separated(tracker, centre)
    booster.speed = 500.0
    assert tracker.update(1.0 + READ_EVERY_SECONDS / 2, centre, False).speed_ms == 800.0
    assert tracker.update(1.0 + READ_EVERY_SECONDS * 1.1, centre, False).speed_ms == 500.0


def test_the_booster_is_lost_for_good_when_the_game_stops_reporting_it():
    ship, booster = FakeVessel(0.0), FakeVessel(100.0)
    tracker = BoosterTracker()
    centre = centre_with(ship, booster)
    separated(tracker, centre)
    booster.fail = True
    assert tracker.update(2.0, centre, False).live  # one failed reading is not the end: the last good one stays
    assert tracker.update(2.0 + LOST_AFTER_SECONDS + 0.5, centre, False) == tracker.reading
    assert not tracker.reading.live and tracker.reading.speed_ms is None
    booster.fail = False
    assert not tracker.update(20.0, centre, False).live  # and it does not come back


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
