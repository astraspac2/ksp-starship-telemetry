"""Live telemetry from KSP through kRPC (read-only: sends no flight commands).

A bare runner with no control panel: the countdown starts the moment it runs. For normal use run
`python run_ground_station.py` instead. Both refuse to run at the same time as another copy.

Start the kRPC server inside KSP first, then:

    python run_live.py                     # countdown from T-60 on KSP's game clock, then mission time
    python run_live.py --countdown 120     # longer countdown
    python run_live.py --shot out.png --wait 3   # connect, wait, save one bar frame and exit

The countdown runs on KSP's game time, so lag or a pause in the game slows or stops it too. Once
KSP reports the vessel has launched, the clock switches to KSP's mission elapsed time. If the
countdown runs out first it holds at T-00:00:01. Without a connection the clock stays frozen.
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
from ground_station.krpc_source import KrpcReader
from ground_station.live import CountdownClock, live_telemetry
from ground_station.pill import PillWidget
from ground_station.single_instance import acquire_or_explain
from ground_station.source import DataSource


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--rpc-port", type=int, default=50000)
    parser.add_argument("--stream-port", type=int, default=50001)
    parser.add_argument("--countdown", type=float, default=60.0, help="seconds of countdown before T-0")
    parser.add_argument("--subtitle", default=DEFAULT_FLIGHT_LABEL)
    parser.add_argument("--shot", help="write a PNG of the bar after --wait seconds and exit")
    parser.add_argument("--wait", type=float, default=3.0)
    args = parser.parse_args()

    lock = None
    if not args.shot:  # a one-off screenshot may run beside the app
        lock = acquire_or_explain()
        if lock is None:
            return 1

    app = QApplication.instance() or QApplication(sys.argv)
    load_bundled_fonts()
    reader = KrpcReader(args.address, args.rpc_port, args.stream_port)
    reader.start()
    clock = CountdownClock(args.countdown)
    clock.start()  # without this the clock waits for a Start button this runner does not have

    if args.shot:
        time.sleep(args.wait)
        status = reader.snapshot()
        tel = live_telemetry(clock, status)
        print(f"state={status.state.value} age={status.age} error={status.error}")
        print(tel)
        bar = TelemetryBar(subtitle=args.subtitle)
        bar.set_telemetry(tel)
        frame = bar.grab().toImage()
        backdrop = QImage(frame.size(), QImage.Format_ARGB32)
        backdrop.fill(QColor(70, 90, 110))
        painter = QPainter(backdrop)
        painter.drawImage(0, 0, frame)
        painter.end()
        backdrop.save(args.shot)
        reader.stop()
        return 0

    pill = PillWidget(subtitle=args.subtitle, source=DataSource.LIVE)
    bar = TelemetryBar(subtitle=args.subtitle)
    screen = app.primaryScreen().availableGeometry()
    pill.move(screen.left() + 24, screen.top() + 24)
    bar.move(screen.left() + (screen.width() - bar.width()) // 2, screen.bottom() - bar.height())

    def tick() -> None:
        tel = live_telemetry(clock, reader.snapshot())
        pill.set_time(tel.t)
        bar.set_telemetry(tel)

    timer = QTimer()
    timer.setInterval(33)
    timer.timeout.connect(tick)
    timer.start()
    pill.show()
    bar.show()
    code = app.exec()
    reader.stop()
    lock.unlock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
