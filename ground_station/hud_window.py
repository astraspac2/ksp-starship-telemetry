"""Shared behaviour of the two display windows: frameless, translucent, optionally click-through."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


class HudWindow(QWidget):
    """A borderless overlay window. While click-through is off it can be dragged with the mouse."""

    def __init__(self) -> None:
        super().__init__()
        self._on_top = True
        self._click_through = True
        self._drag_offset = None
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._apply_flags()

    def set_window_options(self, on_top: bool, click_through: bool) -> None:
        if (on_top, click_through) == (self._on_top, self._click_through):
            return
        self._on_top, self._click_through = on_top, click_through
        was_visible = self.isVisible()
        self._apply_flags()
        if was_visible:
            self.show()  # changing window flags hides the window, so bring it back

    def _apply_flags(self) -> None:
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self._on_top:
            flags |= Qt.WindowStaysOnTopHint
        if self._click_through:
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_offset = None
