from types import SimpleNamespace

from ground_station.flap_probe import read_flaps


def make_part(name="BL3Flap", title="Donnager BL-3 Rear Right Flap", modules=None):
    if modules is None:
        modules = [SimpleNamespace(name="ModuleControlSurface", fields={"Deploy": "Retracted", "Deploy Angle": "50", "Authority Limiter": "40"})]
    return SimpleNamespace(name=name, title=title, modules=modules, direction=lambda frame: (0.0, 1.0, 0.0))


def make_vessel(parts):
    return SimpleNamespace(parts=SimpleNamespace(all=parts), control=SimpleNamespace(pitch=0.5, yaw=0.0, roll=-0.25), reference_frame="frame")


def test_a_flap_gives_a_row_with_its_modules_fields_and_the_pilots_input():
    rows = read_flaps(make_vessel([make_part()]), 3.0)
    assert len(rows) == 1 and rows[0]["errors"] == ""
    assert (rows[0]["deploy_angle"], rows[0]["authority_limiter"], rows[0]["deployed"]) == ("50", "40", "Retracted")
    assert rows[0]["modules"] == "ModuleControlSurface" and rows[0]["kind"] == "control-surface"
    assert rows[0]["input_pitch"] == 0.5 and rows[0]["input_roll"] == -0.25


def test_a_flap_on_a_module_kRPC_does_not_know_is_still_found_by_its_title():
    custom = SimpleNamespace(name="ModuleSEPFlap", fields={"Angle": "12"})
    rows = read_flaps(make_vessel([make_part(title="Starship Flap", modules=[custom])]), 1.0)
    assert len(rows) == 1 and rows[0]["kind"] == "other" and "ModuleSEPFlap:Angle=12" in rows[0]["fields"]


def test_a_part_with_a_deploy_angle_field_is_found_whatever_its_title():
    odd = SimpleNamespace(name="ModuleX", fields={"Deploy Angle": "30"})
    assert len(read_flaps(make_vessel([make_part(title="Widget", modules=[odd])]), 1.0)) == 1


def test_ordinary_parts_are_left_out():
    tank = make_part(title="Fuel tank", modules=[SimpleNamespace(name="ModuleLight", fields={"Colour": "red"})])
    assert read_flaps(make_vessel([tank]), 1.0) == []


def test_a_module_that_will_not_list_its_fields_is_reported_not_fatal():
    class Broken:
        name = "ModuleControlSurface"

        @property
        def fields(self):
            raise RuntimeError("no")

    row = read_flaps(make_vessel([make_part(modules=[Broken()])]), 1.0)[0]
    assert "ERR RuntimeError" in row["fields"] and row["errors"] != ""


def test_a_vessel_that_will_not_list_its_parts_gives_one_error_row():
    class Unloaded:
        control = SimpleNamespace()

        @property
        def parts(self):
            raise RuntimeError("not loaded")

    rows = read_flaps(Unloaded(), 1.0)
    assert len(rows) == 1 and "parts=ERR RuntimeError" in rows[0]["errors"]
