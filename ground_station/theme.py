"""Visual themes for the telemetry bar. A theme changes the look only, never the data shown."""

from dataclasses import dataclass, replace

from PySide6.QtGui import QColor, QFont, QFontDatabase


@dataclass(frozen=True)
class Theme:
    name: str
    fonts: tuple[str, ...]
    text: QColor
    soft: QColor
    dim: QColor
    track: QColor
    accent: QColor
    ring_width: float
    ring_ticks: bool
    clock_px: int
    sign_px: int
    value_px: int
    label_px: int
    sub_px: int
    clock_weight: QFont.Weight
    stretch: int  # 100 = normal width; the Starship overlay uses a wide face for numbers
    small_stretch: int  # width for labels and the subtitle
    spacing: float
    scrim_alpha: int
    plate_style: str  # "slanted" edge tabs, "rounded" glass panels, "outline" squared panels, or "none"
    wide_fonts: tuple[str, ...] = ()  # a natively wide face for numbers; if missing, `fonts` is stretched
    label_weight: QFont.Weight = QFont.DemiBold  # labels, milestone names and the subtitle
    label_tracking: float = 0.6  # extra letter spacing on those, in pixels
    plate_rgb: tuple[int, int, int] = (6, 12, 20)  # colour behind the gauges and clock
    plate_alpha: int = 150
    digit_xscale: float = 1.0  # sideways stretch of the clock and gauge numbers, for the overlay's wide digits
    clock_embolden: float = 0.0  # extra stroke, in pixels, to thicken the clock digits between Regular and Bold
    value_embolden: float = 0.0  # the same for the speed and altitude numbers
    gauge_label_px: int = 0  # size of SPEED / KM/H style labels; 0 = same as label_px
    sub_tracking: float = 0.0  # letter spacing of the subtitle; 0 = same as label_tracking

    def tuned(self, font: str = "", accent: str = "", plate_opacity: float | None = None) -> "Theme":
        """This look with the operator's overrides: a chosen font, accent colour and plate opacity."""
        changes: dict = {}
        if font:
            changes.update(fonts=(font,) + self.fonts, wide_fonts=())
        if accent:
            changes["accent"] = QColor(accent)
        if plate_opacity is not None:
            changes["plate_alpha"] = round(255 * plate_opacity)
        return replace(self, **changes) if changes else self

    def family(self, wide: bool = False) -> str:
        available = set(QFontDatabase.families())
        candidates = (self.wide_fonts + self.fonts) if wide else self.fonts
        return next((f for f in candidates if f in available), candidates[-1])

    def make_font(self, px: int, weight: QFont.Weight | None = None, spacing: float = 0.0, wide: bool = False) -> QFont:
        family = self.family(wide)
        font = QFont(family)
        font.setPixelSize(px)
        font.setWeight(weight if weight is not None else QFont.DemiBold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        # Stretching only stands in for a missing face: the preferred fonts are drawn at their own width.
        preferred = (self.wide_fonts or self.fonts)[0] if wide else self.fonts[0]
        stretch = self.stretch if wide else self.small_stretch
        if family != preferred and stretch != 100:
            font.setStretch(stretch)
        return font


STARSHIP = Theme(
    name="A - Starship-accurate",
    fonts=("D-DIN", "Bahnschrift", "Segoe UI", "Arial"),  # bundled D-DIN; Bahnschrift if it failed to load
    wide_fonts=("D-DIN Exp",),
    text=QColor(255, 255, 255),
    soft=QColor(205, 212, 220),
    dim=QColor(255, 255, 255, 100),
    track=QColor(255, 255, 255, 140),
    accent=QColor(255, 255, 255),
    ring_width=2.8,
    ring_ticks=False,
    clock_px=46,  # sizes measured against the overlay at 1920 px wide
    sign_px=32,
    value_px=39,
    label_px=15,
    gauge_label_px=15,
    sub_px=16,
    label_tracking=1.3,
    sub_tracking=1.0,
    clock_embolden=0.7,
    value_embolden=0.4,
    digit_xscale=1.08,
    clock_weight=QFont.Normal,
    stretch=125,
    small_stretch=108,
    spacing=3.3,
    scrim_alpha=170,
    plate_style="slanted",
    plate_rgb=(0, 0, 0),
    plate_alpha=70,
)

GLASS = Theme(
    name="B - Glass",
    fonts=("Segoe UI Semibold", "Segoe UI", "Arial"),
    text=QColor(255, 255, 255),
    soft=QColor(180, 205, 225),
    dim=QColor(255, 255, 255, 60),
    track=QColor(255, 255, 255, 40),
    accent=QColor(90, 200, 255),
    ring_width=5.0,
    ring_ticks=False,
    clock_px=48,
    sign_px=26,
    value_px=34,
    label_px=13,
    sub_px=14,
    clock_weight=QFont.DemiBold,
    stretch=100,
    small_stretch=100,
    spacing=1.0,
    scrim_alpha=60,
    plate_style="rounded",
)

MISSION_CONTROL = Theme(
    name="C - Mission control",
    fonts=("Bahnschrift SemiBold SemiCondensed", "Bahnschrift SemiCondensed", "Consolas"),
    text=QColor(235, 245, 255),
    soft=QColor(150, 175, 195),
    dim=QColor(120, 150, 175, 80),
    track=QColor(120, 150, 175, 70),
    accent=QColor(255, 176, 48),
    ring_width=3.0,
    ring_ticks=True,
    clock_px=48,
    sign_px=24,
    value_px=30,
    label_px=12,
    sub_px=13,
    clock_weight=QFont.DemiBold,
    stretch=100,
    small_stretch=100,
    spacing=2.2,
    scrim_alpha=190,
    plate_style="outline",
)

FOREST = Theme(
    name="D - Forest",
    fonts=("D-DIN", "Bahnschrift", "Segoe UI", "Arial"),
    wide_fonts=("D-DIN Exp",),
    text=QColor(240, 250, 241),
    soft=QColor(184, 214, 190),
    dim=QColor(220, 245, 225, 70),
    track=QColor(176, 220, 188, 55),
    accent=QColor(143, 214, 148),
    ring_width=3.4,
    ring_ticks=False,
    clock_px=42,
    sign_px=28,
    value_px=31,
    label_px=15,
    sub_px=15,
    label_tracking=1.1,
    clock_weight=QFont.Normal,
    stretch=125,
    small_stretch=108,
    spacing=3.5,
    scrim_alpha=130,
    plate_style="rounded",
    plate_rgb=(5, 26, 15),
    plate_alpha=170,
)

THEMES = [STARSHIP, GLASS, MISSION_CONTROL, FOREST]
