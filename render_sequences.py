"""Frame-by-frame sheets of the bar's switching animations, in the style of a contact sheet, into a folder.

    python render_sequences.py [OUT_DIR]        (default: images)

MOCK data on a stand-in background; nothing connects to the game and your saved settings are untouched.
"""

import dataclasses
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from ground_station.branding import DEFAULT_PAD_LABEL
from ground_station.bar import TelemetryBar
from ground_station.fonts import load_bundled_fonts
from ground_station.layout import ARRANGEMENT_FADE
from ground_station.telemetry import mock_pad_telemetry, mock_telemetry

SEP = 143.0
FPS = 6
COLUMNS = 6
PAD_COLUMNS = 2


def telemetry(t: float):
    base = mock_telemetry(t, SEP)
    return dataclasses.replace(base, separated_at=SEP if t >= SEP else None, pitch_deg=40.0)


def transition_frames(bar: TelemetryBar, before_t: float, after_t: float, area: tuple[int, int, int, int], seconds: float) -> list[QImage]:
    bar.set_telemetry(telemetry(before_t))
    bar.grab()
    bar.set_telemetry(telemetry(after_t))
    bar.grab()  # the change of arrangement starts here
    frames = []
    for k in range(int(seconds * FPS) + 1):
        bar._changed_at = time.monotonic() - k / FPS
        frames.append(bar.grab().toImage().copy(*area))
    return frames


def sheet(frames: list[QImage], path: Path, columns: int = COLUMNS) -> None:
    w, h = frames[0].width(), frames[0].height()
    rows = (len(frames) + columns - 1) // columns
    image = QImage(columns * w, rows * h, QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0))
    painter = QPainter(image)
    painter.setPen(QColor(255, 255, 0))
    painter.setFont(QFont("Arial", 9, QFont.Bold))
    for i, frame in enumerate(frames):
        x, y = (i % columns) * w, (i // columns) * h
        painter.drawImage(x, y, frame)
        painter.drawText(x + 4, y + 12, str(i))
    painter.end()
    image.save(str(path))


def main(out_dir: Path) -> None:
    app = QApplication([])
    load_bundled_fonts()
    out_dir.mkdir(parents=True, exist_ok=True)
    bar = TelemetryBar()
    bar.set_background("#05070b"); bar.set_smoothing(False)
    right = (1500, 25, 360, 160)
    left = (60, 25, 360, 160)
    sheet(transition_frames(bar, 130.0, 139.0, right, ARRANGEMENT_FADE), out_dir / "ours_altitude_becomes_engines.png")
    bar = TelemetryBar()
    bar.set_background("#05070b"); bar.set_smoothing(False)
    sheet(transition_frames(bar, 148.0, 155.0, right, ARRANGEMENT_FADE), out_dir / "ours_speed_becomes_3d_dial.png")
    bar = TelemetryBar()
    bar.set_background("#05070b"); bar.set_smoothing(False)
    sheet(transition_frames(bar, 148.0, 155.0, left, ARRANGEMENT_FADE), out_dir / "ours_left_side_booster_and_dial_become_speed_and_altitude.png")
    bar = TelemetryBar()
    bar.set_background("#05070b"); bar.set_smoothing(False)
    bar.set_telemetry(telemetry(142.0))
    bar.grab()
    frames = []
    for k in range(0, 25):  # the 3D dial while the stack separates: four seconds in quarter-second steps
        bar.set_telemetry(telemetry(143.0 + k / 6))
        bar._changed_at -= 10
        frames.append(bar.grab().toImage().copy(230, 25, 175, 160))
    sheet(frames, out_dir / "ours_3d_dial_booster_drops_away.png")
    pad = TelemetryBar(subtitle=DEFAULT_PAD_LABEL)
    pad.set_background("#05070b"); pad.set_smoothing(False); pad.set_view_mode("pad")
    frames = []
    for k in range(0, 24):  # the small pad bar through the made-up static fire: 1 s apart from T-8 to T+15
        pad.set_telemetry(mock_pad_telemetry(-8.0 + k))
        frames.append(pad.grab().toImage())
    sheet(frames, out_dir / "ours_static_fire_small_bar_second_by_second.png", PAD_COLUMNS)
    del app


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "images"))
