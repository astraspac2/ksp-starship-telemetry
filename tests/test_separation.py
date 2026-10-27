from ground_station.separation import CONFIRM_SECONDS, SeparationDetector


class Wall:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def feed(detector, wall, readings):
    """readings: (flight time, engines, seconds of wall time since the previous reading)"""
    for t, engines, dt in readings:
        wall.now += dt
        detector.update(t, engines, True)
    return detector.separated_at


def test_a_change_in_engine_count_after_liftoff_is_the_separation():
    wall = Wall()
    detector = SeparationDetector(wall)
    seen = feed(detector, wall, [(-5, 33, 0.1), (10, 33, 0.1), (77.9, 33, 0.1), (78.0, 6, 0.1), (78.3, 6, 0.3), (78.6, 6, 0.3)])
    assert seen == 78.0  # the moment the new count first appeared, not when it was confirmed


def test_a_brief_odd_reading_is_not_a_separation():
    wall = Wall()
    detector = SeparationDetector(wall)
    seen = feed(detector, wall, [(10, 33, 0.1), (20, 6, 0.1), (20.1, 33, 0.1), (20.5, 33, 0.4), (21, 33, 0.5)])
    assert seen is None


def test_nothing_counts_before_liftoff():
    wall = Wall()
    detector = SeparationDetector(wall)
    assert feed(detector, wall, [(-30, 33, 0.1), (-20, 6, 0.1), (-19, 6, 1.0), (-18, 6, 1.0)]) is None  # a vessel swap on the pad
    assert feed(detector, wall, [(5, 6, 1.0), (6, 6, 1.0)]) is None  # and the new count is the baseline from then on


def test_a_lost_feed_or_empty_reading_says_nothing():
    wall = Wall()
    detector = SeparationDetector(wall)
    feed(detector, wall, [(10, 33, 0.1)])
    wall.now += 1.0
    detector.update(20, 0, True)  # no engines read
    detector.update(21, 6, False)  # lost feed
    wall.now += 1.0
    detector.update(22, 6, False)
    assert detector.separated_at is None


def test_it_is_remembered_and_reset_clears_it():
    wall = Wall()
    detector = SeparationDetector(wall)
    feed(detector, wall, [(10, 33, 0.1), (78, 6, 0.1), (78.5, 6, CONFIRM_SECONDS + 0.1)])
    assert detector.separated_at == 78
    feed(detector, wall, [(90, 33, 0.1)])
    assert detector.separated_at == 78
    detector.reset()
    assert detector.separated_at is None
