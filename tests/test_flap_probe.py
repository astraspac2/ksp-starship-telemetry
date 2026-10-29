from types import SimpleNamespace

from ground_station.flap_probe import read_flaps


def make_flap(name="BL3Flap", deployed=True, limiter=40.0, modules=None):
    module = SimpleNamespace(name="ModuleControlSurface", fields={"Deploy Angle": "50", "Authority Limiter": "40", "Other": "x"})
    part = SimpleNamespace(name=name, title="Donnager BL-3 Rear Right Flap", modules=modules if modules is not None else [module],
                           direction=lambda frame: (0.0, 1.0, 0.0))
    return SimpleNamespace(part=part, deployed=deployed, authority_limiter=limiter, pitch_enabled=True, yaw_enabled=True,
                           roll_enabled=False, inverted=False, surface_area=3.0)


def make_vessel(surfaces):
    return SimpleNamespace(parts=SimpleNamespace(control_surfaces=surfaces), control=SimpleNamespace(pitch=0.5, yaw=0.0, roll=-0.25),
                           reference_frame="frame")


def test_each_flap_gives_a_row_with_its_state_fields_and_the_pilots_input():
    rows = read_flaps(make_vessel([make_flap(), make_flap("Other", deployed=False)]), 3.0)
    assert len(rows) == 2 and rows[0]["errors"] == ""
    assert (rows[0]["deployed"], rows[1]["deployed"], rows[0]["authority_limiter"]) == (True, False, 40.0)
    assert rows[0]["input_pitch"] == 0.5 and rows[0]["input_roll"] == -0.25
    assert "ModuleControlSurface:Deploy Angle=50" in rows[0]["fields"] and "Other" not in rows[0]["fields"]


def test_a_module_that_will_not_list_its_fields_is_reported_not_fatal():
    class Broken:
        name = "ModuleControlSurface"

        @property
        def fields(self):
            raise RuntimeError("no")

    row = read_flaps(make_vessel([make_flap(modules=[Broken()])]), 1.0)[0]
    assert "ERR RuntimeError" in row["fields"] and row["deployed"] is True


def test_a_vessel_that_will_not_list_its_control_surfaces_gives_one_error_row():
    class Unloaded:
        control = SimpleNamespace()

        @property
        def parts(self):
            raise RuntimeError("not loaded")

    rows = read_flaps(Unloaded(), 1.0)
    assert len(rows) == 1 and "control_surfaces=ERR RuntimeError" in rows[0]["errors"]
