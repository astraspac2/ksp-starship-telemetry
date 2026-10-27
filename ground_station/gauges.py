"""Painter helpers for the bar's round instruments."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen

from .attitude import VIEW_ELEVATION_DEG, compass_point
from .textdraw import draw_text
from .theme import Theme

ARC_START_DEG = 210.0  # lower left; Qt angles run counter-clockwise from 3 o'clock
ARC_SPAN_DEG = 240.0  # clockwise over the top to the lower right, leaving a wide gap at the bottom
ARC_START = int(ARC_START_DEG * 16)  # Qt takes 1/16 degree
ARC_SWEEP = -int(ARC_SPAN_DEG * 16)
END_TICK_LENGTH = 8.0
ROCKET_LENGTH = 1.72  # the dial's rocket standing upright, in dial radii


def _backing(painter: QPainter, center: QPointF, radius: float) -> None:
    """Dark disc behind the engine cluster and the dial, as on the overlay."""
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(0, 0, 0, 75))
    painter.drawEllipse(center, radius, radius)


def _radial(center: QPointF, radius: float, degrees: float, inner: float, outer: float) -> tuple[QPointF, QPointF]:
    angle = math.radians(degrees)
    return (
        QPointF(center.x() + (radius - inner) * math.cos(angle), center.y() - (radius - inner) * math.sin(angle)),
        QPointF(center.x() + (radius + outer) * math.cos(angle), center.y() - (radius + outer) * math.sin(angle)),
    )


def _arc(
    painter: QPainter, center: QPointF, radius: float, fraction: float, theme: Theme, width: float, backing: bool = True
) -> None:
    """An open ring: a dim track, a bright part for the fraction, and a short tick at each end."""
    if backing:
        _backing(painter, center, radius + 6)
    rect = QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius)
    pen = QPen(theme.track, width)
    pen.setCapStyle(Qt.FlatCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawArc(rect, ARC_START, ARC_SWEEP)
    fraction = min(max(fraction, 0.0), 1.0)
    if fraction > 0:
        pen.setColor(theme.accent)
        painter.setPen(pen)
        painter.drawArc(rect, ARC_START, int(ARC_SWEEP * fraction))
    end_deg = ARC_START_DEG - ARC_SPAN_DEG
    for degrees, colour in ((ARC_START_DEG, theme.accent), (end_deg, theme.track)):
        painter.setPen(QPen(colour, width + 0.6, Qt.SolidLine, Qt.FlatCap))
        start, stop = _radial(center, radius, degrees, END_TICK_LENGTH, 1.0)
        painter.drawLine(start, stop)
    if theme.ring_ticks:
        _ticks(painter, center, radius + width + 3, fraction, theme)


def _ticks(painter: QPainter, center: QPointF, radius: float, fraction: float, theme: Theme) -> None:
    steps = 20
    for i in range(steps + 1):
        angle = math.radians(ARC_START_DEG - ARC_SPAN_DEG * i / steps)
        outer = radius + (6 if i % 5 == 0 else 3)
        lit = i / steps <= fraction
        painter.setPen(QPen(theme.accent if lit else theme.track, 1.2))
        painter.drawLine(
            QPointF(center.x() + radius * math.cos(angle), center.y() - radius * math.sin(angle)),
            QPointF(center.x() + outer * math.cos(angle), center.y() - outer * math.sin(angle)),
        )


def draw_value_gauge(
    painter: QPainter, center: QPointF, radius: float, fraction: float, label: str, value: str, unit: str, theme: Theme, backing: bool = False
) -> None:
    """Open ring with a label above the value and a unit below, as for SPEED and ALTITUDE.

    Bare arcs on the booster's bar; the ship's bar (`backing`) puts a faint dark disc behind them.
    """
    _arc(painter, center, radius, fraction, theme, theme.ring_width, backing=backing)
    box = QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius)

    small = theme.make_font(theme.gauge_label_px or theme.label_px, theme.label_weight, theme.label_tracking)
    centre_x = box.center().x()
    # The three lines sit close together, as on the overlay: label above the number, unit just below it.
    wide = QRectF(centre_x - radius, 0, 2 * radius, 0)  # a column as wide as the ring, positioned per line below
    draw_text(painter, QRectF(wide.left(), center.y() - radius * 0.575, wide.width(), 20), Qt.AlignHCenter | Qt.AlignTop, label, small, theme.soft)
    value_font = theme.make_font(theme.value_px, theme.clock_weight, 4.2, wide=True)
    draw_text(
        painter,
        QRectF(box.left() - 20, center.y() - 27, box.width() + 40, 52),
        Qt.AlignCenter,
        value,
        value_font,
        theme.text,
        theme.value_embolden,
        theme.digit_xscale,
    )
    draw_text(painter, QRectF(wide.left(), center.y() + radius * 0.29, wide.width(), 20), Qt.AlignHCenter | Qt.AlignTop, unit, small, theme.soft)


def _ring_counts(total: int) -> list[int]:
    """How many engines sit on each ring, innermost first."""
    if total <= 6:
        return [total]
    counts, capacity = [], 1
    while total > 0:
        counts.append(min(capacity, total))
        total -= counts[-1]
        capacity = 6 if capacity == 1 else capacity + 6
    return counts


def _super_heavy_positions() -> list[tuple[float, float]]:
    """33 engines as on the SEP booster seen from below (screen y points down).

    Measured from the user's photo of the booster: a 3-engine centre triangle pointing down,
    a 10-engine middle ring with engines at 3 and 9 o'clock, and 20 outer engines offset by
    half a step from the vertical. Radii are relative to the outer ring.
    """
    outer = 0.92
    points = []
    for degrees in (90, 210, 330):
        a = math.radians(degrees)
        points.append((outer * 0.236 * math.cos(a), outer * 0.236 * math.sin(a)))
    for k in range(10):
        a = math.radians(36 * k)
        points.append((outer * 0.596 * math.cos(a), outer * 0.596 * math.sin(a)))
    for k in range(20):
        a = math.radians(9 + 18 * k)
        points.append((outer * math.cos(a), outer * math.sin(a)))
    return points


def _ship_positions() -> list[tuple[float, float]]:
    """The ship's 6 engines seen from below (screen y points down), measured from a picture of it.

    Three small engines in a triangle at the centre, then three large ones around them: upper left, upper right
    and straight down. The centre three come first, the same inner-rings-first order as the booster.
    """
    centre = [(0.0, -0.20), (-0.16, 0.07), (0.16, 0.07)]
    outer = [(-0.54, -0.32), (0.54, -0.32), (0.0, 0.58)]
    return centre + outer


def _engine_dot_scale(total: int, index: int) -> float:
    """How big engine `index` is drawn compared with the usual dot: the ship's three large engines are bigger."""
    if total == 6:
        return 2.6 if index >= 3 else 1.05
    return 1.0


