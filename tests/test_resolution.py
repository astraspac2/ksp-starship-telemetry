import pytest

from ground_station.resolution import AUTO, CHOICES, DESIGN_WIDTH, RESOLUTIONS, label, resolution_scale
from ground_station.settings import Settings


def test_the_hud_is_drawn_for_a_1920_wide_screen_and_scaled_by_the_width_of_the_monitor():
    assert resolution_scale("1920x1080", 3840) == 1.0  # a chosen resolution wins over the screen
    assert resolution_scale("3840x2160", 1920) == 2.0
    assert resolution_scale("1280x720", 1920) == pytest.approx(1280 / DESIGN_WIDTH)
    assert resolution_scale(AUTO, 2560) == pytest.approx(2560 / 1920)  # automatic follows the screen
    assert resolution_scale(AUTO, 1920) == 1.0  # on the design size nothing changes


def test_nonsense_gives_the_design_size_instead_of_a_crash():
    assert resolution_scale("wide", 1920) == 1.0
    assert resolution_scale(AUTO, 0) == 1.0


def test_every_choice_has_a_label_and_the_settings_know_them():
    assert label(AUTO).startswith("Automatic") and label("2560x1440") == "2560 x 1440"
    assert CHOICES == (AUTO,) + RESOLUTIONS
    assert Settings().resolution == AUTO  # automatic by default
    assert Settings(resolution="7x7").validated().resolution == AUTO  # an unknown value falls back
    assert Settings(resolution="2560x1440").validated().resolution == "2560x1440"
