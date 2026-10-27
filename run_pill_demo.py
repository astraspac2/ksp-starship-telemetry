"""Run the countdown pill on a mock clock (labeled MOCK DATA).

    python run_pill_demo.py              # live window, counts down from T-40
    python run_pill_demo.py --start -34  # begin at a different time
    python run_pill_demo.py --shot out.png --at -36   # render one frame to a PNG and exit
"""

import argparse
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from ground_station.branding import DEFAULT_FLIGHT_LABEL
from ground_station.fonts import load_bundled_fonts
from ground_station.pill import PillWidget
from ground_station.source import DataSource


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=float, default=-40.0, help="mock start time relative to liftoff (s)")
    parser.add_argument("--subtitle", default=DEFAULT_FLIGHT_LABEL)
    parser.add_argument("--shot", help="write a PNG of one frame and exit")
    parser.add_argument("--at", type=float, default=-36.0, help="time for --shot")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    load_bundled_fonts()
    pill = PillWidget(subtitle=args.subtitle, source=DataSource.MOCK)

    if args.shot:
        pill.set_time(args.at)
        frame = pill.grab().toImage()
        backdrop = QImage(frame.size(), QImage.Format_ARGB32)
        backdrop.fill(QColor(48, 96, 140))  # stand-in sky so the translucent pill is visible
        painter = QPainter(backdrop)
        painter.drawImage(0, 0, frame)
        painter.end()
        backdrop.save(args.shot)
        return 0

    began = time.monotonic()
    timer = QTimer()
    timer.setInterval(33)
    timer.timeout.connect(lambda: pill.set_time(args.start + time.monotonic() - began))
    timer.start()
    pill.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