def _engine_positions(total: int) -> list[tuple[float, float]]:
    """Concentric rings of engine positions inside a unit circle."""
    if total <= 0:
        return []
    if total == 33:
        return _super_heavy_positions()
    if total == 6:
        return _ship_positions()
    if total == 1:
        return [(0.0, 0.0)]
    counts = _ring_counts(total)
    points: list[tuple[float, float]] = []
    for ring, count in enumerate(counts):
        if count == 1 and ring == 0:
            points.append((0.0, 0.0))
            continue
        if len(counts) == 1:
            radius = 0.55
        elif counts[0] == 1:
            radius = 0.92 * ring / (len(counts) - 1)
        else:
            radius = 0.2 + 0.72 * ring / (len(counts) - 1)
        offset = -math.pi / 2 if count == 3 else math.pi / count
        for i in range(count):
            angle = 2 * math.pi * i / count + offset
            points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return points


def _mix(a: QColor, b: QColor, amount: float) -> QColor:
    """The colour part way from a to b (alpha too)."""
    amount = min(max(amount, 0.0), 1.0)
    return QColor(
        round(a.red() + (b.red() - a.red()) * amount),
        round(a.green() + (b.green() - a.green()) * amount),
        round(a.blue() + (b.blue() - a.blue()) * amount),
        round(a.alpha() + (b.alpha() - a.alpha()) * amount),
    )


