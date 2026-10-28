import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dataclasses
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ground_station.fonts import FONT_DIR, load_bundled_fonts
from ground_station.theme import STARSHIP


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    load_bundled_fonts()  # a headless machine may have no system fonts at all
    yield app


def test_oxanium_is_bundled_with_its_licence():
    assert "Oxanium" in load_bundled_fonts() and "D-DIN" in load_bundled_fonts()
    assert (FONT_DIR / "OFL-Oxanium.txt").read_text(encoding="utf-8").startswith("Copyright 2019 The Oxanium Project Authors")
    assert "Oxanium" in (Path(FONT_DIR).parent / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")


def test_the_starship_look_uses_oxanium():
    assert STARSHIP.family() == "Oxanium" and STARSHIP.family(wide=True) == "Oxanium"


def test_without_oxanium_the_starship_look_falls_back_to_d_din():
    without = dataclasses.replace(STARSHIP, fonts=("Not An Installed Font",) + STARSHIP.fonts[1:])
    assert without.family() == "D-DIN"


def test_the_clock_font_is_between_regular_and_medium_and_not_stretched():
    font = STARSHIP.make_font(STARSHIP.clock_px, STARSHIP.clock_weight, STARSHIP.spacing, wide=True)
    assert font.family() == "Oxanium" and font.pixelSize() == 50
    assert 500 <= int(font.weight()) <= 560
    assert font.stretch() in (0, 100)  # Oxanium is drawn at its own width


def test_an_operators_own_font_choice_still_comes_first():
    assert STARSHIP.tuned(font="D-DIN").family() == "D-DIN"
