import json

from ground_station import settings


def test_round_trip(tmp_path):
    path = tmp_path / "s.json"
    original = settings.Settings(
        address="192.168.1.5",
        rpc_port=51000,
        speed_unit="mph",
        altitude_unit="km",
        show_pill=False,
        accent="#5CB6FF",
        panel_opacity=0.4,
        hud_scale=1.25,
        background="solid",
        click_through=False,
        panel_theme="forest",
    )
    settings.save(original, path)
    assert settings.load(path) == original


def test_missing_file_gives_defaults(tmp_path):
    assert settings.load(tmp_path / "nope.json") == settings.Settings()


def test_corrupt_file_gives_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{ not json", encoding="utf-8")
    assert settings.load(path) == settings.Settings()


def test_unknown_keys_are_ignored_and_bad_values_replaced(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps({"rpc_port": 99999, "speed_unit": "furlongs", "refresh_hz": 7, "source": "REPLAY", "extra": 1, "subtitle": "X"}),
        encoding="utf-8",
    )
    loaded = settings.load(path)
    defaults = settings.Settings()
    assert loaded.rpc_port == defaults.rpc_port
    assert loaded.speed_unit == defaults.speed_unit
    assert loaded.refresh_hz == defaults.refresh_hz
    assert loaded.source == defaults.source
    assert loaded.subtitle == "X"


def test_events_and_new_options_round_trip_and_bad_ones_are_cleaned(tmp_path):
    path = tmp_path / "s.json"
    original = settings.Settings(
        warp_policy="hold",
        theme="B - Glass",
        events=[{"time": -600.0, "label": "Broadcast", "description": "d", "enabled": False}],
    )
    settings.save(original, path)
    assert settings.load(path) == original
    path.write_text(json.dumps({"events": [{"time": "x"}, {"time": 3, "label": "ok"}], "theme": "Z", "warp_policy": "?"}), encoding="utf-8")
    loaded = settings.load(path)
    assert [e["label"] for e in loaded.events] == ["ok"]
    assert loaded.theme == settings.THEMES[0] and loaded.warp_policy == "follow"


def test_hud_options_out_of_range_fall_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {
                "accent": "red",
                "background_color": "#12",
                "panel_opacity": 4,
                "hud_scale": 9,
                "timeline_nodes": 0,
                "click_through": "yes",
                "font": 12,
                "background": "image",
                "altitude_mode": "moon",
                "panel_theme": "neon",
            }
        ),
        encoding="utf-8",
    )
    loaded = settings.load(path)
    assert loaded == settings.Settings()


def test_a_hand_set_accent_and_opacity_survive(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"accent": "#00ff88", "panel_opacity": 0.0, "hud_scale": 0.5}), encoding="utf-8")
    loaded = settings.load(path)
    assert loaded.accent == "#00ff88" and loaded.panel_opacity == 0.0 and loaded.hud_scale == 0.5


def test_default_events_are_not_shared_between_instances():
    a, b = settings.Settings(), settings.Settings()
    a.events.append({"time": 1.0, "label": "x"})
    assert len(b.events) == 3


def test_save_creates_missing_folders(tmp_path):
    path = tmp_path / "a" / "b" / "s.json"
    settings.save(settings.Settings(), path)
    assert path.exists()


def test_auto_connect_is_on_by_default_and_a_bad_value_falls_back(tmp_path):
    assert settings.Settings().auto_connect is True
    path = tmp_path / "s.json"
    path.write_text('{"auto_connect": "yes"}', encoding="utf8")
    assert settings.load(path).auto_connect is True


def test_show_map_defaults_off_and_is_saved(tmp_path):
    assert settings.Settings().show_map is False
    path = tmp_path / "s.json"
    s = settings.Settings()
    s.show_map = True
    settings.save(s, path)
    assert settings.load(path).show_map is True


def test_the_view_mode_is_flight_unless_the_operator_chooses_the_pad(tmp_path):
    assert settings.Settings().view_mode == "flight"  # a mode is only ever the operator's choice
    path = tmp_path / "s.json"
    s = settings.Settings()
    s.view_mode = "pad"
    settings.save(s, path)
    assert settings.load(path).view_mode == "pad"
    path.write_text('{"view_mode": "static fire"}', encoding="utf8")
    assert settings.load(path).view_mode == "flight"


def test_thrust_unit_defaults_to_auto_and_a_bad_one_falls_back(tmp_path):
    assert settings.Settings().thrust_unit == "auto"
    path = tmp_path / "s.json"
    path.write_text('{"thrust_unit": "tf"}', encoding="utf8")
    assert settings.load(path).thrust_unit == "tf"
    path.write_text('{"thrust_unit": "furlongs"}', encoding="utf8")
    assert settings.load(path).thrust_unit == "auto"


def test_the_pad_has_its_own_event_list_with_a_short_burn_and_bad_rows_are_dropped(tmp_path):
    defaults = settings.Settings()
    assert [e["label"] for e in defaults.pad_events] == ["Ignition", "Shutdown"]
    assert [e["label"] for e in defaults.events] == ["Liftoff", "Max Q", "Stage Sep"]  # the flight list is its own
    path = tmp_path / "s.json"
    path.write_text('{"pad_events": [{"time": 5, "label": "Full thrust"}, {"label": "no time"}, 7]}', encoding="utf8")
    loaded = settings.load(path)
    assert [e["label"] for e in loaded.pad_events] == ["Full thrust"]
    path.write_text('{"pad_events": "nonsense"}', encoding="utf8")
    assert [e["label"] for e in settings.load(path).pad_events] == ["Ignition", "Shutdown"]
