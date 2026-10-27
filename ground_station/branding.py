"""The app's name and default labels, in one place so a rename touches only this file."""

APP_NAME = "KSP Starship Telemetry"
APP_TAGLINE = "Starship-style telemetry overlay for Kerbal Space Program"
PANEL_TITLE = f"{APP_NAME} - Mission Control"
SETTINGS_FOLDER = APP_NAME  # inside %APPDATA%
LOCK_NAME = APP_NAME.lower().replace(" ", "-") + ".lock"
KRPC_CLIENT_NAME = APP_NAME

DEFAULT_FLIGHT_LABEL = "FLIGHT 1"  # the small text under the clock, until the operator types their own
DEFAULT_PAD_LABEL = "STATIC FIRE"
