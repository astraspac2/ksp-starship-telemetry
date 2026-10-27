"""Render every theme at the same moments onto a stand-in sky, stacked for side-by-side comparison.

    python render_designs.py OUT_DIR
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication

from ground_station.bar import BAR_HEIGHT, BAR_WIDTH, TelemetryBar
from ground_station.fonts import load_bundled_fonts
from ground_station.telemetry import mock_telemetry
from ground_station.theme import THEMES

MOMENTS = {"countdown_T-19": -19.0, "flight_T+60": 60.0}


def backdrop(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format_ARGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 0, height)
    gradient.setColorAt(0.0, QColor(70, 110, 150))
    gradient.setColorAt(1.0, QColor(30, 50, 80))
    painter.fillRect(0, 0, width, height, gradient)
    painter.end()
    return image


def main(out_dir: Path) -> None:
    app = QApplication([])
    load_bundled_fonts()
    out_dir.mkdir(parents=True, exist_ok=True)
    label_height = 28
    for moment, t in MOMENTS.items():
        sheet = QImage(BAR_WIDTH, len(THEMES) * (BAR_HEIGHT + label_height), QImage.Format_ARGB32)
        sheet.fill(QColor(15, 15, 18))
        painter = QPainter(sheet)
        for row, theme in enumerate(THEMES):
            y = row * (BAR_HEIGHT + label_height)
            painter.setPen(QColor(230, 230, 235))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(12, y + 19, theme.name)
            bar = TelemetryBar(theme=theme)
            bar.set_telemetry(mock_telemetry(t))
            frame = bar.grab().toImage()
            tile = backdrop(BAR_WIDTH, BAR_HEIGHT)
            tp = QPainter(tile)
            tp.drawImage(0, 0, frame)
            tp.end()
            painter.drawImage(0, y + label_height, tile)
        painter.end()
        sheet.save(str(out_dir / f"designs_{moment}.png"))
    del app


if __name__ == "__main__":
    main(Path(sys.argv[1]))
