"""Backgrounds for the control panel's looks: two painted skies, and a picture of the operator's own.

The painted ones come from shapes with a fixed random seed, so they are the same every run and need no image files.
"""

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPixmap, QRadialGradient

BACKDROP_THEMES = ("deepspace", "mars", "custom")  # the looks that paint a background (forest has its own module)


def _glow(painter: QPainter, x: float, y: float, radius: float, colour: QColor) -> None:
    gradient = QRadialGradient(QPointF(x, y), radius)
    gradient.setColorAt(0.0, colour)
    faded = QColor(colour)
    faded.setAlpha(0)
    gradient.setColorAt(1.0, faded)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawEllipse(QPointF(x, y), radius, radius)


def paint_deep_space(painter: QPainter, width: int, height: int) -> None:
    """Night sky: a violet-to-black gradient, two soft nebulae, scattered stars and the rim of a planet."""
    sky = QLinearGradient(0, 0, 0, height)
    sky.setColorAt(0.0, QColor("#04050c"))
    sky.setColorAt(0.6, QColor("#0b0a22"))
    sky.setColorAt(1.0, QColor("#1b1038"))
    painter.fillRect(0, 0, width, height, sky)
    _glow(painter, width * 0.78, height * 0.25, max(width, height) * 0.38, QColor(120, 70, 220, 70))
    _glow(painter, width * 0.18, height * 0.62, max(width, height) * 0.30, QColor(40, 150, 200, 55))
    rng = random.Random(7)
    painter.setPen(Qt.NoPen)
    for _ in range(int(width * height / 3500)):
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        size = rng.choice((1.0, 1.0, 1.0, 1.6, 2.2))
        painter.setBrush(QColor(255, 255, 255, rng.randint(70, 230)))
        painter.drawEllipse(QPointF(x, y), size / 2, size / 2)
    planet = QRadialGradient(QPointF(width * 0.5, height * 1.9), height * 1.0)
    planet.setColorAt(0.0, QColor("#0a1226"))
    planet.setColorAt(0.93, QColor("#13284a"))
    planet.setColorAt(0.97, QColor("#4f9be0"))
    planet.setColorAt(1.0, QColor(79, 155, 224, 0))
    painter.setBrush(QBrush(planet))
    painter.drawEllipse(QPointF(width * 0.5, height * 1.9), height * 1.0, height * 1.0)


def _dune(painter: QPainter, width: int, height: int, base: float, amplitude: float, phase: float, colour: QColor) -> None:
    path = QPainterPath()
    path.moveTo(0, height)
    x = 0.0
    while x <= width + 8:
        y = base + amplitude * math.sin(x / 260.0 + phase) + amplitude * 0.4 * math.sin(x / 90.0 + phase * 2.1)
        path.lineTo(x, y)
        x += 8
    path.lineTo(width, height)
    path.closeSubpath()
    painter.fillPath(path, colour)


def paint_mars(painter: QPainter, width: int, height: int) -> None:
    """Dusty dusk on Mars: a rust sky, a small pale sun low on the horizon, and layered dunes."""
    sky = QLinearGradient(0, 0, 0, height)
    sky.setColorAt(0.0, QColor("#120806"))
    sky.setColorAt(0.55, QColor("#4a1f12"))
    sky.setColorAt(0.8, QColor("#b5532a"))
    sky.setColorAt(1.0, QColor("#e08a4e"))
    painter.fillRect(0, 0, width, height, sky)
    _glow(painter, width * 0.72, height * 0.72, height * 0.55, QColor(120, 170, 230, 90))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(235, 240, 255, 235))
    painter.drawEllipse(QPointF(width * 0.72, height * 0.72), 9, 9)
    rng = random.Random(11)
    for _ in range(int(width * height / 9000)):  # a few stars high in the sky
        painter.setBrush(QColor(255, 235, 220, rng.randint(40, 150)))
        painter.drawEllipse(QPointF(rng.uniform(0, width), rng.uniform(0, height * 0.4)), 0.8, 0.8)
    _dune(painter, width, height, height * 0.80, 18, 0.4, QColor("#7a3418"))
    _dune(painter, width, height, height * 0.87, 22, 2.2, QColor("#5a2511"))
    _dune(painter, width, height, height * 0.94, 16, 4.0, QColor("#3a180c"))


def load_cover(path: str, width: int, height: int, dim: int) -> QPixmap | None:
    """The picture scaled to fill the window (cropped, never stretched), darkened by `dim` per cent. None if unreadable."""
    picture = QPixmap(path) if path else QPixmap()
    if picture.isNull() or width < 1 or height < 1:
        return None
    scaled = picture.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    left, top = (scaled.width() - width) // 2, (scaled.height() - height) // 2
    cover = scaled.copy(left, top, width, height)
    painter = QPainter(cover)
    painter.fillRect(cover.rect(), QColor(0, 0, 0, round(255 * max(0, min(100, dim)) / 100)))
    painter.end()
    return cover


def render_backdrop(theme: str, width: int, height: int, image: str = "", dim: int = 55) -> QPixmap | None:
    """The background for one of BACKDROP_THEMES, or None when there is nothing to paint (e.g. no readable picture)."""
    if theme == "custom":
        return load_cover(image, width, height, dim)
    if theme not in BACKDROP_THEMES:
        return None
    pixmap = QPixmap(max(width, 1), max(height, 1))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    (paint_deep_space if theme == "deepspace" else paint_mars)(painter, pixmap.width(), pixmap.height())
    painter.end()
    return pixmap
