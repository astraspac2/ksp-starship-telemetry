"""The overlay windows must be ordinary windows, or OBS does not list them for Window Capture."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ground_station.hud_window import HudWindow

_app = QApplication.instance() or QApplication([])


def test_the_overlay_is_an_ordinary_window_not_a_tool_window():
    window = HudWindow()
    assert window.windowFlags() & Qt.Window
    assert (window.windowFlags() & Qt.WindowType_Mask) != Qt.Tool
    window.set_window_options(on_top=False, click_through=False)
    assert (window.windowFlags() & Qt.WindowType_Mask) != Qt.Tool
