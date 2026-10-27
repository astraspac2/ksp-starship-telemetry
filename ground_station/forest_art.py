"""A painted dusk forest used as the background of the control panel's Forest look.

Everything is drawn from shapes with a fixed random seed, so the picture is the same every run and
needs no image files.
"""

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPixmap, QPolygonF, QRadialGradient


def _ridge(painter: QPainter, width: int, base: float, amplitude: float, phase: float, colour: QColor, height: int) -> None:
    path = QPainterPath()
    path.moveTo(0, height)
    x = 0.0
    while x <= width + 8:
        y = (
            base
            + amplitude * math.sin(x / 210.0 + phase)
            + amplitude * 0.5 * math.sin(x / 83.0 + phase * 2.3)
            + amplitude * 0.25 * math.sin(x / 37.0 + phase * 4.1)
        )
        path.lineTo(x, y)
        x += 8
    path.lineTo(width, height)
    path.closeSubpath()
    painter.fillPath(path, colour)


def _pine(painter: QPainter, x: float, base: float, size: float, colour: QColor) -> None:
    """One pine: a trunk and three stacked tiers that get narrower toward the top."""
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(colour))
    painter.drawRect(QRectF(x - size * 0.04, base - size * 0.12, size * 0.08, size * 0.12))
    tiers = ((0.30, 0.46), (0.52, 0.34), (0.72, 0.22))
    for rise, half_width in tiers:
        top = base - size * (rise + 0.28)
        bottom = base - size * (rise - 0.02) - size * 0.1
        painter.drawPolygon(QPolygonF([QPointF(x, top), QPointF(x + size * half_width * 0.62, bottom), QPointF(x - size * half_width * 0.62, bottom)]))


def _tree_line(painter: QPainter, width: int, base: float, size: tuple[float, float], gap: float, colour: QColor, rng: random.Random) -> None:
    x = -size[1] * 0.3
    while x < width + size[1]:
        _pine(painter, x, base + rng.uniform(-6, 6), rng.uniform(*size), colour)
        x += gap * rng.uniform(0.6, 1.4)


def paint_forest(painter: QPainter, width: int, height: int) -> None:
    rng = random.Random(7)
    sky = QLinearGradient(0, 0, 0, height)
    sky.setColorAt(0.0, QColor(5, 18, 24))
    sky.setColorAt(0.45, QColor(12, 52, 50))
    sky.setColorAt(0.75, QColor(40, 104, 78))
    sky.setColorAt(1.0, QColor(26, 74, 54))
    painter.fillRect(0, 0, width, height, sky)

    for _ in range(70):  # stars, fading out toward the horizon
        x, y = rng.uniform(0, width), rng.uniform(0, height * 0.42)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(220, 245, 230, int(40 + 140 * (1 - y / (height * 0.42)) * rng.random())))
        painter.drawEllipse(QPointF(x, y), 1.1, 1.1)

    moon = QPointF(width * 0.8, height * 0.2)
    glow = QRadialGradient(moon, 150)
    glow.setColorAt(0.0, QColor(220, 255, 220, 120))
    glow.setColorAt(0.25, QColor(180, 235, 190, 45))
    glow.setColorAt(1.0, QColor(180, 235, 190, 0))
    painter.fillRect(QRectF(moon.x() - 160, moon.y() - 160, 320, 320), glow)
    painter.setBrush(QColor(232, 250, 226))
    painter.drawEllipse(moon, 24, 24)

    _ridge(painter, width, height * 0.55, 34, 0.4, QColor(36, 92, 74, 230), height)
    _ridge(painter, width, height * 0.64, 40, 2.1, QColor(24, 70, 56, 240), height)

    mist = QLinearGradient(0, height * 0.58, 0, height * 0.8)
    mist.setColorAt(0.0, QColor(190, 235, 205, 0))
    mist.setColorAt(0.5, QColor(190, 235, 205, 38))
    mist.setColorAt(1.0, QColor(190, 235, 205, 0))
    painter.fillRect(0, int(height * 0.58), width, int(height * 0.22), mist)

    _tree_line(painter, width, height * 0.76, (70, 120), 26, QColor(26, 88, 64, 245), rng)
    _tree_line(painter, width, height * 0.86, (110, 190), 40, QColor(15, 60, 44, 250), rng)
    _tree_line(painter, width, height * 1.0, (190, 300), 70, QColor(6, 34, 24, 255), rng)

    for _ in range(26):  # fireflies between the trees
        x, y = rng.uniform(0, width), rng.uniform(height * 0.55, height * 0.95)
        spark = QRadialGradient(QPointF(x, y), 11)
        spark.setColorAt(0.0, QColor(235, 255, 160, 230))
        spark.setColorAt(0.3, QColor(200, 245, 120, 70))
        spark.setColorAt(1.0, QColor(200, 245, 120, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(spark))
        painter.drawEllipse(QPointF(x, y), 11, 11)

    painter.fillRect(0, 0, width, height, QColor(0, 6, 4, 50))  # dim it a little so the controls on top stay readable


def render_forest(width: int, height: int) -> QPixmap:
    pixmap = QPixmap(max(width, 1), max(height, 1))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    paint_forest(painter, pixmap.width(), pixmap.height())
    painter.end()
    return pixmap