def draw_engine_cluster(
    painter: QPainter,
    center: QPointF,
    radius: float,
    fuel_fraction: float,
    engines_on: int,
    engines_total: int,
    theme: Theme,
    lit: tuple[bool, ...] = (),
    grow: float = 1.0,
    levels: list[float] | None = None,
) -> None:
    """Engine dots inside the current stage's fuel ring. Lit engines are bright, the rest dim.

    `lit` says which dot is which engine; without it the first `engines_on` dots are lit. `grow` (0..1) draws the
    cluster in: the ring sweeps round and the dots swell from nothing. `levels` (0 dim .. 1 lit, per dot) overrides
    `lit`, so a dot can be part way between the two while it fades.
    """
    _arc(painter, center, radius, fuel_fraction * grow, theme, theme.ring_width + 1.2)
    inner_ring = QColor(theme.soft)
    inner_ring.setAlpha(70)
    painter.setPen(QPen(inner_ring, 1.0))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(center, radius * 0.86, radius * 0.86)  # the thin circle round the engine dots
    positions = _engine_positions(engines_total)
    inner = radius * 0.74
    dot = max(2.0, radius * 0.09)
    painter.setPen(Qt.NoPen)
    for i, (ux, uy) in enumerate(positions):
        on = lit[i] if i < len(lit) else i < engines_on
        if levels is not None and i < len(levels):
            painter.setBrush(_mix(theme.dim, theme.text, levels[i]))
        else:
            painter.setBrush(theme.text if on else theme.dim)
        size = dot * _engine_dot_scale(engines_total, i) * grow
        painter.drawEllipse(QPointF(center.x() + ux * inner, center.y() + uy * inner), size, size)


def draw_map_dial(
    painter: QPainter,
    center: QPointF,
    radius: float,
    map_image: QImage | None,
    theme: Theme,
    grow: float = 1.0,
    note: str = "",
) -> None:
    """The map in place of the engine dots: the lit globe with a target-like dot at the vessel, and no fuel ring.

    `map_image` is None when there is no position or no map data; `note` then says why.
    """
    globe = radius * 0.97 * (0.4 + 0.6 * grow)
    face = QRectF(center.x() - globe, center.y() - globe, 2 * globe, 2 * globe)
    if map_image is not None:
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(face, map_image)
        painter.restore()
    else:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 12, 18))
        painter.drawEllipse(face)
        if note:
            font = theme.make_font(theme.gauge_label_px or theme.label_px, theme.label_weight, theme.label_tracking)
            draw_text(painter, QRectF(center.x() - globe, center.y() - 10, 2 * globe, 20), Qt.AlignCenter, note, font, theme.soft)
    if map_image is not None:  # the vessel: a white dot inside a dark ring inside a pale one, readable on land and sea
        pale = QColor(theme.text)
        pale.setAlpha(210)
        painter.setPen(QPen(pale, 1.3))
        painter.setBrush(QColor(0, 0, 0, 215))
        painter.drawEllipse(center, 7.2 * grow, 7.2 * grow)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.text)
        painter.drawEllipse(center, 4.0 * grow, 4.0 * grow)


