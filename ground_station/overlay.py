"""One window for the whole overlay: the countdown pill and the telemetry bar together, so a capture program sees a single window.

The window covers the screen, as big as the picture on stream, and is transparent where nothing is drawn. While click-through is
off, only the parts that hold the pill and the bar take the mouse (a mask), so the rest of the screen stays usable.
"""

from PySide6.QtCore import QEvent, QRect
from PySide6.QtGui import QColor, QPainter, QRegion
from PySide6.QtWidgets import QWidget

from .hud_window import HudWindow

MASK_EVENTS = (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.Hide)


class OverlayWindow(HudWindow):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self._parts: list[QWidget] = []
        self._background: QColor | None = None

    def adopt(self, *widgets: HudWindow) -> None:
        for widget in widgets:
            widget.embed(self)
            widget.installEventFilter(self)
            self._parts.append(widget)

    def cover(self, left: int, top: int, width: int, height: int) -> None:
        self.setGeometry(left, top, width, height)

    def set_background(self, colour: str | None) -> None:
        self._background = QColor(colour) if colour else None
        self.update()

    def set_window_options(self, on_top: bool, click_through: bool) -> None:
        super().set_window_options(on_top, click_through)
        self._refresh_mask()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in MASK_EVENTS:
            self._refresh_mask()
        return False

    def _refresh_mask(self) -> None:
        if self._click_through:
            self.clearMask()
            return
        region = QRegion()
        for part in self._parts:
            if part.isVisibleTo(self):
                region = region.united(QRegion(part.geometry()))
        self.setMask(region if not region.isEmpty() else QRegion(QRect(0, 0, 1, 1)))

    def paintEvent(self, _event) -> None:
        if self._background is not None:
            QPainter(self).fillRect(self.rect(), self._background)
