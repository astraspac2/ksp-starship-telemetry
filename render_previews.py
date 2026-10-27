"""Render pictures of the whole app (pill, full bar at several moments, every control-panel tab) into a folder.

    python render_previews.py [OUT_DIR]        (default: previews)

Everything here is MOCK data on a stand-in sky; nothing connects to the game and your saved settings are untouched.
"""

import dataclasses
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication

from ground_station import settings as settings_io
from ground_station.branding import DEFAULT_PAD_LABEL
from ground_station.bar import BAR_HEIGHT, BAR_WIDTH, TelemetryBar
from ground_station.fonts import load_bundled_fonts
from ground_station.panel import ControlPanel
from ground_station.pill import PillWidget
from ground_station.session import Session
from ground_station.settings import Settings
from ground_station.telemetry import mock_pad_telemetry, mock_telemetry

BAR_MOMENTS = {
    "bar_1_countdown_T-19": (-19.0, None),
    "bar_2_liftoff_T+0": (0.0, None),
    "bar_3_climb_T+60": (60.0, None),
    "bar_4_timeline_half_curved_60km": (90.0, 60.0),
    "bar_5_timeline_full_curve_120km": (150.0, 120.0),
    "bar_6_stage_sep_layout_T+140": (140.0, None),
    "bar_7_stage_sep_layout_T+148_upper_stage_live": (148.0, None),
    "bar_8_flight_layout_T+200": (200.0, None),
}
STAGE_SEP_AT = 143.0  # the default Stage Sep marker
PAD_MOMENTS = {  # the small pad / static-fire bar through the made-up burn: before ignition, lighting, full thrust, after shutdown
    "pad_1_all_there_from_the_start_T-90": -90.0,
    "pad_2_before_ignition_T-8": -8.0,
    "pad_3_lighting_T+0.6": 0.6,
    "pad_4_full_thrust_T+6": 6.0,
    "pad_5_after_shutdown_T+12": 12.0,
}
PILL_MOMENTS = {"pill_1_T-60": -60.0, "pill_2_T-10": -10.0}


def sky(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format_ARGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 0, height)
    gradient.setColorAt(0.0, QColor(70, 110, 150))
    gradient.setColorAt(1.0, QColor(20, 35, 60))
    painter.fillRect(0, 0, width, height, gradient)
    painter.end()
    return image


def on_sky(frame: QImage) -> QImage:
    tile = sky(frame.width(), frame.height())
    painter = QPainter(tile)
    painter.drawImage(0, 0, frame)
    painter.end()
    return tile


def main(out_dir: Path) -> None:
    app = QApplication([])
    load_bundled_fonts()
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, t in PILL_MOMENTS.items():
        pill = PillWidget()
        pill.set_time(t)
        on_sky(pill.grab().toImage()).save(str(out_dir / f"{name}.png"))

    bar = TelemetryBar()
    bar.set_smoothing(False)  # exact still frames, not frames caught part way through an ease
    for name, (t, altitude) in BAR_MOMENTS.items():
        tel = mock_telemetry(t, STAGE_SEP_AT)
        tel = dataclasses.replace(tel, separated_at=STAGE_SEP_AT if t >= STAGE_SEP_AT else None)  # as the session reports it
        if altitude is not None:
            tel = dataclasses.replace(tel, altitude_km=altitude)
        bar.set_telemetry(tel)
        on_sky(bar.grab().toImage()).save(str(out_dir / f"{name}.png"))

    pad = TelemetryBar(subtitle=DEFAULT_PAD_LABEL)
    pad.set_smoothing(False)
    pad.set_view_mode("pad")
    for name, t in PAD_MOMENTS.items():
        pad.set_telemetry(mock_pad_telemetry(t))
        on_sky(pad.grab().toImage()).save(str(out_dir / f"{name}.png"))

    with tempfile.TemporaryDirectory() as tmp:
        settings_io.default_path = lambda: Path(tmp) / "settings.json"  # never touch the real saved settings
        session = Session(Settings(), game_time=lambda: 100.0)
        panel = ControlPanel(session, lambda: None, preview_source=lambda: None)
        panel.resize(1100, 760)
        panel.show()
        for index in range(panel._tabs.count()):
            panel._tabs.setCurrentIndex(index)
            app.processEvents()
            label = panel._tabs.tabText(index).replace("&&", "and").replace(" ", "_")
            panel.grab().save(str(out_dir / f"panel_{index + 1}_{label}.png"))
        panel.hide()
        session.shutdown() if hasattr(session, "shutdown") else None
    del app


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "previews"))
