"""KSP Starship Telemetry: the telemetry bar and pill plus a control panel for a second monitor.

    python run_ground_station.py

The panel operates the app only (connection, data source, countdown, display, markers). Nothing
in it sends a command to the rocket. Settings are saved between runs.
"""

from ground_station.app import main

if __name__ == "__main__":
    raise SystemExit(main())
