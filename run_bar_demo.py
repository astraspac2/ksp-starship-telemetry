"""Run the full telemetry bar on a mock clock (labeled MOCK DATA).

    python run_bar_demo.py                       # live window, counts down from T-35
    python run_bar_demo.py --start -12           # begin at a different time
    python run_bar_demo.py --shot out.png --at -4   # render one frame to a PNG and exit
"""

import argparse
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from ground_station.branding import DEFAULT_FLIGHT_LABEL
from ground_station.bar import TelemetryBar
from ground_station.fonts import load_bundled_fonts
from ground_station.telemetry import mock_telemetry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=float, default=-35.0, help="mock start time relative to liftoff (s)")
    parser.add_argument("--subtitle", default=DEFAULT_FLIGHT_LABEL)
    parser.add_argument("--shot", help="write a PNG of one frame and exit")
    parser.add_argument("--at", type=float, default=-4.0, help="time for --shot")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    load_bundled_fonts()
    bar = TelemetryBar(subtitle=args.subtitle)

    if args.shot:
        bar.set_telemetry(mock_telemetry(args.at))
        frame = bar.grab().toImage()
        backdrop = QImage(frame.size(), QImage.Format_ARGB32)
        backdrop.fill(QColor(70, 90, 110))  # stand-in footage so the translucent bar is visible
        painter = QPainter(backdrop)
        painter.drawImage(0, 0, frame)
        painter.end()
        backdrop.save(args.shot)
        return 0

    began = time.monotonic()
    timer = QTimer()
    timer.setInterval(33)
    timer.timeout.connect(lambda: bar.set_telemetry(mock_telemetry(args.start + time.monotonic() - began)))
    timer.start()
    bar.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
