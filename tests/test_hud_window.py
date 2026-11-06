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


def test_the_pill_and_the_bar_share_one_overlay_window():
    from ground_station.bar import TelemetryBar
    from ground_station.overlay import OverlayWindow
    from ground_station.pill import PillWidget

    overlay, pill, bar = OverlayWindow("Overlay"), PillWidget(), TelemetryBar()
    overlay.adopt(pill, bar)
    overlay.cover(0, 0, 1920, 1080)
    pill.move(10, 40)
    bar.move(300, 1080 - bar.height())
    overlay.set_window_options(on_top=True, click_through=False)
    pill.setVisible(True)
    bar.setVisible(True)
    overlay.show()
    assert pill.parentWidget() is overlay and bar.parentWidget() is overlay
    assert not pill.isWindow() and not bar.isWindow() and overlay.windowTitle() == "Overlay"
    mask = overlay.mask()
    assert mask.contains(pill.geometry().center()) and mask.contains(bar.geometry().center())
    from PySide6.QtCore import QPoint
    assert not mask.contains(QPoint(1900, 5))  # empty parts of the screen stay clickable
    bar.setVisible(False)
    assert not overlay.mask().contains(QPoint(bar.x() + 5, bar.y() + 5))
    overlay.set_window_options(on_top=True, click_through=True)
    assert overlay.mask().isEmpty()  # click-through: the whole window already ignores the mouse


def test_the_overlay_is_put_back_on_top_while_keep_in_front_is_on(monkeypatch):
    from ground_station import overlay as overlay_module

    calls = []
    monkeypatch.setattr(overlay_module.QGuiApplication, "platformName", staticmethod(lambda: "windows"))
    monkeypatch.setattr(overlay_module, "reassert_topmost", lambda hwnd: calls.append(hwnd) or True)
    window = overlay_module.OverlayWindow("test")
    window.show()
    window.set_window_options(True, True)
    window._keep_on_top()
    assert len(calls) == 1 and window.reasserted == 1  # on top, shown: it is put back
    window.set_window_options(False, True)
    window._keep_on_top()
    assert len(calls) == 1  # "keep in front" off: left alone
    window.set_window_options(True, True)
    window.hide()
    window._keep_on_top()
    assert len(calls) == 1  # not shown: nothing to put back
    assert window._keep_timer.isActive()


def test_putting_a_window_back_on_top_does_nothing_off_windows():
    from ground_station.keep_on_top import reassert_topmost

    import sys

    if sys.platform != "win32":
        assert reassert_topmost(1234) is False
    assert reassert_topmost(0) is False
