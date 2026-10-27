"""Wires the session, the two display windows and the control panel into one running app."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from . import settings as settings_io
from .bar import TelemetryBar
from .fonts import load_bundled_fonts
from .panel import ControlPanel, place_on_second_screen
from .pill import MARGIN as PILL_MARGIN
from .pill import PillWidget
from .session import Session
from .single_instance import acquire_or_explain
from .theme import THEMES

PANEL_REFRESH_MS = 250
PILL_TOP_GAP = 40  # pixels between the top of the screen and the pill's drawn shape (at 100 % size)
CORNER_GAP = 16  # the small pad bar sits this far from the bottom and right edges of the screen


def pill_visible(show_pill: bool, view_mode: str) -> bool:
    """The countdown pill is for flights; the pad / static-fire view has no pill."""
    return show_pill and view_mode != "pad"


def hud_positions(left: int, top: int, width: int, height: int, bar_w: int, bar_h: int, scale: float, corner: bool = False):
    """Window positions that put the pill's visible shape at the left edge, a little below the top, and the bar flush on the bottom edge.

    With `corner` (the small pad bar) the bar goes to the bottom right corner instead, a little in from both edges.

    The pill window has a transparent margin around the drawn shape, so it is moved outward by that margin.
    """
    inset = round(PILL_MARGIN * scale)
    pill = (left - inset, top - inset + round(PILL_TOP_GAP * scale))
    if corner:
        gap = round(CORNER_GAP * scale)
        return pill, (left + width - bar_w - gap, top + height - bar_h - gap)
    return pill, (left + (width - bar_w) // 2, top + height - bar_h)


class GroundStationApp:
    def __init__(self, argv: list[str]):
        self.app = QApplication(argv)
        load_bundled_fonts()
        self.session = Session(settings_io.load())
        self.pill = PillWidget(subtitle=self.session.settings.mission_label)
        self.bar = TelemetryBar(subtitle=self.session.settings.mission_label, milestones=self.session.milestones())
        self._scale_placed = None  # the HUD scale and view the windows were last positioned for
        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self.tick)
        self.panel = ControlPanel(self.session, self.apply_display, self._preview)

        self.panel_timer = QTimer()
        self.panel_timer.setInterval(PANEL_REFRESH_MS)
        self.panel_timer.timeout.connect(self.panel.refresh)
        self.app.aboutToQuit.connect(self.session.shutdown)
        place_on_second_screen(self.panel)
        self.apply_display()
        self.session.connect_on_start()

    def _preview(self) -> QPixmap | None:
        return self.bar.grab() if self.session.settings.show_bar else None

    def _place_windows(self) -> None:
        screen = self.app.primaryScreen().geometry()  # the whole screen, not the part above the taskbar
        (pill_x, pill_y), (bar_x, bar_y) = hud_positions(
            screen.left(), screen.top(), screen.width(), screen.height(), self.bar.width(), self.bar.height(), self.session.settings.hud_scale,
            corner=self.session.pad_mode,
        )
        self.pill.move(pill_x, pill_y)
        self.bar.move(bar_x, bar_y)

    def apply_display(self) -> None:
        s = self.session.settings
        theme = next((t for t in THEMES if t.name == s.theme), THEMES[0]).tuned(s.font, s.accent, s.panel_opacity)
        background = s.background_color if s.background == "solid" else None

        self.pill.set_subtitle(s.mission_label)
        self.pill.set_scale(s.hud_scale)
        self.pill.set_font_override(s.font)
        self.pill.set_background(background)
        self.pill.set_window_options(s.on_top, s.click_through)

        self.bar.set_subtitle(s.mission_label)
        self.bar.set_theme(theme)
        self.bar.set_units(s.speed_unit, s.altitude_unit)
        self.bar.set_thrust_unit(s.thrust_unit)
        self.bar.set_view_mode(s.view_mode)
        self.bar.set_milestones(self.session.milestones())
        self.bar.set_scale(s.hud_scale)
        self.bar.set_background(background)
        self.bar.set_badge(s.show_badge)
        self.bar.set_show_map(s.show_map)
        self.bar.set_timeline(s.show_timeline, s.timeline_nodes)
        self.bar.set_window_options(s.on_top, s.click_through)
        problem = self.bar.set_vessel_model(s.vessel_model, s.vessel_model_flip, s.starship_model)
        if problem:
            self.panel.statusBar().showMessage(f"The 3D model could not be used, so the built-in rocket is shown: {problem}")

        if self._scale_placed != (s.hud_scale, s.view_mode):  # only reposition when the size changes, so a dragged HUD stays put
            self._place_windows()
            self._scale_placed = (s.hud_scale, s.view_mode)
        self.pill.setVisible(pill_visible(s.show_pill, s.view_mode))
        self.bar.setVisible(s.show_bar)
        self.display_timer.setInterval(round(1000 / s.refresh_hz))

    def tick(self) -> None:
        telemetry = self.session.telemetry()
        self.pill.set_source(telemetry.source)
        self.pill.set_time(telemetry.t)
        self.bar.set_telemetry(telemetry)

    def run(self) -> int:
        self.display_timer.start()
        self.panel_timer.start()
        self.panel.show()
        return self.app.exec()


def main() -> int:
    lock = acquire_or_explain()  # held until the app exits
    if lock is None:
        return 1
    try:
        return GroundStationApp(sys.argv).run()
    finally:
        lock.unlock()
