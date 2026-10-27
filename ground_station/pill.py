"""The compact countdown "pill" shown before T-30s."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath

from .branding import DEFAULT_FLIGHT_LABEL
from .countdown import format_clock, pill_state
from .hud_window import HudWindow
from .source import DataSource

PILL_WIDTH = 330
PILL_HEIGHT = 58
SLANT = 40
MARGIN = 12
WINDOW_HEIGHT = PILL_HEIGHT + 76


def _pick_font(candidates: list[str]) -> str:
    families = set(QFontDatabase.families())
    return next((name for name in candidates if name in families), candidates[-1])


class PillWidget(HudWindow):
    def __init__(self, subtitle: str = DEFAULT_FLIGHT_LABEL, source: DataSource = DataSource.MOCK):
        super().__init__()
        self._t = -60.0
        self._subtitle = subtitle
        self._source = source
        self._scale = 1.0
        self._font_override = ""
        self._background: QColor | None = None
        self._family = _pick_font(["D-DIN Exp", "Bahnschrift", "Segoe UI Semibold", "Arial"])  # clock
        self._label_family = _pick_font(["D-DIN", "Bahnschrift", "Segoe UI Semibold", "Arial"])
        self.resize(PILL_WIDTH + 2 * MARGIN, WINDOW_HEIGHT)

    def set_time(self, t: float) -> None:
        self._t = t
        self.update()

    def set_subtitle(self, text: str) -> None:
        self._subtitle = text
        self.update()

    def set_source(self, source: DataSource) -> None:
        self._source = source
        self.update()

    def set_scale(self, scale: float) -> None:
        self._scale = scale
        self.resize(round((PILL_WIDTH + 2 * MARGIN) * scale), round(WINDOW_HEIGHT * scale))
        self.update()

    def set_font_override(self, family: str) -> None:
        """A chosen font for the pill's text, or '' for the bundled D-DIN."""
        self._font_override = family
        self.update()

    def set_background(self, colour: str | None) -> None:
        self._background = QColor(colour) if colour else None
        self.update()

    def _pill_path(self, x: float, y: float) -> QPainterPath:
        r = 14.0
        path = QPainterPath()
        path.moveTo(x, y)
        path.lineTo(x + PILL_WIDTH - r, y)
        path.quadTo(x + PILL_WIDTH, y, x + PILL_WIDTH - 5, y + r * 0.8)
        path.lineTo(x + PILL_WIDTH - SLANT, y + PILL_HEIGHT)
        path.lineTo(x, y + PILL_HEIGHT)
        path.closeSubpath()
        return path

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        if self._background is not None:
            painter.fillRect(self.rect(), self._background)
        state = pill_state(self._t)
        if not state.visible:
            return
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.scale(self._scale, self._scale)
        painter.setOpacity(state.opacity)
        x = MARGIN + state.x_offset
        y = MARGIN
        clock_family = self._font_override or self._family
        label_family = self._font_override or self._label_family

        painter.fillPath(self._pill_path(x, y), QColor(8, 16, 24, 215))

        sign, clock = format_clock(self._t)
        sign_font = QFont(clock_family)
        sign_font.setPixelSize(20)
        sign_font.setWeight(QFont.DemiBold)
        painter.setFont(sign_font)
        painter.setPen(QColor(200, 210, 220))
        painter.drawText(QRectF(x + 18, y, 40, PILL_HEIGHT), Qt.AlignVCenter | Qt.AlignLeft, sign)

        clock_font = QFont(clock_family)
        clock_font.setPixelSize(33)
        clock_font.setWeight(QFont.DemiBold)
        clock_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        painter.setFont(clock_font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(x + 54, y, 240, PILL_HEIGHT), Qt.AlignVCenter | Qt.AlignLeft, clock)

        sub_font = QFont(label_family)
        sub_font.setPixelSize(13)
        sub_font.setWeight(QFont.DemiBold)
        sub_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.4)
        painter.setFont(sub_font)
        painter.setPen(QColor(215, 225, 235))
        painter.drawText(
            QRectF(x + 18, y + PILL_HEIGHT + 8, PILL_WIDTH, 22), Qt.AlignVCenter | Qt.AlignLeft, self._subtitle.upper()
        )

        if self._source is not DataSource.LIVE:
            self._draw_source_chip(painter, label_family, x, y + PILL_HEIGHT + 34)

    def _draw_source_chip(self, painter: QPainter, family: str, x: float, y: float) -> None:
        font = QFont(family)
        font.setPixelSize(11)
        font.setWeight(QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        painter.setFont(font)
        rect = QRectF(x + 18, y, 96, 17)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(230, 160, 40))
        painter.drawRoundedRect(rect, 3, 3)
        painter.setPen(QColor(20, 14, 4))
        painter.drawText(rect, Qt.AlignCenter, f"{self._source.value} DATA")
