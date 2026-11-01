from types import SimpleNamespace

from ground_station.booster_probe import DROP_PARTS, FIND_SECONDS, BoosterFinder, read_booster


class FakeEngine:
    def __init__(self, name="cluster", active=True, thrust=1000.0, nozzles=13, mode="13"):
        self.part = SimpleNamespace(name=name, modules=[SimpleNamespace(name="ModuleSEPEngineSwitch", get_field=lambda f: mode)])
        self.active, self.thrust, self.available_thrust, self.thrusters = active, thrust, thrust * 2, [0] * nozzles


class FakeFlight:
    surface_altitude, mean_altitude, speed = 26_100.0, 26_500.0, 1269.0
    mach, dynamic_pressure, g_force, atmosphere_density = 4.1, 21_000.0, 1.8, 0.04


class FakeVessel:
    def __init__(self, distance=100.0, parts=10, engines=(), loaded=True):
        self.met, self.situation, self.mass = 200.0, SimpleNamespace(name="flying"), 40_000.0
        self.reference_frame = "frame"
        self._distance, self._parts, self._engines, self._loaded = distance, parts, list(engines), loaded
        self.orbit = SimpleNamespace(body=SimpleNamespace(reference_frame="body"))
        self.control = SimpleNamespace(throttle=0.5)

    def position(self, frame):
        return (self._distance, 0.0, 0.0)

    def flight(self, frame=None):
        return FakeFlight()

    @property
    def parts(self):
        if not self._loaded:
            raise RuntimeError("not loaded")
        return SimpleNamespace(all=[0] * self._parts, engines=self._engines)


def test_a_loaded_booster_gives_a_full_row():
    vessel = FakeVessel(engines=[FakeEngine(), FakeEngine("core", active=False, thrust=0.0, nozzles=3, mode="3")])
    row = read_booster(vessel, FakeVessel(0.0), 5000.0, 12.5)
    assert row["errors"] == ""
    assert (row["altitude_m"], row["speed_ms"], row["mach"], row["parts"], row["engines"], row["engines_active"]) == (26_100.0, 1269.0, 4.1, 10, 2, 1)
    assert row["thrust_n"] == 1000.0 and row["sep_modes"] == "13;3"
    assert row["engine_detail"] == "cluster:on:1000:13n;core:off:0:3n"


def test_an_unreadable_booster_names_what_failed_and_keeps_what_still_reads():
    row = read_booster(FakeVessel(loaded=False), FakeVessel(0.0), 5000.0, 12.5)
    assert row["altitude_m"] == 26_100.0 and row["parts"] == "ERR RuntimeError"
    assert "parts=ERR RuntimeError" in row["errors"] and "engines=ERR RuntimeError" in row["errors"]


def test_the_booster_is_taken_for_the_nearest_vessel_when_the_ship_drops_parts_at_once():
    ship = FakeVessel(0.0, parts=40)
    booster, pad_vessel = FakeVessel(300.0), FakeVessel(30_000.0)
    centre = SimpleNamespace(active_vessel=ship, vessels=[ship, pad_vessel, booster])
    finder = BoosterFinder()
    assert finder.update(0.0, centre) is None and finder.update(1.0, centre) is None  # nothing has separated yet
    ship._parts = 40 - DROP_PARTS
    assert finder.update(2.0, centre) is booster
    assert finder.update(3.0, centre) is booster  # and it stays that one


def test_the_booster_is_only_looked_for_for_a_while_after_the_separation():
    ship = FakeVessel(0.0, parts=40)
    centre = SimpleNamespace(active_vessel=ship, vessels=[ship])
    finder = BoosterFinder()
    finder.update(0.0, centre)
    ship._parts = 20
    finder.update(1.0, centre)
    centre.vessels.append(FakeVessel(300.0))
    assert finder.update(1.0 + FIND_SECONDS + 5.0, centre) is None
