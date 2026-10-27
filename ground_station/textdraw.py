"""Text drawing with an adjustable weight.

D-DIN comes in Regular and Bold only, and the overlay's numbers sit between the two. Drawing the
glyph outlines and stroking them a little thickens Regular to the in-between weight.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen


def draw_text(
    painter: QPainter,
    rect: QRectF,
    align,
    text: str,
    font: QFont,
    colour: QColor,
    embolden: float = 0.0,
    xscale: float = 1.0,
) -> None:
    """Draw `text` in `rect` like QPainter.drawText, thickened by `embolden` pixels of stroke.

    `xscale` stretches the text sideways about the edge or centre it is aligned to, for a wider face.
    """
    if xscale != 1.0:
        anchor = rect.right() if align & Qt.AlignRight else rect.center().x() if align & Qt.AlignHCenter else rect.left()
        painter.save()
        painter.translate(anchor, 0)
        painter.scale(xscale, 1.0)
        painter.translate(-anchor, 0)
        draw_text(painter, rect, align, text, font, colour, embolden)
        painter.restore()
        return
    painter.setFont(font)
    painter.setPen(colour)
    if embolden <= 0:
        painter.drawText(rect, align, text)
        return
    metrics = QFontMetricsF(font)
    advance = metrics.horizontalAdvance(text)
    if align & Qt.AlignRight:
        x = rect.right() - advance
    elif align & Qt.AlignHCenter:
        x = rect.center().x() - advance / 2
    else:
        x = rect.left()
    if align & Qt.AlignBottom:
        y = rect.bottom() - metrics.descent()
    elif align & Qt.AlignTop:
        y = rect.top() + metrics.ascent()
    else:
        y = rect.center().y() + (metrics.ascent() - metrics.descent()) / 2
    path = QPainterPath()
    path.addText(x, y, font, text)
    painter.fillPath(path, colour)
    painter.strokePath(path, QPen(colour, embolden, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
