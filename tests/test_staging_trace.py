import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dataclasses

from PySide6.QtWidgets import QApplication

from ground_station.bar import TelemetryBar
from ground_station.fonts import load_bundled_fonts
from ground_station.layout import BoosterMemory
from ground_station.staging_trace import AFTER_SECONDS, StagingTrace
from ground_station.telemetry import mock_telemetry


def feed(trace, clock, rows):
    for t, total, on in rows:
        clock[0] += 0.1
        trace.add(t, total, on, None, None)


def test_the_trace_writes_what_came_before_and_after_a_change_in_the_engine_count(tmp_path):
    clock = [0.0]
    trace = StagingTrace(tmp_path / "trace.csv", now=lambda: clock[0])
    feed(trace, clock, [(100 + i * 0.1, 33, 33) for i in range(20)])
    assert not (tmp_path / "trace.csv").exists()  # nothing changed yet, nothing written
    feed(trace, clock, [(102.0, 6, 6), (102.1, 6, 6)])
    lines = (tmp_path / "trace.csv").read_text().splitlines()
    assert lines[0].startswith("wall_s,flight_t,engines_total")
    totals = [row.split(",")[2] for row in lines[1:]]
    assert totals[0] == "33" and totals[-1] == "6" and "6" in totals and len(totals) >= 20


def test_the_trace_stops_after_a_while_and_a_new_staging_starts_a_fresh_file(tmp_path):
    clock = [0.0]
    trace = StagingTrace(tmp_path / "trace.csv", now=lambda: clock[0])
    feed(trace, clock, [(10.0, 33, 33), (11.0, 6, 6)])
    clock[0] += AFTER_SECONDS + 1
    feed(trace, clock, [(40.0, 6, 6)])
    assert "40.0" not in (tmp_path / "trace.csv").read_text()
    feed(trace, clock, [(50.0, 3, 3)])
    assert (tmp_path / "trace.csv").read_text().count("wall_s") == 1  # overwritten, not appended


def test_the_pad_and_a_missing_reading_do_not_start_a_trace(tmp_path):
    clock = [0.0]
    trace = StagingTrace(tmp_path / "trace.csv", now=lambda: clock[0])
    feed(trace, clock, [(-30.0, 33, 33), (-20.0, 6, 6), (5.0, 0, 0), (6.0, 33, 33)])
    assert not (tmp_path / "trace.csv").exists()


def test_a_trace_that_cannot_be_written_does_not_raise(tmp_path):
    clock = [0.0]
    trace = StagingTrace(tmp_path / "no" / "such" / "folder" / "trace.csv", now=lambda: clock[0])
    feed(trace, clock, [(10.0, 33, 33), (11.0, 6, 6)])


def test_the_booster_memory_ignores_readings_with_another_engine_count():
    memory = BoosterMemory()
    for t, reading, size in [(100.0, "33 lit", 33), (103.0, "ship flicker", 6), (103.1, "33 again", 33), (104.0, "ship", 6), (104.2, "ship", 6)]:
        memory.record(t, reading, size)
    assert memory.before(105.0) == "33 again"  # the ship's readings, even from just before the separation was confirmed, are skipped
    memory.record(-30.0, "new flight", 33)
    assert memory.before(500.0) == "new flight"


def test_the_booster_dial_keeps_the_booster_when_the_ship_count_shows_up_before_the_separation_is_confirmed():
    app = QApplication.instance() or QApplication([])
    load_bundled_fonts()
    bar = TelemetryBar()
    bar.set_smoothing(False)
    sep_t = 104.3  # the detector confirmed late, after several readings with the ship's six engines
    for t in (103.8, 104.0, 104.2, 104.3, 104.5):
        total = 33 if t < 104.0 else 6
        tel = mock_telemetry(t, 105.0)
        bar.set_telemetry(dataclasses.replace(tel, engines_total=total, engines_on=total, engine_lit=(True,) * total, separated_at=sep_t if t >= sep_t else None))
        bar.grab()
    fuel, on, total, lit = bar._booster.before(sep_t)
    assert total == 33 and len(lit) == 33
