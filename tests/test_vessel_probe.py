from types import SimpleNamespace

from ground_station.vessel_probe import probe, read_vessel


class Flight:
    def __init__(self, altitude, speed):
        self.surface_altitude, self.speed = altitude, speed


class FakeVessel:
    def __init__(self, name, distance, loaded=True, altitude=1200.0, speed=300.0):
        self.name, self.situation = name, SimpleNamespace(name="flying")
        self._distance, self._loaded, self._flight = distance, loaded, Flight(altitude, speed)
        self.orbit = SimpleNamespace(body=SimpleNamespace(reference_frame="body"))
        self.reference_frame = f"frame-{name}"

    def position(self, frame):
        return (self._distance, 0.0, 0.0)

    def flight(self, frame=None):
        return self._flight

    @property
    def parts(self):
        if not self._loaded:
            raise RuntimeError("vessel is not loaded")
        return SimpleNamespace(all=[1, 2, 3], engines=[1])


def test_a_loaded_vessel_reads_fully():
    row = read_vessel(FakeVessel("Booster", 3000.0), FakeVessel("Ship", 0.0))
    assert row["readable"] and (row["distance_m"], row["altitude_m"], row["speed_ms"], row["parts"]) == (3000.0, 1200.0, 300.0, 3)


def test_an_unloaded_vessel_is_marked_not_readable_with_the_reason():
    row = read_vessel(FakeVessel("Booster", 90_000.0, loaded=False), FakeVessel("Ship", 0.0))
    assert not row["readable"] and row["parts"] == "ERR RuntimeError"
    assert row["altitude_m"] == 1200.0  # what can still be read is still shown


def test_probe_lists_the_flown_vessel_first_then_the_nearest():
    ship = FakeVessel("Ship", 0.0)
    centre = SimpleNamespace(
        active_vessel=ship, vessels=[FakeVessel("Far", 50_000.0), FakeVessel("Booster", 3000.0), ship]
    )
    rows = probe(centre)
    assert [r["name"] for r in rows] == ["Ship", "Booster", "Far"]
    assert [r["active"] for r in rows] == [True, False, False]
