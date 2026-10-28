"""The control panel: a tabbed window for a second monitor. It operates the app, never the rocket."""

import math
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor, QFontDatabase, QIcon, QKeySequence, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QInputDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import settings as settings_io
from .bar import TelemetryBar
from .branding import PANEL_TITLE
from .clock import ClockState
from .events import Event, event_status, format_clock_text, parse_clock, sorted_events
from .forest_art import render_forest
from .krpc_source import ConnState
from .mesh import ModelError, load_mesh, normalize
from .mock_game import WARP_RATES
from .session import Session
from .settings import ALTITUDE_MODES, BACKGROUNDS, PANEL_THEMES, REFRESH_HZ, VIEW_MODES, WARP_POLICIES
from .source import DataSource
from .telemetry import mock_telemetry
from .theme import THEMES as BAR_THEMES
from .units import (
    ALTITUDE_LABELS,
    ALTITUDE_UNITS,
    SPEED_LABELS,
    SPEED_UNITS,
    THRUST_LABELS,
    THRUST_UNITS,
    format_altitude,
    format_speed,
)

STYLE_TEMPLATE = """
QWidget { background: @bg@; color: @text@; font-family: 'D-DIN', 'Segoe UI'; font-size: 13px; }
QMainWindow { background: @bg@; }
QMenuBar, QStatusBar { background: @bar_bg@; }
QMenuBar::item:selected, QMenu::item:selected { background: @hover@; }
QMenu { background: @panel@; border: 1px solid @border@; }
QScrollArea { border: none; }
QGroupBox { border: 1px solid @border@; border-radius: 6px; margin-top: 12px; padding: 10px 8px 8px 8px; background: @group_bg@; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: @title@; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget, QTableWidget { background: @panel@; border: 1px solid @border@; border-radius: 3px; padding: 3px 5px; }
QComboBox QAbstractItemView { background: @panel@; selection-background-color: @hover@; }
QTableWidget { gridline-color: @grid@; alternate-background-color: @panel_alt@; }
QHeaderView::section { background: @panel@; color: @title@; border: none; border-bottom: 1px solid @border@; padding: 6px; }
QPushButton, QToolButton { background: @button@; border: 1px solid @button_border@; border-radius: 3px; padding: 5px 14px; }
QPushButton:hover, QToolButton:hover { background: @hover@; }
QPushButton:disabled { color: @disabled@; background: @bar_bg@; border-color: @grid@; }
QToolButton:checked { border: 2px solid @accent@; background: @hover@; }
QPushButton#abort { background: #7a1620; border-color: #b4323f; color: #fff; font-weight: bold; }
QPushButton#abort:hover { background: #961c28; }
QPushButton#abort:disabled { background: #2a1519; border-color: #3a2226; color: #6a5558; }
QTabWidget::pane { border: 1px solid @border@; top: -1px; background: @pane_bg@; }
QTabBar::tab { background: @panel@; padding: 8px 18px; border: 1px solid @border@; border-bottom: none; }
QTabBar::tab:selected { background: @button@; color: @accent@; }
QSlider::groove:horizontal { height: 4px; background: @border@; border-radius: 2px; }
QSlider::handle:horizontal { background: @accent@; width: 14px; margin: -6px 0; border-radius: 7px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 2px; }
QRadioButton::indicator, QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid @button_border@; background: @panel@; }
QCheckBox::indicator { border-radius: 3px; }
QCheckBox::indicator:checked { background: @accent@; border-color: @text@; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: @border@; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""

PALETTES = {
    "aerospace": {
        "bg": "#121a23", "bar_bg": "#0e151d", "text": "#d8e0e8", "border": "#2a3b4e", "panel": "#0f1822",
        "panel_alt": "#111c28", "title": "#8fa3b5", "button": "#172433", "button_border": "#34506b", "hover": "#20344a",
        "accent": "#6cc0ff", "grid": "#1d2a38", "disabled": "#566878", "group_bg": "transparent", "pane_bg": "transparent",
    },
    "forest": {
        "bg": "transparent", "bar_bg": "rgba(3,14,9,215)", "text": "#e6f3e7", "border": "#2f6a4a", "panel": "rgba(4,22,13,210)",
        "panel_alt": "rgba(8,32,19,210)", "title": "#a9d8ae", "button": "rgba(14,52,32,225)", "button_border": "#3f8f62",
        "hover": "rgba(28,88,54,235)", "accent": "#8fd694", "grid": "#1d4a33", "disabled": "#5f8a6c",
        "group_bg": "rgba(3,16,10,150)", "pane_bg": "rgba(3,14,9,120)",
    },
}
PANEL_THEME_LABELS = {"aerospace": "Aerospace dark", "forest": "Forest at dusk"}
ACCENT_SWATCHES = [("Moss", "#8FD694"), ("Ice", "#5CB6FF"), ("Amber", "#FFB030"), ("Rose", "#FF7A90"), ("White", "#FFFFFF")]


def build_style(panel_theme: str) -> str:
    sheet = STYLE_TEMPLATE
    for key, value in PALETTES.get(panel_theme, PALETTES["aerospace"]).items():
        sheet = sheet.replace(f"@{key}@", value)
    return sheet


GREEN, AMBER, RED, GREY = "#3ddc84", "#ffb030", "#ff5148", "#6b7a88"
WARP_LABELS = ["Follow game time through time warp (default)", "Hold the countdown during time warp"]
ALTITUDE_MODE_LABELS = {
    "surface": "Surface altitude (above ground/sea, whichever is closer)",
    "sea": "Altitude above sea level",
}
BACKGROUND_LABELS = {"transparent": "Transparent (per-pixel alpha)", "solid": "Solid colour (for chroma-key capture)"}
STATE_NAMES = {
    ClockState.IDLE: "STANDBY",
    ClockState.RUNNING: "COUNTING",
    ClockState.HELD: "HOLD",
    ClockState.ABORTED: "ABORTED",
}
COL_ON, COL_TIME, COL_LABEL, COL_DESC, COL_STATUS = range(5)
AUTO_ON, AUTO_TIME, AUTO_LABEL, AUTO_STATUS = range(4)
AUTOMATIC_FONT = "Automatic (bundled D-DIN, then system)"
VIEW_LABELS = {
    "flight": "Flight - stage 1, stage separation, flight",
    "pad": "Pad / static fire - engines and dial, thrust and throttle",
}
EVENTS_TITLES = {
    "flight": "Timeline events - times are relative to T-0 (T- before liftoff, T+ after)",
    "pad": "Pad / static-fire events - times are relative to T-0 (the ignition command), T+ after it",
}
THUMB_WIDTH = 440  # two look cards side by side must fit the narrowest panel window


def scrolling(page: QWidget) -> QScrollArea:
    """Let a tab scroll when the window is too short for it."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(page)
    return area


