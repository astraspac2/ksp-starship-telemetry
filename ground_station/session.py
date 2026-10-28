"""Everything the control panel operates on: data source, kRPC connection, countdown and markers.

Qt-free so it can be unit-tested. The panel only calls this; the display windows only read from it.
"""

import time
from dataclasses import replace
from typing import Callable

from .auto_markers import AutoMarker, AutoMarkerTracker, NodeProposal, auto_markers_from_dicts, auto_markers_to_dicts
from .clock import ClockState, CountdownClock
from .events import Event, events_from_dicts, events_to_dicts
from .krpc_source import ConnState, KrpcReader, ReaderStatus
from .live import live_telemetry
from .mock_game import MockGame
from .settings import Settings
from .source import DataSource
from .telemetry import Telemetry, mock_pad_telemetry, mock_telemetry
from .layout import stage_sep_time
from .separation import SeparationDetector
from .timeline import Milestone

NOT_CONNECTED = ReaderStatus(ConnState.DISCONNECTED, None, None, None)
VIEW_FLIGHT, VIEW_PAD = "flight", "pad"
ABORT_STATUS = "COUNTDOWN ABORTED"


class Session:
    def __init__(
        self,
        settings: Settings,
        reader_factory: Callable[..., KrpcReader] = KrpcReader,
        game_time: Callable[[], float] = time.monotonic,
    ):
        self.settings = settings
        self._reader_factory = reader_factory
        self.mock_game = MockGame(now=game_time)  # the mock source's stand-in for KSP's game clock
        self._reader: KrpcReader | None = None
        self.last: Telemetry | None = None  # what the display was last given, for the panel's readouts
        self.markers: list[Milestone] = []
        self._events = {VIEW_FLIGHT: events_from_dicts(settings.events), VIEW_PAD: events_from_dicts(settings.pad_events)}
        self.source = DataSource.MOCK if settings.source == "MOCK" else DataSource.LIVE
        self.clock = self._new_clock()
        self.t = self.clock.last_t
        self.separation = SeparationDetector()
        self.auto_markers: list[AutoMarker] = auto_markers_from_dicts(settings.auto_markers)  # added by the station itself
        self.auto = AutoMarkerTracker(self.auto_markers)
        self._auto_clock = time.monotonic
        self.auto_dirty = False  # the list changed behind the panel's back; it redraws its table and saves

    @property
    def pad_mode(self) -> bool:
        """Whether the bar is the pad / static-fire one. Only ever the operator's choice, never switched by the data."""
        return self.settings.view_mode == VIEW_PAD

    def set_view_mode(self, mode: str) -> None:
        if mode in (VIEW_FLIGHT, VIEW_PAD):
            self.settings.view_mode = mode
            self.clock.hold_at_zero = self._holds_at_zero()

    def _holds_at_zero(self) -> bool:
        """A flight waits at T-0 for KSP to report the launch. On the pad KSP never does (mission time stays 0 through a
        static fire), so there the clock counts on through zero; a demo source does the same."""
        return self.source is DataSource.LIVE and not self.pad_mode

    @property
    def events(self) -> list[Event]:
        """The planned events of the mode being shown: the flight's, or the pad's own."""
        return self._events[self.settings.view_mode]

    def _new_clock(self) -> CountdownClock:
        return CountdownClock(
            self.settings.countdown_seconds,
            hold_at_zero=self._holds_at_zero(),
            hold_in_warp=self.settings.warp_policy == "hold",
        )

    def set_warp_policy(self, policy: str) -> None:
        self.settings.warp_policy = policy
        self.clock.hold_in_warp = policy == "hold"

    def game_ut(self) -> float | None:
        """Game time shown in the panel: KSP's UT from the newest sample (live), or the mock game's UT."""
        if self.source is DataSource.MOCK:
            return self.mock_game.ut()
        sample = self.reader_status().sample
        return None if sample is None else sample.ut

    # data source and connection
    def set_source(self, source: DataSource) -> None:
        if source is self.source:
            return
        self.source = source
        self.settings.source = source.value
        self.clock = self._new_clock()  # the two sources keep separate clocks, so start clean
        self.separation.reset()
        self.auto.reset()
        self.t = self.clock.last_t

    @property
    def connected(self) -> bool:
        return self._reader is not None

    def connect(self) -> None:
        if self._reader is not None:
            return
        s = self.settings
        self._reader = self._reader_factory(s.address.strip(), s.rpc_port, s.stream_port)
        self._reader.altitude_mode = s.altitude_mode
        self._reader.start()

    def connect_on_start(self) -> None:
        """Connect when the app opens, if that is wanted and the source is the game. The reader retries until KSP is up."""
        if self.settings.auto_connect and self.source is DataSource.LIVE:
            self.connect()

    def disconnect(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader = None

    def reconnect(self) -> None:
        """Apply the current address and ports by connecting afresh."""
        self.disconnect()
        self.connect()

    def set_altitude_mode(self, mode: str) -> None:
        self.settings.altitude_mode = mode
        if self._reader is not None:
            self._reader.altitude_mode = mode

    def reader_status(self) -> ReaderStatus:
        return self._reader.snapshot() if self._reader is not None else NOT_CONNECTED

    # countdown
    def set_countdown_seconds(self, seconds: float) -> None:
        """Re-arm at a new T-minus. Only allowed while the countdown is idle."""
        if self.clock.state is ClockState.IDLE:
            self.settings.countdown_seconds = seconds
            self.clock.reset(seconds)
            self.t = self.clock.last_t

    def start_countdown(self) -> None:
        self.clock.start()

    def hold_countdown(self) -> None:
        self.clock.hold()

    def resume_countdown(self) -> None:
        self.clock.resume()

    def reset_countdown(self) -> None:
        self.clock.reset(self.settings.countdown_seconds)
        self.t = self.clock.last_t
        self.separation.reset()

    def abort_countdown(self) -> None:
        """Scrub the countdown on the display. Nothing is sent to KSP."""
        self.clock.abort()

    # telemetry for the display
    def telemetry(self) -> Telemetry:
        if self.source is DataSource.MOCK:
            sep = stage_sep_time(self.milestones())
            make = mock_pad_telemetry if self.pad_mode else (lambda t: mock_telemetry(t, sep))
            ut = self.mock_game.ut()  # always integrate, so a lost link does not lose game time
            if self.mock_game.link_lost:
                telemetry = replace(make(self.clock.last_t), status="SIGNAL LOST")  # clock freezes, like a lost feed
            else:
                self.t = self.clock.advance(ut, False, 0.0, self.mock_game.warping)
                telemetry = make(self.t)
        else:
            status = self.reader_status()
            telemetry = live_telemetry(self.clock, status)
            self.t = telemetry.t
            self._watch_game(status, telemetry)
        separated = self.separation.update(telemetry.t, telemetry.engines_total, telemetry.status is None)
        telemetry = replace(telemetry, separated_at=None if self.pad_mode else separated)  # the pad has no stage separation
        if self.clock.state is ClockState.ABORTED:
            telemetry = replace(telemetry, status=ABORT_STATUS)
        self.last = telemetry
        return telemetry

    # markers the station adds by itself
    def _watch_game(self, status: ReaderStatus, telemetry: Telemetry) -> None:
        """Hand the newest game readings (nodes, orbit) to the automatic markers, when the feed is healthy."""
        sample = status.sample
        if sample is None or telemetry.status is not None or self.pad_mode:  # nodes and re-entry are for flights
            return
        self.auto.update(
            self._auto_clock(),
            telemetry.t,
            sample.ut,
            sample.node_uts,
            sample.altitude_m / 1000.0,
            sample.reentry_ut,
        )
        if self.auto.take_changed():
            self.sync_auto_markers()

    def sync_auto_markers(self) -> None:
        """Remember the automatic markers in the settings, and tell the panel to redraw them."""
        self.settings.auto_markers = auto_markers_to_dicts(self.auto_markers)
        self.auto_dirty = True

    def take_auto_dirty(self) -> bool:
        dirty, self.auto_dirty = self.auto_dirty, False
        return dirty

    @property
    def pending_node(self) -> NodeProposal | None:
        """A maneuver node the operator has not been asked about yet."""
        return self.auto.pending

    def name_node(self, name: str) -> AutoMarker | None:
        marker = self.auto.accept(name)
        if marker is not None:
            self.sync_auto_markers()
        return marker

    def skip_node(self) -> None:
        self.auto.decline()

    def remove_auto_marker(self, index: int) -> None:
        if 0 <= index < len(self.auto_markers):
            marker = self.auto_markers[index]
            marker.node_ut = None
            del self.auto_markers[index]
            self.sync_auto_markers()

    def set_auto_marker(self, index: int, enabled: bool | None = None, name: str | None = None) -> None:
        if 0 <= index < len(self.auto_markers):
            marker = self.auto_markers[index]
            if enabled is not None:
                marker.enabled = enabled
            if name is not None and name.strip():
                marker.name = name.strip()
            self.sync_auto_markers()

    # planned events
    def set_events(self, events: list[Event]) -> None:
        mode = self.settings.view_mode
        self._events[mode] = list(events)
        saved = events_to_dicts(self._events[mode])
        if mode == VIEW_PAD:
            self.settings.pad_events = saved
        else:
            self.settings.events = saved

    # markers
    def add_marker(self, text: str) -> Milestone | None:
        """Stamp a typed note at the current time. Blank text is ignored."""
        text = text.strip().upper()
        if not text:
            return None
        marker = Milestone(text, round(self.t, 1), manual=True)
        self.markers.append(marker)
        return marker

    def remove_marker(self, index: int) -> None:
        if 0 <= index < len(self.markers):
            del self.markers[index]

    def milestones(self) -> list[Milestone]:
        """Enabled planned events, automatic markers and manual markers, in time order, for the bar's timeline."""
        planned = [Milestone(e.label.upper(), e.time) for e in self.events if e.enabled]
        automatic = [] if self.pad_mode else [Milestone(m.name.upper(), m.time) for m in self.auto_markers if m.enabled]
        return sorted(planned + automatic + self.markers, key=lambda m: m.time)

    def shutdown(self) -> None:
        self.disconnect()
