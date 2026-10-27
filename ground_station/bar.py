"""The full telemetry bar (stage 1 layout): timeline, clock, engine cluster, dial, speed, altitude.

Coordinates are in a 1920 x 195 frame measured from the Starship overlay; `set_scale` scales the
whole window.
"""

import math
import time

import numpy as np

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen, QTransform

from .branding import DEFAULT_FLIGHT_LABEL
from .countdown import format_clock
from .earth_map import MapRenderer
from .gauges import draw_attitude_dial, draw_engine_cluster, draw_map_dial, draw_value_gauge, rocket_pixels
from .hud_window import HudWindow
from .layout import BoosterMemory, Layout, fade_progress, layout_for, stage_sep_time, staged
from .mesh import ModelError, builtin_rocket, load_mesh, normalize
from .starship_model import starship_stack
from .render3d import PROGRESS_STEPS, ModelRenderer, body_to_world
from .source import DataSource
from .telemetry import Telemetry
from .textdraw import draw_text
from .theme import STARSHIP, Theme
from .timeline import (
    Milestone,
    bar_state,
    curve_amount,
    milestone_x,
    nearest_milestone,
    panels_state,
    passed_progress,
    sag,
    tilt_degrees,
)
from .units import format_altitude, format_speed, format_thrust

BAR_WIDTH = 1920
BAR_HEIGHT = 195
CENTER_X = BAR_WIDTH / 2
LINE_Y = 49
CLOCK_Y = 102
SUBTITLE_Y = 138
LINE_LEFT, LINE_RIGHT = 430.0, 1450.0
GAUGE_Y = 105.5
GAUGE_RADIUS = 69.5
ENGINE_CENTER_X = 150.5
DIAL_CENTER_X = 316.7
DIAL_RADIUS = 68.0
SPEED_CENTER_X = 1603.0
ALTITUDE_CENTER_X = 1769.3
NOW_TICK_HALF_HEIGHT = 5.4
MARKER_RADIUS = 6.7
LABEL_ABOVE_GAP = 19  # the centre of a milestone name above the line sits this far above it
CLOCK_GROUP_SHIFT = 1.5  # nudges the "T-" and digits to where the overlay puts them
LABEL_BELOW_GAP = 7  # and this far below the line when it hangs underneath
SUBTITLE_INDENT = 7.0
SPEED_FULL_SCALE_KMH = 30000.0
ALTITUDE_FULL_SCALE_KM = 200.0
RISE_DISTANCE = 45.0
SECOND_TRACK_DROP = 22.0  # how far below the timeline its second, fainter track runs once the line is fully bowed
SECOND_TRACK_ALPHA = 48  # how bright the track is at most (0-255); it is meant to sit back, like the side panels
LABEL_TRACK_PAD = 6.0  # clear space the track keeps around a milestone name
SECOND_TRACK_INSET = 90.0  # it starts this far in from the left end of the line
# The pad / static-fire bar is a small window of its own size: engines, clock, thrust and throttle on one rounded plate, with no
# dial and no timeline. It is drawn with the full bar's coordinates, moved up by PAD_TOP, so every gauge looks exactly the same.
PAD_SCALE = 0.75  # the small bar is drawn this much smaller again than the HUD scale says, so it can sit in a corner
PAD_WIDTH = 840
PAD_HEIGHT = 171
PAD_TOP = 20.0
PAD_ENGINE_X = 90.0
PAD_CLOCK_X = 340.0
PAD_THRUST_X = 590.0
PAD_THROTTLE_X = 750.0