def draw_attitude_dial(
    painter: QPainter,
    center: QPointF,
    radius: float,
    pitch_deg: float | None,
    theme: Theme,
    rocket_image: QImage | None = None,
) -> None:
    """The attitude globe: a horizon ellipse with north and the compass lines, and the rocket on it.

    `rocket_image` is the 3D model already rendered for the vessel's attitude. Without one (the heading
    is unknown) the flat built-in rocket is drawn leaning by `pitch_deg`, the tilt from vertical.
    With no attitude data at all the globe is drawn without a rocket rather than a guessed orientation.
    """
    _backing(painter, center, radius + 6)
    outline = QColor(theme.soft)
    outline.setAlpha(135)
    painter.setPen(QPen(outline, 1.3))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(center, radius, radius)
    painter.drawEllipse(center, radius, radius * math.sin(math.radians(VIEW_ELEVATION_DEG)))  # the horizon plane

    faint = QColor(outline)
    faint.setAlpha(95)
    painter.setPen(QPen(faint, 1.1))

    def at(heading: float) -> QPointF:
        x, y = compass_point(heading)
        return QPointF(center.x() + x * radius, center.y() - y * radius)

    painter.drawLine(at(0.0), at(180.0))  # north-south
    painter.drawLine(at(90.0), at(270.0))  # east-west

    north_x, north_up = compass_point(0.0)
    label_centre = QPointF(center.x() + north_x * radius * 0.8, center.y() - (north_up + 0.16) * radius)
    painter.setFont(theme.make_font(theme.label_px + 2, theme.label_weight, theme.label_tracking * 0.5))
    painter.setPen(theme.soft)
    painter.drawText(QRectF(label_centre.x() - 12, label_centre.y() - 12, 24, 24), Qt.AlignCenter, "N")

    if pitch_deg is None:
        return
    if rocket_image is not None:
        side = rocket_pixels(radius)
        painter.drawImage(QRectF(center.x() - side / 2, center.y() - side / 2, side, side), rocket_image)
        return
    painter.save()
    painter.translate(center)
    painter.rotate(pitch_deg)
    _draw_rocket(painter, radius * ROCKET_LENGTH, radius * 0.135, theme)
    painter.restore()


def rocket_pixels(radius: float) -> float:
    """Width and height the rendered 3D rocket is drawn at on a dial of this radius."""
    return radius * ROCKET_LENGTH / 0.97  # the renderer leaves a 3 % margin round the model


def _draw_rocket(painter: QPainter, length: float, width: float, theme: Theme) -> None:
    """A built-in two-stage rocket, nose up, centred on the origin: dark ship on a light booster."""
    top, bottom = -length / 2, length / 2
    split = top + length * 0.44  # where the ship ends and the booster begins
    half = width / 2
    painter.setPen(Qt.NoPen)

    booster = QPainterPath()
    booster.addRect(QRectF(-half, split, width, bottom - split))
    painter.fillPath(booster, QColor(228, 232, 236))
    painter.setBrush(QColor(110, 118, 126))
    painter.drawRect(QRectF(-half * 0.9, bottom - length * 0.05, width * 0.9, length * 0.05))  # engine skirt
    painter.setBrush(QColor(60, 66, 72))
    for side in (-1, 1):  # grid fins just below the join
        painter.drawRect(QRectF(side * half - (width * 0.22 if side > 0 else 0), split + length * 0.05, width * 0.22, length * 0.04))

    ship = QPainterPath()
    ship.moveTo(0, top)
    ship.quadTo(half * 1.1, top + length * 0.10, half, top + length * 0.30)
    ship.lineTo(half, split)
    ship.lineTo(-half, split)
    ship.lineTo(-half, top + length * 0.30)
    ship.quadTo(-half * 1.1, top + length * 0.10, 0, top)
    ship_colour = QColor(78, 86, 94)  # dark metal, but light enough to read against the dial's dark disc
    painter.fillPath(ship, ship_colour)
    for side in (-1, 1):  # a flap at the ship's tail and a smaller one forward
        tail = QPainterPath()
        tail.moveTo(side * half, split - length * 0.10)
        tail.lineTo(side * half * 1.9, split - length * 0.01)
        tail.lineTo(side * half, split)
        tail.closeSubpath()
        painter.fillPath(tail, ship_colour)
        fore = QPainterPath()
        fore.moveTo(side * half, top + length * 0.30)
        fore.lineTo(side * half * 1.6, top + length * 0.36)
        fore.lineTo(side * half, top + length * 0.38)
        fore.closeSubpath()
        painter.fillPath(fore, ship_colour)