class ControlPanel(QMainWindow):
    def __init__(
        self,
        session: Session,
        on_display_changed: Callable[[], None],
        preview_source: Callable[[], QPixmap | None] | None = None,
    ):
        super().__init__()
        self._session = session
        self._on_display_changed = on_display_changed
        self._asking_about_node = False
        self._preview_source = preview_source
        self._syncing = False  # true while widgets are being filled from settings, so that does not re-save them
        self._forest_cache: QPixmap | None = None
        self.setWindowTitle(PANEL_TITLE)
        self.resize(1100, 760)
        self.setMinimumSize(1000, 620)  # the look cards sit two across and need this much room

        central = QWidget()
        root = QVBoxLayout(central)
        root.addWidget(self._build_countdown_box())
        self._tabs = QTabWidget()
        self._tabs.addTab(scrolling(self._build_mission_tab()), "Mission && Timeline")
        self._tabs.addTab(scrolling(self._build_hud_tab()), "HUD")
        self._tabs.addTab(scrolling(self._build_data_tab()), "Data && Test")
        self._tabs.addTab(scrolling(self._build_appearance_tab()), "Appearance")
        self._tabs.addTab(scrolling(self._build_panel_look_tab()), "Panel look")
        self._tabs.addTab(scrolling(self._build_markers_tab()), "Markers")
        root.addWidget(self._tabs, 1)
        self.setCentralWidget(central)
        self._build_menu()
        self.statusBar().showMessage("Ready.")
        self._sync_from_settings()
        self._apply_panel_theme()
        self.refresh()

    def closeEvent(self, event) -> None:
        QApplication.quit()  # the pill and bar are separate windows, so closing the panel must end the app
        super().closeEvent(event)

    # the forest picture behind everything
    def paintEvent(self, event) -> None:
        if self._session.settings.panel_theme == "forest":
            if self._forest_cache is None or self._forest_cache.size() != self.size():
                self._forest_cache = render_forest(self.width(), self.height())
            painter = QPainter(self)
            painter.drawPixmap(0, 0, self._forest_cache)
        else:
            super().paintEvent(event)

    def _apply_panel_theme(self) -> None:
        self.setStyleSheet(build_style(self._session.settings.panel_theme))
        self._forest_cache = None
        self.update()

    # menu
    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        self._view_menu = self.menuBar().addMenu("View")
        self._pill_action = QAction("Show countdown pill", self, checkable=True)
        self._bar_action = QAction("Show telemetry bar", self, checkable=True)
        self._pill_action.triggered.connect(lambda checked: self._show_pill.setChecked(checked))
        self._bar_action.triggered.connect(lambda checked: self._show_bar.setChecked(checked))
        self._map_action = QAction("Show map instead of engine dial", self, checkable=True)
        self._map_action.setShortcut(QKeySequence("M"))
        self._map_action.triggered.connect(lambda checked: self._map_check.setChecked(checked))
        self._pad_action = QAction("Pad / static-fire bar", self, checkable=True)
        self._pad_action.setShortcut(QKeySequence("P"))
        self._pad_action.triggered.connect(
            lambda checked: self._view_mode.setCurrentIndex(VIEW_MODES.index("pad" if checked else "flight"))
        )
        self._view_menu.addAction(self._pill_action)
        self._view_menu.addAction(self._bar_action)
        self._view_menu.addAction(self._map_action)
        self._view_menu.addAction(self._pad_action)

    # countdown header
    def _build_countdown_box(self) -> QGroupBox:
        box = QGroupBox("Countdown")
        layout = QHBoxLayout(box)
        left = QVBoxLayout()
        top = QHBoxLayout()
        self._clock_readout = QLabel("")
        self._clock_readout.setStyleSheet("font-size: 34px; font-weight: bold;")
        self._state_label = QLabel("")
        top.addWidget(self._clock_readout)
        top.addWidget(self._state_label)
        top.addStretch(1)
        left.addLayout(top)
        self._source_label = QLabel("")
        left.addWidget(self._source_label)
        self._readout = QLabel("")  # live numbers, so the panel shows the flight as well as the controls
        left.addWidget(self._readout)
        row = QHBoxLayout()
        self._start_button = QPushButton("Start")
        self._hold_button = QPushButton("Hold")
        self._resume_button = QPushButton("Resume")
        self._reset_button = QPushButton("Reset")
        for button in (self._start_button, self._hold_button, self._resume_button, self._reset_button):
            row.addWidget(button)
        row.addStretch(1)
        left.addLayout(row)
        layout.addLayout(left, 1)

        right = QVBoxLayout()
        self._lock = QCheckBox("BROADCAST LOCK")
        self._lock.setStyleSheet("font-weight: bold;")
        self._lock.setToolTip("Locks every setting and the Start, Resume and Reset buttons. Hold and Abort stay available.")
        self._abort_button = QPushButton("ABORT")
        self._abort_button.setObjectName("abort")
        self._abort_button.setToolTip("Scrubs the countdown on the display. Nothing is sent to KSP.")
        self._abort_button.setMinimumHeight(40)
        right.addWidget(self._lock, 0, Qt.AlignRight)
        right.addStretch(1)
        right.addWidget(self._abort_button)
        layout.addLayout(right)

        self._start_button.clicked.connect(self._session.start_countdown)
        self._hold_button.clicked.connect(self._session.hold_countdown)
        self._resume_button.clicked.connect(self._session.resume_countdown)
        self._reset_button.clicked.connect(self._session.reset_countdown)
        self._abort_button.clicked.connect(self._abort)
        self._lock.toggled.connect(lambda _locked: self.refresh())
        return box

    # tabs
    def _build_mission_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self._subtitle = QLineEdit()
        self._subtitle.editingFinished.connect(self._store_hud)
        self._start_text = QLineEdit()
        self._start_text.setPlaceholderText("T-00:01:00")
        self._start_text.editingFinished.connect(self._store_countdown_start)
        self._warp = QComboBox()
        self._warp.addItems(WARP_LABELS)
        self._warp.currentIndexChanged.connect(self._store_warp)
        form.addRow("Mission label (pill and bar; flight and pad each keep their own)", self._subtitle)
        form.addRow("Countdown starts at", self._start_text)
        form.addRow("Time warp", self._warp)
        layout.addLayout(form)

        self._events_box = box = QGroupBox(EVENTS_TITLES["flight"])
        inner = QVBoxLayout(box)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["On", "Time (T-/T+)", "Label", "Description", "Status"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setMinimumHeight(230)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(COL_ON, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_TIME, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_LABEL, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_DESC, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeToContents)
        self._table.itemChanged.connect(self._table_edited)
        inner.addWidget(self._table, 1)
        buttons = QHBoxLayout()
        for text, handler in (
            ("Add event", self._add_event),
            ("Remove", self._remove_event),
            ("Move up", lambda: self._move_event(-1)),
            ("Move down", lambda: self._move_event(1)),
            ("Sort by time", self._sort_events),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch(1)
        inner.addLayout(buttons)
        hint = QLabel("The timeline always lists enabled events in time order. Untick a row to hide it without deleting it.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8fa3b5;")
        inner.addWidget(hint)

        auto_box = QGroupBox("Automatic markers - added from what KSP reports (flight view only)")
        auto_inner = QVBoxLayout(auto_box)
        self._auto_table = QTableWidget(0, 4)
        self._auto_table.setHorizontalHeaderLabels(["On", "Time (T-/T+)", "Label", "Status"])
        self._auto_table.setAlternatingRowColors(True)
        self._auto_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._auto_table.setSelectionMode(QTableWidget.SingleSelection)
        self._auto_table.setMinimumHeight(230)
        self._auto_table.verticalHeader().setVisible(False)
        auto_header = self._auto_table.horizontalHeader()
        auto_header.setSectionResizeMode(AUTO_ON, QHeaderView.ResizeToContents)
        auto_header.setSectionResizeMode(AUTO_TIME, QHeaderView.ResizeToContents)
        auto_header.setSectionResizeMode(AUTO_LABEL, QHeaderView.Stretch)
        auto_header.setSectionResizeMode(AUTO_STATUS, QHeaderView.ResizeToContents)
        self._auto_table.itemChanged.connect(self._auto_table_edited)
        auto_inner.addWidget(self._auto_table, 1)
        auto_buttons = QHBoxLayout()
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete_auto_marker)
        auto_buttons.addWidget(delete)
        auto_buttons.addStretch(1)
        auto_inner.addLayout(auto_buttons)
        auto_hint = QLabel(
            "Plan a maneuver node in KSP and you are asked to name it; it lands on the timeline when it will happen. "
            "RE-ENTRY appears once the vessel has been above 70 km, and is set when it "
            "comes down through 70 km. Untick a row to hide it, Delete to remove it."
        )
        auto_hint.setWordWrap(True)
        auto_hint.setStyleSheet("color: #8fa3b5;")
        auto_inner.addWidget(auto_hint)

        halves = QHBoxLayout()
        halves.addWidget(box, 1)
        halves.addWidget(auto_box, 1)
        layout.addLayout(halves, 1)
        return page

    def _build_hud_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._build_preview_group("hud"))

        form = QFormLayout()
        self._view_mode = QComboBox()
        self._view_mode.addItems([VIEW_LABELS[m] for m in VIEW_MODES])
        self._view_mode.setToolTip("Always your choice: the bar never switches to or from the pad view by itself.")
        self._view_mode.currentIndexChanged.connect(self._view_mode_changed)
        form.addRow("Bar for", self._view_mode)

        accent_row = QHBoxLayout()
        self._accent_button = QPushButton()
        self._accent_button.clicked.connect(self._pick_accent)
        accent_reset = QPushButton("Reset")
        accent_reset.clicked.connect(lambda: self._set_accent(""))
        accent_row.addWidget(self._accent_button, 1)
        accent_row.addWidget(accent_reset)
        form.addRow("Accent colour", accent_row)

        opacity_row = QHBoxLayout()
        self._opacity = QSlider(Qt.Horizontal)
        self._opacity.setRange(0, 100)
        self._opacity_label = QLabel("")
        self._opacity_label.setMinimumWidth(48)
        opacity_reset = QPushButton("Reset")
        opacity_reset.clicked.connect(self._reset_opacity)
        opacity_row.addWidget(self._opacity, 1)
        opacity_row.addWidget(self._opacity_label)
        opacity_row.addWidget(opacity_reset)
        form.addRow("Panel opacity", opacity_row)
        self._opacity.valueChanged.connect(self._opacity_moved)

        self._scale = QDoubleSpinBox()
        self._scale.setRange(0.5, 2.0)
        self._scale.setSingleStep(0.05)
        self._scale.setDecimals(2)
        self._scale.valueChanged.connect(self._store_hud)
        form.addRow("HUD scale", self._scale)

        self._font = QComboBox()
        self._font.addItem(AUTOMATIC_FONT)
        self._font.addItems(sorted(set(QFontDatabase.families())))
        self._font.currentIndexChanged.connect(self._store_hud)
        form.addRow("Font", self._font)

        background_row = QHBoxLayout()
        self._background = QComboBox()
        self._background.addItems([BACKGROUND_LABELS[b] for b in BACKGROUNDS])
        self._background.currentIndexChanged.connect(self._store_hud)
        self._background_button = QPushButton()
        self._background_button.setFixedWidth(110)
        self._background_button.clicked.connect(self._pick_background_colour)
        background_row.addWidget(self._background, 1)
        background_row.addWidget(self._background_button)
        form.addRow("Background", background_row)

        self._on_top = QCheckBox("Keep the HUD in front of all other windows (recommended)")
        self._click_through = QCheckBox("Click-through: mouse clicks pass through the HUD (untick to drag it)")
        self._badge_check = QCheckBox("Show a small connection badge (top right)")
        self._show_pill = QCheckBox("Show the countdown pill before T-30 s (flight view; the pad bar has none)")
        self._show_bar = QCheckBox("Show the telemetry bar")
        self._timeline_check = QCheckBox("Show the event timeline along the bar")
        self._map_check = QCheckBox("Show the map in place of the engine dial (flight view)")
        for checkbox in (
            self._on_top,
            self._click_through,
            self._badge_check,
            self._show_pill,
            self._show_bar,
            self._timeline_check,
            self._map_check,
        ):
            checkbox.toggled.connect(self._store_hud)
            form.addRow(checkbox)

        self._nodes = QSpinBox()
        self._nodes.setRange(1, 20)
        self._nodes.valueChanged.connect(self._store_hud)
        form.addRow("Timeline nodes", self._nodes)

        self._speed_unit = QComboBox()
        self._speed_unit.addItems([SPEED_LABELS[u] for u in SPEED_UNITS])
        self._altitude_unit = QComboBox()
        self._altitude_unit.addItems([ALTITUDE_LABELS[u] for u in ALTITUDE_UNITS])
        self._thrust_unit = QComboBox()
        self._thrust_unit.addItems([THRUST_LABELS[u] for u in THRUST_UNITS])
        self._refresh_rate = QComboBox()
        self._refresh_rate.addItems([f"{hz} Hz" for hz in REFRESH_HZ])
        for combo in (self._speed_unit, self._altitude_unit, self._thrust_unit, self._refresh_rate):
            combo.currentIndexChanged.connect(self._store_hud)
        form.addRow("Speed unit", self._speed_unit)
        form.addRow("Altitude unit", self._altitude_unit)
        form.addRow("Thrust unit (pad view)", self._thrust_unit)
        form.addRow("Refresh rate", self._refresh_rate)

        vessel_row = QHBoxLayout()
        self._vessel_path = QLineEdit()
        self._vessel_path.setReadOnly(True)
        self._vessel_path.setPlaceholderText("Built-in 3D rocket (or choose your own .glb, .gltf, .obj or .stl model)")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_vessel)
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self._set_vessel(""))
        vessel_row.addWidget(self._vessel_path, 1)
        vessel_row.addWidget(browse)
        vessel_row.addWidget(clear)
        form.addRow("3D model", vessel_row)
        self._starship_model = QCheckBox("Show the Starship on its booster (untick for the plain dummy rocket; your own model, if chosen, wins)")
        self._starship_model.toggled.connect(self._starship_model_changed)
        form.addRow(self._starship_model)
        self._model_flip = QCheckBox("Flip the model nose to tail (tick it if the rocket shows upside down)")
        self._model_flip.toggled.connect(self._model_flip_changed)
        form.addRow(self._model_flip)
        self._model_note = QLabel("")
        self._model_note.setWordWrap(True)
        self._model_note.setStyleSheet("color: #8fa3b5;")
        form.addRow(self._model_note)

        layout.addLayout(form)
        toggle = QPushButton("Show / hide HUD window")
        toggle.clicked.connect(lambda: self._show_bar.setChecked(not self._show_bar.isChecked()))
        layout.addWidget(toggle)
        layout.addStretch(1)
        return page

    def _build_preview_group(self, which: str) -> QGroupBox:
        box = QGroupBox("Live preview")
        layout = QVBoxLayout(box)
        label = QLabel("")
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumHeight(80)
        layout.addWidget(label)
        setattr(self, f"_{which}_preview", label)
        return box

    def _build_data_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        source = QGroupBox("Data source")
        form = QFormLayout(source)
        self._source_combo = QComboBox()
        self._source_combo.addItems(["LIVE KSP via kRPC", "MOCK simulator"])
        self._source_combo.currentIndexChanged.connect(self._source_changed)
        form.addRow("Source", self._source_combo)
        self._badge = QLabel("")
        self._badge.setAlignment(Qt.AlignCenter)
        form.addRow(self._badge)
        self._address = QLineEdit()
        self._address.editingFinished.connect(self._store_connection)
        form.addRow("kRPC address", self._address)
        ports = QHBoxLayout()
        self._rpc_port = QSpinBox()
        self._stream_port = QSpinBox()
        for spin in (self._rpc_port, self._stream_port):
            spin.setRange(1, 65535)
            spin.editingFinished.connect(self._store_connection)
        ports.addWidget(QLabel("RPC"))
        ports.addWidget(self._rpc_port)
        ports.addWidget(QLabel("Stream"))
        ports.addWidget(self._stream_port)
        ports.addStretch(1)
        form.addRow("Ports", ports)
        self._altitude_mode = QComboBox()
        self._altitude_mode.addItems([ALTITUDE_MODE_LABELS[m] for m in ALTITUDE_MODES])
        self._altitude_mode.currentIndexChanged.connect(self._altitude_mode_changed)
        form.addRow("Altitude shown", self._altitude_mode)
        self._auto_connect = QCheckBox("Connect to KSP automatically when this app starts")
        self._auto_connect.toggled.connect(self._auto_connect_changed)
        form.addRow("", self._auto_connect)
        buttons = QHBoxLayout()
        self._connect_button = QPushButton("Apply and connect")
        self._connect_button.clicked.connect(self._apply_and_connect)
        self._disconnect_button = QPushButton("Disconnect")
        self._disconnect_button.clicked.connect(self._disconnect)
        buttons.addWidget(self._connect_button, 1)
        buttons.addWidget(self._disconnect_button)
        form.addRow(buttons)
        status_row = QHBoxLayout()
        self._light = QLabel()
        self._light.setFixedSize(14, 14)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        status_row.addWidget(self._light)
        status_row.addWidget(self._status, 1)
        form.addRow("Status", status_row)
        layout.addWidget(source)

        self._mock_group = QGroupBox("Mock simulator - simulate game conditions")
        mock = QFormLayout(self._mock_group)
        self._paused = QCheckBox("Game paused (UT stops)")
        self._paused.toggled.connect(self._mock_changed)
        mock.addRow(self._paused)
        self._warp_rate = QComboBox()
        self._warp_rate.addItems([f"x{int(rate)}" for rate in WARP_RATES])
        self._warp_rate.currentIndexChanged.connect(self._mock_changed)
        mock.addRow("Time warp", self._warp_rate)
        lag_row = QHBoxLayout()
        self._lag_seconds = QDoubleSpinBox()
        self._lag_seconds.setRange(0.5, 60.0)
        self._lag_seconds.setValue(5.0)
        self._lag_seconds.setSuffix(" s")
        self._lag_button = QPushButton("Freeze the simulated game (lag spike)")
        self._lag_button.clicked.connect(lambda: self._session.mock_game.freeze(self._lag_seconds.value()))
        lag_row.addWidget(self._lag_seconds)
        lag_row.addWidget(self._lag_button, 1)
        mock.addRow("Lag spike", lag_row)
        self._link_loss = QCheckBox("Simulate link loss (game keeps running)")
        self._link_loss.toggled.connect(self._mock_changed)
        mock.addRow(self._link_loss)
        jump_row = QHBoxLayout()
        self._jump_back = QPushButton("Jump game time -60 s (quickload)")
        self._jump_forward = QPushButton("Jump game time +120 s")
        self._jump_back.clicked.connect(lambda: self._session.mock_game.jump(-60.0))
        self._jump_forward.clicked.connect(lambda: self._session.mock_game.jump(120.0))
        jump_row.addWidget(self._jump_back, 1)
        jump_row.addWidget(self._jump_forward, 1)
        mock.addRow("UT discontinuity", jump_row)
        layout.addWidget(self._mock_group)
        layout.addStretch(1)
        return page

    def _build_appearance_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._build_preview_group("appearance"))

        looks = QGroupBox("Telemetry bar look - click one to use it")
        grid = QGridLayout(looks)
        self._theme_buttons: dict[str, QToolButton] = {}
        for index, theme in enumerate(BAR_THEMES):
            button = QToolButton()
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setText(theme.name)
            button.setIcon(QIcon(self._theme_thumbnail(theme)))
            button.setIconSize(QSize(THUMB_WIDTH, round(THUMB_WIDTH * 195 / 1920)))
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.clicked.connect(lambda _checked, name=theme.name: self._choose_theme(name))
            self._theme_buttons[theme.name] = button
            grid.addWidget(button, index // 2, index % 2)
        layout.addWidget(looks)

        swatches = QGroupBox("Accent colour - one click, or pick any colour on the HUD tab")
        swatch_row = QHBoxLayout(swatches)
        for name, colour in ACCENT_SWATCHES:
            button = QPushButton(name)
            button.setStyleSheet(f"border: 2px solid {colour}; border-radius: 4px; padding: 8px 16px;")
            button.clicked.connect(lambda _checked, c=colour: self._set_accent(c))
            swatch_row.addWidget(button)
        reset = QPushButton("Default")
        reset.clicked.connect(lambda: self._set_accent(""))
        swatch_row.addWidget(reset)
        layout.addWidget(swatches)
        layout.addStretch(1)
        return page

    def _build_panel_look_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        box = QGroupBox("This control panel's look")
        form = QFormLayout(box)
        self._panel_theme = QComboBox()
        self._panel_theme.addItems([PANEL_THEME_LABELS[p] for p in PANEL_THEMES])
        self._panel_theme.currentIndexChanged.connect(self._store_panel_theme)
        form.addRow("Theme", self._panel_theme)
        note = QLabel(
            "Aerospace dark is the plain mission-control look. Forest at dusk puts a painted pine forest behind the "
            "controls: moonlight, mist and fireflies. It changes only how this window looks, not the telemetry."
        )
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(box)
        layout.addStretch(1)
        return page

    def _build_markers_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel("Markers you type here are manual notes. They show on the timeline as squares at the current time.")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self._marker_text = QLineEdit()
        self._marker_text.setPlaceholderText("Marker text, e.g. clamp release")
        add = QPushButton("Add at current time")
        self._marker_text.returnPressed.connect(self._add_marker)
        add.clicked.connect(self._add_marker)
        row.addWidget(self._marker_text, 1)
        row.addWidget(add)
        layout.addLayout(row)
        self._marker_list = QListWidget()
        self._marker_list.setMinimumHeight(220)
        layout.addWidget(self._marker_list, 1)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_marker)
        layout.addWidget(remove)
        return page

    def _theme_thumbnail(self, theme) -> QPixmap:
        """A picture of the bar in this look, mid-flight, on a stand-in sky."""
        bar = TelemetryBar(theme=theme)
        bar.set_telemetry(mock_telemetry(60.0))
        frame = bar.grab()
        sky = QPixmap(frame.size())
        painter = QPainter(sky)
        gradient = QLinearGradient(0, 0, 0, sky.height())
        gradient.setColorAt(0.0, QColor(70, 110, 150))
        gradient.setColorAt(1.0, QColor(30, 50, 80))
        painter.fillRect(sky.rect(), gradient)
        painter.drawPixmap(0, 0, frame)
        painter.end()
        return sky.scaledToWidth(THUMB_WIDTH, Qt.SmoothTransformation)

    # reading settings into the widgets
    def _base_theme(self):
        return next((t for t in BAR_THEMES if t.name == self._session.settings.theme), BAR_THEMES[0])

    def _sync_from_settings(self) -> None:
        self._syncing = True
        try:
            self._fill_widgets()
        finally:
            self._syncing = False

    def _fill_widgets(self) -> None:
        s = self._session.settings
        self._address.setText(s.address)
        self._rpc_port.setValue(s.rpc_port)
        self._stream_port.setValue(s.stream_port)
        self._altitude_mode.setCurrentIndex(ALTITUDE_MODES.index(s.altitude_mode))
        self._auto_connect.setChecked(s.auto_connect)
        self._start_text.setText(format_clock_text(-s.countdown_seconds))
        self._subtitle.setText(s.mission_label)
        self._view_mode.setCurrentIndex(VIEW_MODES.index(s.view_mode))
        self._events_box.setTitle(EVENTS_TITLES[s.view_mode])
        self._warp.setCurrentIndex(WARP_POLICIES.index(s.warp_policy))
        self._panel_theme.setCurrentIndex(PANEL_THEMES.index(s.panel_theme))
        self._speed_unit.setCurrentIndex(SPEED_UNITS.index(s.speed_unit))
        self._altitude_unit.setCurrentIndex(ALTITUDE_UNITS.index(s.altitude_unit))
        self._thrust_unit.setCurrentIndex(THRUST_UNITS.index(s.thrust_unit))
        self._refresh_rate.setCurrentIndex(REFRESH_HZ.index(s.refresh_hz))
        self._scale.setValue(s.hud_scale)
        font_index = self._font.findText(s.font) if s.font else 0
        self._font.setCurrentIndex(max(font_index, 0))
        self._background.setCurrentIndex(BACKGROUNDS.index(s.background))
        self._on_top.setChecked(s.on_top)
        self._click_through.setChecked(s.click_through)
        self._badge_check.setChecked(s.show_badge)
        self._map_check.setChecked(s.show_map)
        self._show_pill.setChecked(s.show_pill)
        self._show_bar.setChecked(s.show_bar)
        self._timeline_check.setChecked(s.show_timeline)
        self._nodes.setValue(s.timeline_nodes)
        self._vessel_path.setText(s.vessel_model)
        self._model_flip.setChecked(s.vessel_model_flip)
        self._starship_model.setChecked(s.starship_model)
        for action, value in (
            (self._pill_action, s.show_pill),
            (self._bar_action, s.show_bar),
            (self._map_action, s.show_map),
            (self._pad_action, s.view_mode == "pad"),
        ):
            action.setChecked(value)
        self._source_combo.setCurrentIndex(0 if self._session.source is DataSource.LIVE else 1)
        self._fill_theme_dependent()
        self._fill_table()
        self._fill_auto_table()

    def _fill_theme_dependent(self) -> None:
        """The widgets whose shown value depends on the chosen look (accent, opacity, which card is ticked)."""
        s = self._session.settings
        base = self._base_theme()
        accent = s.accent or base.accent.name().upper()
        self._accent_button.setText(accent + ("" if s.accent else "  (the look's own colour)"))
        text_colour = "#000" if QColor(accent).lightness() > 130 else "#fff"
        self._accent_button.setStyleSheet(f"background: {accent}; color: {text_colour}; font-weight: bold;")
        opacity = s.panel_opacity if s.panel_opacity is not None else base.plate_alpha / 255
        self._opacity.blockSignals(True)
        self._opacity.setValue(round(opacity * 100))
        self._opacity.blockSignals(False)
        self._opacity_label.setText(f"{round(opacity * 100)} %")
        self._background_button.setText(s.background_color.upper())
        self._background_button.setStyleSheet(f"background: {s.background_color}; color: #000; font-weight: bold;")
        self._background_button.setEnabled(s.background == "solid")
        for name, button in self._theme_buttons.items():
            button.setChecked(name == s.theme)

    def _fill_auto_table(self) -> None:
        markers = self._session.auto_markers
        self._auto_table.blockSignals(True)
        self._auto_table.setRowCount(len(markers))
        for row, marker in enumerate(markers):
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            on.setCheckState(Qt.Checked if marker.enabled else Qt.Unchecked)
            self._auto_table.setItem(row, AUTO_ON, on)
            for column, text in ((AUTO_TIME, format_clock_text(marker.time)), (AUTO_STATUS, "")):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self._auto_table.setItem(row, column, item)
            self._auto_table.setItem(row, AUTO_LABEL, QTableWidgetItem(marker.name))
        self._auto_table.blockSignals(False)
        self._refresh_auto_status()

    def _fill_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._session.events))
        for row, event in enumerate(self._session.events):
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            on.setCheckState(Qt.Checked if event.enabled else Qt.Unchecked)
            self._table.setItem(row, COL_ON, on)
            self._table.setItem(row, COL_TIME, QTableWidgetItem(format_clock_text(event.time)))
            self._table.setItem(row, COL_LABEL, QTableWidgetItem(event.label))
            self._table.setItem(row, COL_DESC, QTableWidgetItem(event.description))
            status = QTableWidgetItem("")
            status.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self._table.setItem(row, COL_STATUS, status)
        self._table.blockSignals(False)

    # saving
    def _save(self) -> None:
        try:
            settings_io.save(self._session.settings)
            self.statusBar().showMessage("Settings saved.", 3000)
        except OSError as exc:
            self.statusBar().showMessage(f"Could not save settings: {exc}")

    def _store_connection(self) -> None:
        if self._syncing:
            return
        s = self._session.settings
        s.address = self._address.text().strip() or s.address
        s.rpc_port = self._rpc_port.value()
        s.stream_port = self._stream_port.value()
        self._save()

    def _store_countdown_start(self) -> None:
        if self._syncing:
            return
        seconds = parse_clock(self._start_text.text())
        if seconds is None or seconds >= 0:
            self.statusBar().showMessage("Countdown start must be a time before liftoff, like T-00:01:00.")
        else:
            self._session.set_countdown_seconds(-seconds)
            self._save()
        self._start_text.setText(format_clock_text(-self._session.settings.countdown_seconds))

    def _store_warp(self, *_args) -> None:
        if self._syncing:
            return
        self._session.set_warp_policy(WARP_POLICIES[self._warp.currentIndex()])
        self._save()

    def _store_hud(self, *_args) -> None:
        """Read every HUD control into the settings, save, and tell the display windows."""
        if self._syncing:
            return
        s = self._session.settings
        label = self._subtitle.text().strip()
        if label:
            if s.view_mode == "pad":
                s.pad_subtitle = label
            else:
                s.subtitle = label
        s.speed_unit = SPEED_UNITS[self._speed_unit.currentIndex()]
        s.altitude_unit = ALTITUDE_UNITS[self._altitude_unit.currentIndex()]
        s.thrust_unit = THRUST_UNITS[self._thrust_unit.currentIndex()]
        s.refresh_hz = REFRESH_HZ[self._refresh_rate.currentIndex()]
        s.hud_scale = round(self._scale.value(), 2)
        s.font = "" if self._font.currentIndex() == 0 else self._font.currentText()
        s.background = BACKGROUNDS[self._background.currentIndex()]
        s.on_top = self._on_top.isChecked()
        s.click_through = self._click_through.isChecked()
        s.show_badge = self._badge_check.isChecked()
        s.show_map = self._map_check.isChecked()
        s.show_pill = self._show_pill.isChecked()
        s.show_bar = self._show_bar.isChecked()
        s.show_timeline = self._timeline_check.isChecked()
        s.timeline_nodes = self._nodes.value()
        for action, value in (
            (self._pill_action, s.show_pill),
            (self._bar_action, s.show_bar),
            (self._map_action, s.show_map),
            (self._pad_action, s.view_mode == "pad"),
        ):
            action.blockSignals(True)
            action.setChecked(value)
            action.blockSignals(False)
        self._background_button.setEnabled(s.background == "solid")
        self._save()
        self._on_display_changed()

    def _view_mode_changed(self, index: int) -> None:
        """Switch the bar between the flight and the pad / static-fire view; each has its own events and mission label."""
        if self._syncing:
            return
        mode = VIEW_MODES[index]
        s = self._session.settings
        if mode == s.view_mode:
            return
        self._session.set_view_mode(mode)
        self._syncing = True
        try:
            self._subtitle.setText(s.mission_label)
            self._events_box.setTitle(EVENTS_TITLES[mode])
            self._pad_action.setChecked(mode == "pad")
            self._fill_table()
        finally:
            self._syncing = False
        self._save()
        self._on_display_changed()
        self.refresh()

    def _store_panel_theme(self, *_args) -> None:
        if self._syncing:
            return
        self._session.settings.panel_theme = PANEL_THEMES[self._panel_theme.currentIndex()]
        self._apply_panel_theme()
        self._save()

    # colours, opacity, look
    def _choose_color(self, initial: str) -> str | None:
        colour = QColorDialog.getColor(QColor(initial), self, "Choose a colour")
        return colour.name().upper() if colour.isValid() else None

    def _pick_accent(self) -> None:
        s = self._session.settings
        chosen = self._choose_color(s.accent or self._base_theme().accent.name())
        if chosen:
            self._set_accent(chosen)

    def _set_accent(self, colour: str) -> None:
        self._session.settings.accent = colour
        self._fill_theme_dependent()
        self._save()
        self._on_display_changed()

    def _pick_background_colour(self) -> None:
        chosen = self._choose_color(self._session.settings.background_color)
        if chosen:
            self._session.settings.background_color = chosen
            self._fill_theme_dependent()
            self._save()
            self._on_display_changed()

    def _opacity_moved(self, value: int) -> None:
        if self._syncing:
            return
        self._session.settings.panel_opacity = value / 100
        self._opacity_label.setText(f"{value} %")
        self._save()
        self._on_display_changed()

    def _reset_opacity(self) -> None:
        self._session.settings.panel_opacity = None
        self._fill_theme_dependent()
        self._save()
        self._on_display_changed()

    def _choose_theme(self, name: str) -> None:
        self._session.settings.theme = name
        self._fill_theme_dependent()
        self._save()
        self._on_display_changed()

    def _browse_vessel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a 3D model of your rocket", "", "3D models (*.glb *.gltf *.obj *.stl)"
        )
        if path:
            self._set_vessel(path)

    def _set_vessel(self, path: str) -> None:
        """Use this model for the dial. A file that cannot be used is refused with the reason and not saved."""
        s = self._session.settings
        if path:
            try:
                mesh = normalize(load_mesh(path), flip=s.vessel_model_flip)
            except ModelError as exc:
                self.statusBar().showMessage(f"That model could not be used: {exc}")
                return
            self._model_note.setText(
                f"Loaded: {mesh.triangle_count:,} triangles. Heavy models are thinned automatically. Textures are not shown."
            )
        else:
            self._model_note.setText("")
        s.vessel_model = path
        self._vessel_path.setText(path)
        self._save()
        self._on_display_changed()

    def _starship_model_changed(self, shown: bool) -> None:
        if self._syncing:
            return
        self._session.settings.starship_model = shown
        self._save()
        self._on_display_changed()

    def _model_flip_changed(self, flipped: bool) -> None:
        if self._syncing:
            return
        self._session.settings.vessel_model_flip = flipped
        self._save()
        self._on_display_changed()

    # data source and connection
    def _source_changed(self, index: int) -> None:
        if self._syncing:
            return
        self._session.set_source(DataSource.LIVE if index == 0 else DataSource.MOCK)
        self._save()
        self.refresh()

    def _altitude_mode_changed(self, index: int) -> None:
        if self._syncing:
            return
        self._session.set_altitude_mode(ALTITUDE_MODES[index])
        self._save()

    def _auto_connect_changed(self, checked: bool) -> None:
        if self._syncing:
            return
        self._session.settings.auto_connect = checked
        self._save()

    def _apply_and_connect(self) -> None:
        self._store_connection()
        self._session.reconnect()
        self.refresh()

    def _disconnect(self) -> None:
        self._session.disconnect()
        self.refresh()

    def _mock_changed(self, *_args) -> None:
        game = self._session.mock_game
        game.paused = self._paused.isChecked()
        game.warp = WARP_RATES[self._warp_rate.currentIndex()]
        game.link_lost = self._link_loss.isChecked()

    def _confirm_abort(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Abort countdown",
            "Scrub the countdown?\n\nThis only changes the display. Nothing is sent to KSP.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def _abort(self) -> None:
        if self._confirm_abort():
            self._session.abort_countdown()
            self.refresh()

    # timeline events
    def _read_table(self) -> list[Event]:
        events = []
        for row in range(self._table.rowCount()):
            time = parse_clock(self._table.item(row, COL_TIME).text())
            old = self._session.events[row]
            events.append(
                Event(
                    old.time if time is None else time,
                    self._table.item(row, COL_LABEL).text().strip() or old.label,
                    self._table.item(row, COL_DESC).text(),
                    self._table.item(row, COL_ON).checkState() == Qt.Checked,
                )
            )
        return events

    def _commit_events(self, events: list[Event], select: int | None = None) -> None:
        self._session.set_events(events)
        self._fill_table()
        if select is not None and 0 <= select < len(events):
            self._table.selectRow(select)
        self._save()
        self._on_display_changed()

    def _table_edited(self, item: QTableWidgetItem) -> None:
        if self._syncing or item.column() == COL_STATUS:
            return
        if item.column() == COL_TIME and parse_clock(item.text()) is None:
            self.statusBar().showMessage("Time must look like T-00:00:30 or T+00:01:50.")
        self._commit_events(self._read_table(), item.row())

    def _add_event(self) -> None:
        events = list(self._session.events)
        events.append(Event(float(round(self._session.t)), "New event"))
        self._commit_events(events, len(events) - 1)

    def _remove_event(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            events = list(self._session.events)
            del events[row]
            self._commit_events(events, min(row, len(events) - 1))

    def _move_event(self, step: int) -> None:
        row = self._table.currentRow()
        target = row + step
        events = list(self._session.events)
        if row >= 0 and 0 <= target < len(events):
            events[row], events[target] = events[target], events[row]
            self._commit_events(events, target)

    def _sort_events(self) -> None:
        self._commit_events(sorted_events(self._session.events))

    # markers
    def _add_marker(self) -> None:
        if self._session.add_marker(self._marker_text.text()):
            self._marker_text.clear()
            self._refresh_markers()
            self._on_display_changed()

    def _remove_marker(self) -> None:
        row = self._marker_list.currentRow()
        if row >= 0:
            self._session.remove_marker(row)
            self._refresh_markers()
            self._on_display_changed()

    def _refresh_markers(self) -> None:
        self._marker_list.clear()
        for marker in self._session.markers:
            self._marker_list.addItem(f"{format_clock_text(marker.time)}   {marker.name}   [MANUAL]")

    # periodic refresh
    def refresh(self) -> None:
        session = self._session
        live = session.source is DataSource.LIVE
        locked = self._lock.isChecked()
        state = session.clock.state

        self._clock_readout.setText(format_clock_text(session.t))
        name = STATE_NAMES[state]
        if state is ClockState.RUNNING and session.t >= 0:
            name = "LIFTOFF"
        self._state_label.setText(name)
        palette = PALETTES[session.settings.panel_theme]
        colour = {ClockState.ABORTED: RED, ClockState.HELD: AMBER}.get(state, palette["accent"] if name != "STANDBY" else GREY)
        self._state_label.setStyleSheet(f"font-size: 16px; font-weight: bold; padding-top: 12px; color: {colour};")
        self._source_label.setText(self._source_summary())
        self._readout.setText(self._readout_text())

        self._start_button.setEnabled(state is ClockState.IDLE and not locked)
        self._hold_button.setEnabled(state is ClockState.RUNNING)
        self._resume_button.setEnabled(state is ClockState.HELD and not locked)
        self._reset_button.setEnabled(state is not ClockState.IDLE and not locked)
        self._abort_button.setEnabled(state in (ClockState.RUNNING, ClockState.HELD) and session.t < 0)
        self._tabs.setEnabled(not locked)
        self._view_menu.setEnabled(not locked)
        self._start_text.setEnabled(state is ClockState.IDLE)

        light, text = self._connection_summary()
        self._light.setStyleSheet(f"background: {light}; border-radius: 7px;")
        self._status.setText(text)
        self._connect_button.setEnabled(live)
        self._disconnect_button.setEnabled(live and session.connected)
        for widget in (self._address, self._rpc_port, self._stream_port, self._altitude_mode):
            widget.setEnabled(live)
        self._mock_group.setEnabled(not live)
        if live:
            self._badge.setText("LIVE kRPC DATA")
            self._badge.setStyleSheet(f"background: {GREEN}; color: #04140a; font-weight: bold; padding: 5px; border-radius: 3px;")
        else:
            self._badge.setText("MOCK DATA - NOT REAL FLIGHT DATA")
            self._badge.setStyleSheet(f"background: {AMBER}; color: #1a1000; font-weight: bold; padding: 5px; border-radius: 3px;")

        self._refresh_event_status()
        self._refresh_auto_markers()
        self._refresh_previews()
        self._ask_about_node()

    def _refresh_previews(self) -> None:
        if self._preview_source is None:
            return
        label = {1: self._hud_preview, 3: self._appearance_preview}.get(self._tabs.currentIndex())
        if label is None:
            return
        frame = self._preview_source()
        if frame is None or frame.isNull():
            label.setText("The telemetry bar is hidden.")
            return
        sky = QPixmap(frame.size())
        painter = QPainter(sky)
        gradient = QLinearGradient(0, 0, 0, sky.height())
        gradient.setColorAt(0.0, QColor(70, 110, 150))
        gradient.setColorAt(1.0, QColor(30, 50, 80))
        painter.fillRect(sky.rect(), gradient)
        painter.drawPixmap(0, 0, frame)
        painter.end()
        width = max(label.width() - 8, 200)
        label.setPixmap(sky.scaledToWidth(width, Qt.SmoothTransformation))

    def _refresh_auto_markers(self) -> None:
        """The station added, moved or changed a marker by itself: redraw the table, save, and update the bar."""
        if self._session.take_auto_dirty():
            self._fill_auto_table()
            self._save()
            self._on_display_changed()
        else:
            self._refresh_auto_status()

    def _refresh_auto_status(self) -> None:
        t = self._session.t
        self._auto_table.blockSignals(True)
        for row, marker in enumerate(self._session.auto_markers):
            item = self._auto_table.item(row, AUTO_STATUS)
            if item is None:
                continue
            if not marker.enabled:
                text, colour = "hidden", Qt.GlobalColor.gray
            elif t >= marker.time:
                text, colour = "done", Qt.GlobalColor.gray
            else:
                text, colour = f"in {math.ceil(marker.time - t)}s", Qt.GlobalColor.cyan
            if item.text() != text:
                item.setText(text)
            item.setForeground(colour)
            clock = format_clock_text(marker.time)  # follows a maneuver node that is being dragged
            time_item = self._auto_table.item(row, AUTO_TIME)
            if time_item is not None and time_item.text() != clock:
                time_item.setText(clock)
        self._auto_table.blockSignals(False)

    def _ask_about_node(self) -> None:
        """A maneuver node has been planned in KSP: ask what to call it, then put it on the timeline."""
        if self._asking_about_node:
            return
        proposal = self._session.pending_node
        if proposal is None:
            return
        self._asking_about_node = True
        try:
            minutes, seconds = divmod(round(proposal.ahead), 60)
            hours, minutes = divmod(minutes, 60)
            away = f"{hours}h {minutes:02d}m {seconds:02d}s" if hours else f"{minutes}m {seconds:02d}s"
            name, accepted = QInputDialog.getText(
                self,
                "Maneuver node",
                f"A maneuver node is {away} away, at {format_clock_text(proposal.time)}.\n"
                "Name it to put it on the timeline (Cancel to leave it off):",
                text="Maneuver",
            )
            if accepted and name.strip():
                self._session.name_node(name)
            else:
                self._session.skip_node()
        finally:
            self._asking_about_node = False
        self._refresh_auto_markers()

    def _auto_table_edited(self, item: QTableWidgetItem) -> None:
        if self._syncing:
            return
        row = item.row()
        if item.column() == AUTO_ON:
            self._session.set_auto_marker(row, enabled=item.checkState() == Qt.Checked)
        elif item.column() == AUTO_LABEL:
            self._session.set_auto_marker(row, name=item.text())
        self._refresh_auto_markers()

    def _delete_auto_marker(self) -> None:
        row = self._auto_table.currentRow()
        if row >= 0:
            self._session.remove_auto_marker(row)
            self._refresh_auto_markers()

    def _refresh_event_status(self) -> None:
        events, t = self._session.events, self._session.t
        self._table.blockSignals(True)
        for row in range(min(self._table.rowCount(), len(events))):
            item = self._table.item(row, COL_STATUS)
            text = event_status(events, row, t)
            if item.text() != text:
                item.setText(text)
            item.setForeground(Qt.GlobalColor.cyan if text.startswith("NEXT") else Qt.GlobalColor.gray)
        self._table.blockSignals(False)

    def _readout_text(self) -> str:
        tel = self._session.last
        if tel is None or tel.speed_kmh is None or tel.altitude_km is None:
            return "SPEED —    ALTITUDE —    FUEL —    ENGINES —"
        s = self._session.settings
        speed, speed_unit = format_speed(tel.speed_kmh, s.speed_unit)
        altitude, altitude_unit = format_altitude(tel.altitude_km, s.altitude_unit)
        fuel = "—" if tel.fuel_fraction is None else f"{tel.fuel_fraction * 100:.0f} %"
        return f"SPEED {speed} {speed_unit}    ALTITUDE {altitude} {altitude_unit}    FUEL {fuel}    ENGINES {tel.engines_on}/{tel.engines_total}"

    def _source_summary(self) -> str:
        if self._session.source is DataSource.MOCK:
            return f"MOCK DATA   UT {self._session.game_ut():,.1f} s   (no KSP connected)"
        ut = self._session.game_ut()
        status = self._session.reader_status()
        if status.state is ConnState.CONNECTED and ut is not None:
            return f"KSP LIVE   UT {ut:,.1f} s" + ("   (STALE)" if status.stale else "")
        return "KSP LIVE   " + {
            ConnState.DISCONNECTED: "NOT CONNECTED",
            ConnState.CONNECTING: "NO SIGNAL",
            ConnState.LOST: "SIGNAL LOST",
        }.get(status.state, "NO DATA")

    def _connection_summary(self) -> tuple[str, str]:
        s = self._session.settings
        if self._session.source is DataSource.MOCK:
            return GREY, "Mock source: no kRPC connection needed."
        status = self._session.reader_status()
        age = "" if status.age is None else f" - last data {status.age:.1f} s ago"
        if status.state is ConnState.CONNECTED:
            version = f" {status.server_version}" if status.server_version else ""
            line = f"Connected to kRPC{version} at {s.address}:{s.rpc_port}"
            return (AMBER, f"STALE - {line}{age}") if status.stale else (GREEN, f"{line}{age}")
        if status.state is ConnState.CONNECTING:
            return AMBER, f"CONNECTING - {status.error}" if status.error else "CONNECTING"
        if status.state is ConnState.LOST:
            return RED, f"SIGNAL LOST{age} - {status.error}"
        return GREY, "NOT CONNECTED"


def place_on_second_screen(window: QWidget) -> None:
    """Put the window on the second monitor if there is one, otherwise offset on the main screen."""
    screens = QApplication.screens()
    target = screens[1] if len(screens) > 1 else screens[0]
    area = target.availableGeometry()
    window.move(area.left() + 60, area.top() + 60)
