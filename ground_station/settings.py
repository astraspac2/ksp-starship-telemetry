"""Operator settings saved between sessions. Qt-free so it can be unit-tested."""

import json
import os
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .branding import DEFAULT_FLIGHT_LABEL, DEFAULT_PAD_LABEL, SETTINGS_FOLDER
from .auto_markers import auto_markers_from_dicts, auto_markers_to_dicts
from .events import DEFAULT_EVENTS, DEFAULT_PAD_EVENTS, events_from_dicts, events_to_dicts
from .units import ALTITUDE_UNITS, SPEED_UNITS, THRUST_UNITS

REFRESH_HZ = (20, 30, 60)
WARP_POLICIES = ("follow", "hold")  # countdown follows game time through time warp, or holds while warping
THEMES = ("A - Starship-accurate", "B - Glass", "C - Mission control", "D - Forest")
PANEL_THEMES = ("aerospace", "forest")
BACKGROUNDS = ("transparent", "solid")
ALTITUDE_MODES = ("surface", "sea")  # above the ground/sea, or above sea level
VIEW_MODES = ("flight", "pad")  # the bar for a flight, or for the pad and a static fire
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def default_path() -> Path:
    base = os.environ.get("APPDATA")
    return (Path(base) if base else Path.home()) / SETTINGS_FOLDER / "settings.json"


@dataclass
class Settings:
    # connection and source
    address: str = "127.0.0.1"
    rpc_port: int = 50000
    stream_port: int = 50001
    source: str = "LIVE"  # LIVE or MOCK
    altitude_mode: str = "surface"
    auto_connect: bool = True  # connect to KSP as soon as the app starts (the reader keeps retrying until the server is up)
    # countdown and timeline
    countdown_seconds: float = 60.0
    subtitle: str = DEFAULT_FLIGHT_LABEL
    pad_subtitle: str = DEFAULT_PAD_LABEL  # the label under the clock while the pad view is shown
    warp_policy: str = "follow"
    events: list = field(default_factory=lambda: events_to_dicts(DEFAULT_EVENTS))
    pad_events: list = field(default_factory=lambda: events_to_dicts(DEFAULT_PAD_EVENTS))  # the pad / static-fire view has its own
    auto_markers: list = field(default_factory=list)  # markers the station added by itself (maneuver nodes, re-entry)
    # HUD
    view_mode: str = "flight"  # "flight", or "pad" for the pad / static-fire bar (always the operator's choice, never automatic)
    show_pill: bool = True
    show_bar: bool = True
    refresh_hz: int = 30
    speed_unit: str = "km/h"
    altitude_unit: str = "auto"
    thrust_unit: str = "auto"
    accent: str = ""  # "" = the look's own accent, else "#RRGGBB"
    panel_opacity: float | None = None  # None = the look's own; else 0..1 for the plates behind the gauges
    hud_scale: float = 1.0
    font: str = ""  # "" = automatic (bundled D-DIN, then system)
    background: str = "transparent"
    background_color: str = "#00FF00"  # chroma-key green for capture software
    on_top: bool = True
    click_through: bool = True
    show_badge: bool = False
    show_map: bool = False  # the map in place of the engine dial
    show_timeline: bool = True
    timeline_nodes: int = 7
    vessel_model: str = ""  # path to an OBJ, STL or glTF/GLB model for the attitude dial; "" = the built-in rocket
    vessel_model_flip: bool = False  # turn the model nose to tail if it came out upside down
    starship_model: bool = True  # the built-in model is the Starship on its booster; off = the plain dummy rocket
    # looks
    theme: str = THEMES[0]
    panel_theme: str = PANEL_THEMES[0]

    @property
    def mission_label(self) -> str:
        """The small text under the clock: the flight's own, or the pad's while the pad view is shown."""
        return self.pad_subtitle if self.view_mode == "pad" else self.subtitle

    def validated(self) -> "Settings":
        """Replace anything out of range with its default so a hand-edited file cannot break the app."""
        defaults = Settings()
        fixed = Settings(**asdict(self))

        def one_of(name: str, allowed) -> None:
            if getattr(fixed, name) not in allowed:
                setattr(fixed, name, getattr(defaults, name))

        def within(name: str, low: float, high: float) -> None:
            value = getattr(fixed, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not (low <= value <= high):
                setattr(fixed, name, getattr(defaults, name))

        def text(name: str) -> None:
            if not isinstance(getattr(fixed, name), str):
                setattr(fixed, name, getattr(defaults, name))

        def flag(name: str) -> None:
            if not isinstance(getattr(fixed, name), bool):
                setattr(fixed, name, getattr(defaults, name))

        fixed.events = events_to_dicts(events_from_dicts(fixed.events)) if isinstance(fixed.events, list) else defaults.events
        fixed.pad_events = events_to_dicts(events_from_dicts(fixed.pad_events)) if isinstance(fixed.pad_events, list) else defaults.pad_events
        fixed.auto_markers = auto_markers_to_dicts(auto_markers_from_dicts(fixed.auto_markers))
        for name, allowed in (
            ("warp_policy", WARP_POLICIES),
            ("theme", THEMES),
            ("panel_theme", PANEL_THEMES),
            ("source", ("LIVE", "MOCK")),
            ("refresh_hz", REFRESH_HZ),
            ("speed_unit", SPEED_UNITS),
            ("altitude_unit", ALTITUDE_UNITS),
            ("thrust_unit", THRUST_UNITS),
            ("view_mode", VIEW_MODES),
            ("altitude_mode", ALTITUDE_MODES),
            ("background", BACKGROUNDS),
        ):
            one_of(name, allowed)
        within("rpc_port", 1, 65535)
        within("stream_port", 1, 65535)
        within("countdown_seconds", 1, 24 * 3600)
        within("hud_scale", 0.5, 2.0)
        within("timeline_nodes", 1, 20)
        for name in ("address", "subtitle", "pad_subtitle", "font", "vessel_model", "accent", "background_color"):
            text(name)
        for name in ("auto_connect", "show_pill", "show_bar", "on_top", "click_through", "show_badge", "show_map", "show_timeline", "vessel_model_flip", "starship_model"):
            flag(name)
        if not fixed.address.strip():
            fixed.address = defaults.address
        if fixed.accent and not _HEX.match(fixed.accent):
            fixed.accent = ""
        if not _HEX.match(fixed.background_color):
            fixed.background_color = defaults.background_color
        if fixed.panel_opacity is not None:
            ok = isinstance(fixed.panel_opacity, (int, float)) and not isinstance(fixed.panel_opacity, bool)
            fixed.panel_opacity = float(fixed.panel_opacity) if ok and 0.0 <= fixed.panel_opacity <= 1.0 else None
        return fixed


def load(path: Path | None = None) -> Settings:
    """Saved settings, or defaults if the file is missing or unreadable."""
    path = path or default_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        known = {f.name: f.type for f in fields(Settings)}
        values = {k: v for k, v in raw.items() if k in known}
        return Settings(**values).validated()
    except (OSError, ValueError, TypeError):
        return Settings()


def save(settings: Settings, path: Path | None = None) -> None:
    """Write atomically so a crash mid-save cannot leave a half-written file."""
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    os.replace(temp, path)