MAP_PICTURE_PX = 220  # the map is drawn this big and scaled into the dial
ATTITUDE_EASE_SECONDS = 0.07  # the 3D dial closes about two thirds of the way to a new attitude in this long
ATTITUDE_SNAP_COSINE = 0.34  # a turn of more than about 70 degrees (a new vessel, a reset) is shown at once
ATTITUDE_RESET_SECONDS = 0.5  # after a pause this long (the dial was hidden) it starts again from the real attitude
ATTITUDE_REDRAW_DELTA = 0.0015  # about a tenth of a degree
DOT_FADE_SECONDS = 0.12  # an engine dot closes about two thirds of the way to lit or dim in this long
SEPARATION_ANIMATION_SECONDS = 4.0  # the dial's booster drops away and the ship fills it over this long
BOOSTER_ENGINES = 33  # the booster's dots, drawn dark once it has separated
UPPER_STAGE_ENGINES = 6  # the ship's engines, drawn dark until it is the stage that is flying
# What sits at each position (centre x) in each arrangement. Where the element at a position changes, the old one fades
# out and the new one fades in (an engine cluster also draws itself in); elements that stay put are left alone.
ELEMENTS = {
    Layout.STAGE_1: {ENGINE_CENTER_X: "booster", DIAL_CENTER_X: "dial", SPEED_CENTER_X: "speed", ALTITUDE_CENTER_X: "altitude"},
    Layout.STAGE_SEP: {ENGINE_CENTER_X: "booster", DIAL_CENTER_X: "dial", SPEED_CENTER_X: "speed", ALTITUDE_CENTER_X: "ship_engines"},
    Layout.FLIGHT: {ENGINE_CENTER_X: "speed", DIAL_CENTER_X: "altitude", SPEED_CENTER_X: "dial", ALTITUDE_CENTER_X: "ship_engines"},
    Layout.PAD: {PAD_ENGINE_X: "booster", PAD_THRUST_X: "thrust", PAD_THROTTLE_X: "throttle"},
}
FADE_OUT_SHARE = 0.4  # the first share of a change is the old element going; the rest is the new one arriving

DEFAULT_MILESTONES = [Milestone("LIFTOFF", 0.0), Milestone("MAX Q", 70.0), Milestone("STAGE SEP", 143.0)]


class TelemetryBar(HudWindow):
    def __init__(
        self,
        subtitle: str = DEFAULT_FLIGHT_LABEL,
        milestones: list[Milestone] | None = None,
        theme: Theme = STARSHIP,
    ):
        super().__init__()
        self._subtitle = subtitle
        self._milestones = milestones or DEFAULT_MILESTONES
        self._theme = theme
        self._speed_unit = "km/h"
        self._altitude_unit = "auto"
        self._thrust_unit = "auto"
        self._pad = False  # the pad / static-fire bar instead of the flight bar
        self._scale = 1.0
        self._background: QColor | None = None  # None = transparent
        self._show_badge = False
        self._show_timeline = True
        self._show_map = False  # the map in place of the live engine dial
        self._smoothing = True  # ease the 3D dial and the engine dots between readings (off for exact still frames)
        self._attitude: np.ndarray | None = None  # the orientation the 3D dial is showing, eased toward the real one
        self._attitude_time = 0.0
        self._attitude_drawn: tuple[np.ndarray, int, object] | None = None  # orientation, separation step, picture
        self._dot_levels: dict[str, list[float]] = {}  # how bright each engine dot is now, 0 (dim) to 1 (lit)
        self._dot_time: dict[str, float] = {}
        self._map = MapRenderer(MAP_PICTURE_PX)
        self._timeline_nodes = 7
        self._telemetry: Telemetry | None = None
        self._booster = BoosterMemory()
        self._shown: dict[float, str] | None = None  # what is at each position on screen, and what it is fading away from
        self._previous: dict[float, str] | None = None
        self._previous_arrangement: Layout | None = None
        self._shown_arrangement: Layout | None = None
        self._changed_at = 0.0
        self.model_triangles = 0
        self._renderer: ModelRenderer
        self.set_vessel_model("")  # the built-in rocket until a model is chosen
        self._apply_size()

    def _frame(self) -> tuple[int, int]:
        """The size of the drawing: the full bar's, or the pad / static-fire bar's smaller one."""
        return (PAD_WIDTH, round(PAD_HEIGHT)) if self._pad else (BAR_WIDTH, BAR_HEIGHT)

    def _drawing_scale(self) -> float:
        return self._scale * (PAD_SCALE if self._pad else 1.0)

    def _apply_size(self) -> None:
        width, height = self._frame()
        scale = self._drawing_scale()
        self.resize(round(width * scale), round(height * scale))

    def set_telemetry(self, telemetry: Telemetry) -> None:
        self._telemetry = telemetry
        self.update()

    def set_subtitle(self, text: str) -> None:
        self._subtitle = text
        self.update()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_units(self, speed_unit: str, altitude_unit: str) -> None:
        self._speed_unit, self._altitude_unit = speed_unit, altitude_unit
        self.update()

    def set_view_mode(self, mode: str) -> None:
        """"pad" for the small pad / static-fire bar (engines, clock, thrust and throttle), else the full flight bar."""
        self._pad = mode == "pad"
        self._shown = None  # the new bar is simply there, with no fade from the old one
        self._apply_size()
        self.update()

    def set_thrust_unit(self, unit: str) -> None:
        self._thrust_unit = unit
        self.update()

    def set_milestones(self, milestones: list[Milestone]) -> None:
        self._milestones = milestones or DEFAULT_MILESTONES
        self.update()

    def set_scale(self, scale: float) -> None:
        self._scale = scale
        self._apply_size()
        self.update()

    def set_background(self, colour: str | None) -> None:
        """A solid fill behind everything (for chroma-key capture), or None for a transparent window."""
        self._background = QColor(colour) if colour else None
        self.update()

    def set_badge(self, show: bool) -> None:
        self._show_badge = show
        self.update()

    def set_smoothing(self, enabled: bool) -> None:
        """Turn the easing of the 3D dial and the engine dots off, to draw exact still frames."""
        self._smoothing = enabled
        self._attitude = None
        self._dot_levels.clear()
        self.update()

    def set_show_map(self, show: bool) -> None:
        self._show_map = show
        self.update()

    def set_timeline(self, show: bool, nodes: int) -> None:
        self._show_timeline, self._timeline_nodes = show, nodes
        self.update()

    def set_vessel_model(self, path: str, flip: bool = False, starship: bool = True) -> str | None:
        """Use a 3D model (OBJ, STL, glTF/GLB) for the dial's rocket; "" selects a built-in one.

        The built-in one is the Starship on its booster when `starship` is set, otherwise the plain dummy rocket.
        Returns None on success, or a message saying why the model could not be used, in which case the
        built-in rocket stays in place.
        """
        self._model_path, self._model_flip = path, flip
        error = None
        mesh = starship_stack() if starship else builtin_rocket()
        if path:
            try:
                mesh = normalize(load_mesh(path), flip=flip)
            except ModelError as exc:
                error = str(exc)
        self._renderer = ModelRenderer(mesh, round(rocket_pixels(DIAL_RADIUS)))
        self.model_triangles = mesh.triangle_count
        self.update()
        return error

    def _rocket_image(self, tel: Telemetry):
        """The 3D rocket for this attitude, or None when the heading is unknown (the dial then draws it flat)."""
        if tel.pitch_deg is None or tel.heading_deg is None:
            return None
        separation = 0.0 if tel.separated_at is None else (tel.t - tel.separated_at) / SEPARATION_ANIMATION_SECONDS
        step = round(min(max(separation, 0.0), 1.0) * PROGRESS_STEPS)
        target = body_to_world(90.0 - tel.pitch_deg, tel.heading_deg, tel.roll_deg or 0.0)
        now = time.monotonic()
        shown = target
        if self._smoothing and self._attitude is not None and now - self._attitude_time < ATTITUDE_RESET_SECONDS:
            if float(self._attitude[:, 1] @ target[:, 1]) > ATTITUDE_SNAP_COSINE:  # a small turn: ease toward it
                blend = 1.0 - math.exp(-(now - self._attitude_time) / ATTITUDE_EASE_SECONDS)
                shown = self._attitude + (target - self._attitude) * blend
                nose = shown[:, 1] / np.linalg.norm(shown[:, 1])
                right = shown[:, 0] - nose * float(shown[:, 0] @ nose)
                right /= np.linalg.norm(right)
                shown = np.column_stack([right, nose, np.cross(right, nose)])  # keep it a true rotation
        self._attitude, self._attitude_time = shown, now
        if self._attitude_drawn is not None:
            last, last_step, picture = self._attitude_drawn
            if last_step == step and float(np.abs(last - shown).max()) < ATTITUDE_REDRAW_DELTA:
                return picture  # it has not moved enough to show: keep the picture
        picture = self._renderer.render_matrix(shown, separation)
        self._attitude_drawn = (shown, step, picture)
        return picture

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if self._background is not None:
            painter.fillRect(self.rect(), self._background)
        if self._telemetry is None:
            return
        painter.scale(self._drawing_scale(), self._drawing_scale())
        tel = self._telemetry
        if self._pad:
            self._paint_pad(painter, tel)
            return

        bar = bar_state(tel.t)
        if bar.opacity > 0:
            painter.setOpacity(bar.opacity)
            self._draw_scrim(painter)
            if self._theme.plate_style in ("rounded", "outline"):
                self._block_plate(painter, QRectF(790, 78, 340, 112))
            if self._show_timeline:
                self._draw_timeline(painter, tel.t, curve_amount(tel.altitude_km))
            self._draw_clock(painter, tel)
            if self._show_badge:
                self._draw_badge(painter, tel)

        panels = panels_state(tel.t)
        if panels.opacity > 0:
            painter.setOpacity(panels.opacity)
            painter.translate(0, panels.offset * RISE_DISTANCE)
            self._draw_plates(painter)
            self._draw_panels(painter, tel)

    def _paint_pad(self, painter: QPainter, tel: Telemetry) -> None:
        """The small pad / static-fire bar: one plate, the clock, the engine dial, thrust and throttle. No timeline, no 3D dial.

        Everything is there from the start: no fade in at T-30 and no rising at T-10, as on the flight bar.
        """
        painter.translate(0, -PAD_TOP)
        self._block_plate(painter, QRectF(1, PAD_TOP + 1, PAD_WIDTH - 2, PAD_HEIGHT - 2))
        self._draw_clock(painter, tel, PAD_CLOCK_X)
        if self._show_badge:
            self._draw_badge(painter, tel, PAD_WIDTH, PAD_TOP)
        self._draw_panels(painter, tel)

    def _plate_colour(self) -> QColor:
        r, g, b = self._theme.plate_rgb
        return QColor(r, g, b, self._theme.plate_alpha)

    def _draw_scrim(self, painter: QPainter) -> None:
        gradient = QLinearGradient(0, 0, 0, BAR_HEIGHT)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(1.0, QColor(0, 0, 0, self._theme.scrim_alpha))
        painter.fillRect(QRectF(0, 0, BAR_WIDTH, BAR_HEIGHT), gradient)

    def _draw_plates(self, painter: QPainter) -> None:
        style = self._theme.plate_style
        if style == "slanted":
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._plate_colour())
            left = QPainterPath()
            left.moveTo(0, 18)
            left.lineTo(360, 18)
            left.quadTo(384, 18, 394, 36)
            left.lineTo(540, BAR_HEIGHT)
            left.lineTo(0, BAR_HEIGHT)
            left.closeSubpath()
            painter.drawPath(left)
            right = QPainterPath()
            right.moveTo(BAR_WIDTH, 18)
            right.lineTo(BAR_WIDTH - 360, 18)
            right.quadTo(BAR_WIDTH - 384, 18, BAR_WIDTH - 394, 36)
            right.lineTo(BAR_WIDTH - 540, BAR_HEIGHT)
            right.lineTo(BAR_WIDTH, BAR_HEIGHT)
            right.closeSubpath()
            painter.drawPath(right)
        elif style in ("rounded", "outline"):
            self._block_plate(painter, QRectF(40, 24, 400, 160))
            self._block_plate(painter, QRectF(BAR_WIDTH - 440, 24, 400, 160))

    def _block_plate(self, painter: QPainter, rect: QRectF) -> None:
        outline = self._theme.plate_style == "outline"
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0) if outline else Qt.NoPen)
        painter.setBrush(self._plate_colour())
        radius = 3 if outline else 18
        painter.drawRoundedRect(rect, radius, radius)

    def _draw_timeline(self, painter: QPainter, t: float, curve: float = 0.0) -> None:
        theme = self._theme
        white = QColor(theme.accent)

        half = (LINE_RIGHT - LINE_LEFT) / 2

        def y_at(x: float) -> float:
            return LINE_Y + sag(x, CENTER_X, half, curve)

        def stroke(x0: float, x1: float, pen: QPen, drop: float = 0.0) -> None:
            path = QPainterPath(QPointF(x0, y_at(x0) + drop))
            steps = 48
            for k in range(1, steps + 1):
                x = x0 + (x1 - x0) * k / steps
                path.lineTo(x, y_at(x) + drop)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        clear = QColor(white)
        clear.setAlpha(0)
        if curve > 0 and theme.plate_style == "slanted":
            self._draw_track_plate(painter, y_at, curve)
        past = QLinearGradient(LINE_LEFT, 0, CENTER_X, 0)
        past.setColorAt(0.0, clear)
        past.setColorAt(1.0, white)
        stroke(LINE_LEFT, CENTER_X, QPen(past, 2.0))

        future = QLinearGradient(CENTER_X, 0, LINE_RIGHT, 0)
        faint = QColor(white)
        faint.setAlpha(110)
        future.setColorAt(0.0, faint)
        future.setColorAt(1.0, clear)
        stroke(CENTER_X, LINE_RIGHT, QPen(future, 1.5))

        label_font = theme.make_font(theme.label_px, theme.label_weight, theme.label_tracking)
        painter.setFont(label_font)
        emphasised = nearest_milestone(t, self._milestones)
        label_spots: list[tuple[QRectF, float, float, float]] = []
        shown = sorted(range(len(self._milestones)), key=lambda i: abs(self._milestones[i].time - t))
        shown = set(shown[: self._timeline_nodes])  # only the nodes nearest in time
        for i, milestone in enumerate(self._milestones):
            x = milestone_x(milestone.time, t, CENTER_X)
            if i not in shown or not LINE_LEFT <= x <= LINE_RIGHT:
                continue
            strong = i == emphasised
            y = y_at(x)
            painter.setPen(QPen(theme.text if strong else theme.soft, 1.4))
            painter.setBrush(QColor(10, 20, 30, 190))
            if milestone.manual:  # typed in by the operator: a square, so it is not mistaken for a detected event
                painter.drawRect(QRectF(x - 5.0, y - 5.0, 10.0, 10.0))
            else:
                painter.drawEllipse(QPointF(x, y), MARKER_RADIUS, MARKER_RADIUS)
            done = passed_progress(t, milestone.time)
            if done > 0:  # the clock has passed it: a white fill grows out of the centre, with a ring that fades out
                grow = 1.0 - (1.0 - done) ** 3
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(theme.text))
                if milestone.manual:
                    half_side = 5.0 * grow
                    painter.drawRect(QRectF(x - half_side, y - half_side, 2 * half_side, 2 * half_side))
                else:
                    painter.drawEllipse(QPointF(x, y), MARKER_RADIUS * grow, MARKER_RADIUS * grow)
                if done < 1.0:
                    ring = QColor(theme.text)
                    ring.setAlphaF(0.8 * (1.0 - done))
                    painter.setPen(QPen(ring, 1.4))
                    painter.setBrush(Qt.NoBrush)
                    pulse = MARKER_RADIUS + 9.0 * done
                    painter.drawEllipse(QPointF(x, y), pulse, pulse)
            above = i % 2 == 0
            rect = QRectF(-90, -LABEL_ABOVE_GAP - 11 if above else LABEL_BELOW_GAP, 180, 22)  # 22 tall, relative to the marker
            tilt = tilt_degrees(x, CENTER_X, half, curve)
            name_width = QFontMetricsF(label_font).horizontalAdvance(milestone.name.upper()) + 2.0 * len(milestone.name)
            label_spots.append((QRectF(-name_width / 2, rect.top(), name_width, rect.height()), x, y, tilt))
            painter.save()
            painter.translate(x, y)
            painter.rotate(tilt)  # the name lies along the curve
            painter.setPen(theme.text if strong else theme.soft)
            painter.drawText(rect, Qt.AlignCenter, milestone.name.upper())
            painter.restore()

        if curve > 0:  # as the line bows, a second thin track appears beneath it and follows its curve
            track_left = LINE_LEFT + SECOND_TRACK_INSET
            track = QLinearGradient(track_left, 0, LINE_RIGHT, 0)
            soft = QColor(white)
            soft.setAlpha(round(SECOND_TRACK_ALPHA * min(curve * 2.0, 1.0)))  # it fades in over the first half of the bend
            track.setColorAt(0.0, clear)
            track.setColorAt(0.25, soft)
            track.setColorAt(0.75, soft)
            track.setColorAt(1.0, clear)
            keep_clear = QPainterPath()  # the track gives way to the milestone names rather than running through them
            for rect, x, y, tilt in label_spots:
                spot = QPainterPath()
                spot.addRect(rect.adjusted(-LABEL_TRACK_PAD, -LABEL_TRACK_PAD / 2, LABEL_TRACK_PAD, LABEL_TRACK_PAD / 2))
                keep_clear.addPath(QTransform().translate(x, y).rotate(tilt).map(spot))
            painter.save()
            everything = QPainterPath()
            everything.addRect(QRectF(0, 0, BAR_WIDTH, BAR_HEIGHT))
            painter.setClipPath(everything.subtracted(keep_clear))
            stroke(track_left, LINE_RIGHT, QPen(track, 1.0), SECOND_TRACK_DROP * curve)
            painter.restore()

        painter.setPen(QPen(theme.text, 2.2))
        painter.drawLine(QPointF(CENTER_X, LINE_Y - NOW_TICK_HALF_HEIGHT), QPointF(CENTER_X, LINE_Y + NOW_TICK_HALF_HEIGHT))

    def _draw_track_plate(self, painter: QPainter, y_at, curve: float) -> None:
        """A dark, see-through plate under the bowed timeline, as dark as the side panels, so the clock reads on any sky.

        Its top edge follows the second track; it fades out toward both ends and appears as the line bends.
        """
        drop = SECOND_TRACK_DROP * curve
        path = QPainterPath(QPointF(LINE_LEFT, y_at(LINE_LEFT) + drop))
        steps = 48
        for k in range(1, steps + 1):
            x = LINE_LEFT + (LINE_RIGHT - LINE_LEFT) * k / steps
            path.lineTo(x, y_at(x) + drop)
        path.lineTo(LINE_RIGHT, BAR_HEIGHT)
        path.lineTo(LINE_LEFT, BAR_HEIGHT)
        path.closeSubpath()
        solid = self._plate_colour()
        solid.setAlpha(round(solid.alpha() * min(curve * 2.0, 1.0)))
        clear = QColor(solid)
        clear.setAlpha(0)
        fade = QLinearGradient(LINE_LEFT, 0, LINE_RIGHT, 0)
        fade.setColorAt(0.0, clear)
        fade.setColorAt(0.14, solid)
        fade.setColorAt(0.86, solid)
        fade.setColorAt(1.0, clear)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fade)
        painter.drawPath(path)

    def _draw_clock(self, painter: QPainter, tel: Telemetry, centre_x: float = CENTER_X) -> None:
        theme = self._theme
        sign, clock = format_clock(tel.t)
        sign_font = theme.make_font(theme.sign_px, QFont.Bold, 0.0, wide=True)
        clock_font = theme.make_font(theme.clock_px, theme.clock_weight, theme.spacing, wide=True)
        sign_w = QFontMetricsF(sign_font).horizontalAdvance(sign)
        clock_w = QFontMetricsF(clock_font).horizontalAdvance(clock) * theme.digit_xscale
        gap = 11.0
        left = centre_x + CLOCK_GROUP_SHIFT - (sign_w + gap + clock_w) / 2
        digits_x = left + sign_w + gap

        painter.setFont(sign_font)
        painter.setPen(theme.soft)
        painter.drawText(QRectF(left, CLOCK_Y - 32, sign_w + 4, 64), Qt.AlignVCenter | Qt.AlignLeft, sign)

        draw_text(
            painter,
            QRectF(digits_x, CLOCK_Y - 32, clock_w + 10, 64),
            Qt.AlignVCenter | Qt.AlignLeft,
            clock,
            clock_font,
            theme.text,
            theme.clock_embolden,
            theme.digit_xscale,
        )

        sub_font = theme.make_font(theme.sub_px, theme.label_weight, theme.sub_tracking or theme.label_tracking)
        draw_text(
            painter,
            QRectF(digits_x + SUBTITLE_INDENT, SUBTITLE_Y - 11, 460, 22),
            Qt.AlignVCenter | Qt.AlignLeft,
            self._subtitle.upper(),
            sub_font,
            theme.soft,
        )

        if tel.source is not DataSource.LIVE:
            self._draw_chip(painter, f"{tel.source.value} DATA", QColor(230, 160, 40), digits_x, SUBTITLE_Y + 18)
        elif tel.status:
            self._draw_chip(painter, tel.status, QColor(220, 60, 50), digits_x, SUBTITLE_Y + 18)

    def _draw_chip(self, painter: QPainter, text: str, colour: QColor, x: float, y: float) -> None:
        font = self._theme.make_font(11, QFont.Bold, 1.2)
        painter.setFont(font)
        rect = QRectF(x, y, QFontMetricsF(font).horizontalAdvance(text) + 18, 17)
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(rect, 3, 3)
        painter.setPen(QColor(20, 14, 4) if colour.lightness() > 120 else QColor(255, 255, 255))
        painter.drawText(rect, Qt.AlignCenter, text)

    def _draw_badge(self, painter: QPainter, tel: Telemetry, frame_width: float = BAR_WIDTH, top: float = 0.0) -> None:
        """A small connection badge in the top right corner."""
        if tel.source is not DataSource.LIVE:
            text, colour = "MOCK", QColor(230, 160, 40)
        elif tel.status:
            text, colour = tel.status, QColor(220, 60, 50)
        else:
            text, colour = "LIVE", QColor(61, 220, 132)
        font = self._theme.make_font(12, QFont.Bold, 1.4)
        painter.setFont(font)
        width = QFontMetricsF(font).horizontalAdvance(text) + 30
        rect = QRectF(frame_width - width - 12, top + 4, width, 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 130))
        painter.drawRoundedRect(rect, 10, 10)
        painter.setBrush(colour)
        painter.drawEllipse(QPointF(rect.left() + 12, rect.center().y()), 4.5, 4.5)
        painter.setPen(self._theme.text)
        painter.drawText(rect.adjusted(22, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

    def _draw_panels(self, painter: QPainter, tel: Telemetry) -> None:
        sep_time = stage_sep_time(self._milestones)
        arrangement = Layout.PAD if self._pad else layout_for(tel.t, sep_time, tel.separated_at)  # the pad ignores Stage Sep
        upper_live = False if self._pad else staged(tel.t, tel.separated_at)
        if not upper_live:
            self._booster.record(tel.t, (tel.fuel_fraction or 0.0, tel.engines_on, tel.engines_total, tel.engine_lit))
        booster = self._booster.before(tel.separated_at) if upper_live else None

        now = time.monotonic()
        kinds = self._kinds_for(arrangement, upper_live)
        if kinds != self._shown:  # a new arrangement, or the map switched on or off: fade what changed
            self._previous, self._shown, self._changed_at = self._shown, kinds, now
            self._previous_arrangement, self._shown_arrangement = self._shown_arrangement, arrangement
        progress = fade_progress(now, self._changed_at)
        base = painter.opacity()
        for x, kind in kinds.items():
            old = self._previous.get(x) if self._previous is not None and progress < 1.0 else kind
            if old == kind:
                self._draw_element(painter, tel, kind, x, arrangement, upper_live, booster, 1.0)
            elif progress < FADE_OUT_SHARE:
                painter.setOpacity(base * (1.0 - progress / FADE_OUT_SHARE))
                self._draw_element(painter, tel, old, x, self._previous_arrangement or arrangement, upper_live, booster, 1.0)
            else:
                arriving = (progress - FADE_OUT_SHARE) / (1.0 - FADE_OUT_SHARE)
                painter.setOpacity(base * arriving)
                self._draw_element(painter, tel, kind, x, arrangement, upper_live, booster, arriving)
            painter.setOpacity(base)

    def _levels_for(self, key: str, on: int, total: int, lit: tuple[bool, ...]) -> list[float] | None:
        """How bright each engine dot is right now: each eases toward lit or dim instead of jumping."""
        if not self._smoothing:
            return None
        targets = [1.0 if (lit[i] if i < len(lit) else i < on) else 0.0 for i in range(total)]
        now = time.monotonic()
        levels = self._dot_levels.get(key)
        if levels is None or len(levels) != total:
            levels = list(targets)  # a different cluster, or the first look: start where it should be
        else:
            blend = 1.0 - math.exp(-(now - self._dot_time.get(key, now)) / DOT_FADE_SECONDS)
            levels = [level + (target - level) * blend for level, target in zip(levels, targets)]
        self._dot_levels[key], self._dot_time[key] = levels, now
        return levels

    def _kinds_for(self, arrangement: Layout, upper_live: bool) -> dict[float, str]:
        """What is at each position: the arrangement's dials, with the map standing in for the engine dial that is flying."""
        if arrangement is Layout.PAD:  # nothing is flying, so no map either
            return dict(ELEMENTS[arrangement])
        kinds = {}
        for x, kind in ELEMENTS[arrangement].items():
            flying = (kind == "booster" and not upper_live) or (kind == "ship_engines" and (upper_live or arrangement is Layout.FLIGHT))
            kinds[x] = "map" if self._show_map and flying else kind
        return kinds

    def _draw_map(self, painter: QPainter, tel: Telemetry, centre: QPointF, grow: float) -> None:
        picture, note = None, "NO POSITION"
        if tel.latitude_deg is not None and tel.longitude_deg is not None:
            picture = self._map.render(tel.latitude_deg, tel.longitude_deg)
            if picture is None:
                note = "NO MAP DATA"
        draw_map_dial(painter, centre, GAUGE_RADIUS - 2.5, picture, self._theme, grow, note)

    def _draw_element(
        self,
        painter: QPainter,
        tel: Telemetry,
        kind: str,
        x: float,
        arrangement: Layout,
        upper_live: bool,
        booster: tuple | None,
        grow: float,
    ) -> None:
        """One dial at one position. `grow` (0..1) is how far an engine cluster has drawn itself in."""
        theme = self._theme
        centre = QPointF(x, GAUGE_Y)
        r = GAUGE_RADIUS
        no_data = "—"
        if kind == "map":  # stands in for the engine dial of the stage that is flying, when the operator asks
            self._draw_map(painter, tel, centre, grow)
        elif kind == "booster":
            if upper_live:  # the booster's dial holds what it showed when the stack separated
                fuel, on, total, lit = booster or (0.0, 0, BOOSTER_ENGINES, (False,) * BOOSTER_ENGINES)
            else:
                fuel, on, total, lit = tel.fuel_fraction or 0.0, tel.engines_on, tel.engines_total, tel.engine_lit
            draw_engine_cluster(painter, centre, r - 2.5, fuel, on, total, theme, lit, grow, self._levels_for(kind, on, total, lit))
        elif kind == "ship_engines":
            if upper_live or arrangement is Layout.FLIGHT:
                fuel, on, total, lit = tel.fuel_fraction or 0.0, tel.engines_on, tel.engines_total, tel.engine_lit
            else:  # the ship's own readings are not available until it is the vessel being flown
                fuel, on, total, lit = 0.0, 0, UPPER_STAGE_ENGINES, (False,) * UPPER_STAGE_ENGINES
            draw_engine_cluster(painter, centre, r - 2.5, fuel, on, total, theme, lit, grow, self._levels_for(kind, on, total, lit))
        elif kind == "dial":
            draw_attitude_dial(painter, centre, DIAL_RADIUS, tel.pitch_deg, theme, self._rocket_image(tel))
        elif kind == "speed":
            speed = tel.speed_kmh
            text, label = ("", format_speed(0.0, self._speed_unit)[1]) if speed is None else format_speed(speed, self._speed_unit)
            draw_value_gauge(
                painter, centre, r, 0.0 if speed is None else speed / SPEED_FULL_SCALE_KMH, "SPEED", no_data if speed is None else text, label, theme,
                arrangement is Layout.FLIGHT,
            )
        elif kind == "altitude":
            altitude = tel.altitude_km
            text, label = (
                ("", format_altitude(0.0, self._altitude_unit)[1]) if altitude is None else format_altitude(altitude, self._altitude_unit)
            )
            draw_value_gauge(
                painter,
                centre,
                r,
                0.0 if altitude is None else altitude / ALTITUDE_FULL_SCALE_KM,
                "ALTITUDE",
                no_data if altitude is None else text,
                label,
                theme,
                arrangement is Layout.FLIGHT,
            )
        elif kind == "thrust":
            thrust, full = tel.thrust_n, tel.max_thrust_n
            if thrust is None:  # burning but not known, or no data: say so rather than show a number
                text, label = no_data, format_thrust(0.0, self._thrust_unit, full)[1]
                fraction = 0.0
            else:
                text, label = format_thrust(thrust, self._thrust_unit, full)
                fraction = min(thrust / full, 1.0) if full else 0.0
            draw_value_gauge(painter, centre, r, fraction, "THRUST", text, label, theme, False)
        elif kind == "throttle":
            throttle = tel.throttle
            draw_value_gauge(
                painter, centre, r, 0.0 if throttle is None else min(max(throttle, 0.0), 1.0), "THROTTLE",
                no_data if throttle is None else f"{throttle * 100:.0f}", "%", theme, False,
            )
