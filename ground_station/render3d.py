"""A small software 3D renderer for the attitude dial's model.

It turns a mesh into a transparent picture for a given attitude (pitch, heading, roll) as seen on the dial:
a camera slightly above the horizon plane, with north to the upper left. Triangles are sorted back to front
and shaded by a fixed light. Pictures are cached by attitude rounded to a degree, so a slowly changing
attitude costs one render per degree.
"""

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF

from .attitude import VIEW_AZIMUTH_DEG, VIEW_ELEVATION_DEG, nose_direction
from .mesh import Mesh

SUPERSAMPLE = 2
STACK_SPLIT_Y = 0.05  # model height (the model is centred, one unit long) above which the stack is the ship and below it the booster
BOOSTER_BACK = 0.9  # how far (in model lengths) the booster drops away during the separation animation
SHIP_SHARE_OF_DIAL = 0.6  # the lone ship ends up this long compared with the whole stack before separation
PROGRESS_STEPS = 60  # the animation is drawn in this many distinct steps, so its pictures can be cached
CACHE_LIMIT = 90
BASE_COLOUR = np.array([0.86, 0.88, 0.91], dtype=np.float32)
AMBIENT = 0.38
SOLID_LIFT = 0.40  # closed bodies are lit more evenly than flat faces, so a white booster stays white on its shaded side
EDGE_DARKENING = 0.65  # how dark the faces of a closed body get at its silhouette, against 1.0 facing the viewer
LIGHT_VIEW = np.array([-0.45, 0.65, -0.62])  # from the upper left, toward the viewer (view z grows away from it)


def view_matrix() -> np.ndarray:
    """Rotate world (east, north, up) into view space (right, up, away from the viewer)."""
    a, el = math.radians(VIEW_AZIMUTH_DEG), math.radians(VIEW_ELEVATION_DEG)
    return np.array(
        [
            [math.cos(a), math.sin(a), 0.0],
            [-math.sin(a) * math.sin(el), math.cos(a) * math.sin(el), math.cos(el)],
            [-math.sin(a) * math.cos(el), math.cos(a) * math.cos(el), -math.sin(el)],
        ]
    )


def body_to_world(pitch_deg: float, heading_deg: float, roll_deg: float) -> np.ndarray:
    """Columns are the model's right, nose and top axes expressed in world (east, north, up)."""
    nose = np.array(nose_direction(pitch_deg, heading_deg))
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(nose, up)
    if np.linalg.norm(right) < 1e-6:  # standing straight up: the heading says which way "right" is
        h = math.radians(heading_deg)
        right = np.array([math.cos(h), -math.sin(h), 0.0])
    right /= np.linalg.norm(right)
    top = np.cross(right, nose)
    r = math.radians(roll_deg)
    right, top = right * math.cos(r) + top * math.sin(r), top * math.cos(r) - right * math.sin(r)
    return np.column_stack([right, nose, top])


class ModelRenderer:
    def __init__(self, mesh: Mesh, size_px: int):
        """`size_px` is the width and height of the finished picture; the model is one unit long inside it."""
        self._vertices = mesh.vertices.astype(np.float64)
        self._faces = mesh.faces
        split = STACK_SPLIT_Y if mesh.stage_split is None else mesh.stage_split
        self._is_booster = self._vertices[self._faces][:, :, 1].mean(axis=1) < split
        self._ship_centre = (0.5 + split) / 2  # height of the ship's middle
        self._ship_zoom = SHIP_SHARE_OF_DIAL / (0.5 - split)  # scale that settles the ship at its size in the dial
        self._solid, self._outward = self._facing_signs(mesh)
        self._colours = mesh.face_colors if mesh.face_colors is not None else np.tile(BASE_COLOUR, (len(mesh.faces), 1))
        self.size_px = size_px
        self._cache: dict[tuple[int, int, int, int], QImage] = {}
        self._view = view_matrix()

    def _facing_signs(self, mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
        """For the faces of a closed body round the Y axis: +1 or -1 so that the face's winding normal times it points outward.

        Such faces can be skipped whenever they face away from the viewer. Faces whose winding says nothing (no area, or
        edge-on to the axis) are drawn from both sides like any other.
        """
        count = len(mesh.faces)
        solid, outward = np.zeros(count, dtype=bool), np.ones(count)
        if mesh.solid is not None:
            corners = self._vertices[self._faces]
            normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
            radial = corners.mean(axis=1) * np.array([1.0, 0.0, 1.0])
            side = np.einsum("ij,ij->i", normal, radial)
            solid = mesh.solid & (np.abs(side) > 1e-12)
            outward = np.where(side < 0, -1.0, 1.0)
        return solid, outward

    def render(self, pitch_deg: float, heading_deg: float, roll_deg: float = 0.0, separation: float = 0.0) -> QImage:
        """The model for this attitude. `separation` runs 0..1 through the stage separation: the booster drops away
        backwards while the view zooms in on the ship, which is all that is left at 1."""
        key = (round(pitch_deg), round(heading_deg) % 360, round(roll_deg) % 360, round(min(max(separation, 0.0), 1.0) * PROGRESS_STEPS))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        image = self._draw(*key)
        if len(self._cache) >= CACHE_LIMIT:
            self._cache.clear()
        self._cache[key] = image
        return image

    def _stage_triangles(self, step: int) -> tuple[np.ndarray, np.ndarray]:
        """Triangle corners (model space) and which of them to draw, for a step of the separation animation."""
        corners = self._vertices[self._faces]  # (M, 3, 3)
        if step == 0:
            return corners, np.arange(len(self._faces))
        p = step / PROGRESS_STEPS
        eased = p * p * (3.0 - 2.0 * p)
        zoom = 1.0 + (self._ship_zoom - 1.0) * eased
        corners = corners.copy()
        corners[self._is_booster, :, 1] -= BOOSTER_BACK * eased * eased  # drops away, speeding up
        corners[:, :, 1] -= self._ship_centre * eased  # the view settles on the ship
        corners *= zoom
        keep = np.arange(len(self._faces)) if step < PROGRESS_STEPS else np.flatnonzero(~self._is_booster)
        return corners, keep

    def render_matrix(self, axes: np.ndarray, separation: float = 0.0) -> QImage:
        """The model for an exact orientation (columns: right, nose, top in east/north/up), without rounding to a degree.

        For a smoothly turning dial; nothing is cached, so call it only when the orientation has really changed.
        """
        return self._draw_matrix(axes, round(min(max(separation, 0.0), 1.0) * PROGRESS_STEPS))

    def _draw(self, pitch: float, heading: float, roll: float, step: int = 0) -> QImage:
        return self._draw_matrix(body_to_world(pitch, heading, roll), step)

    def _draw_matrix(self, axes: np.ndarray, step: int) -> QImage:
        corners, keep = self._stage_triangles(step)
        world = corners[keep].reshape(-1, 3) @ axes.T
        view = world @ self._view.T  # x right, y up, z away from the viewer
        tri = view.reshape(-1, 3, 3)
        normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        length = np.linalg.norm(normal, axis=1)
        length[length == 0] = 1.0
        normal /= length[:, None]
        solid = self._solid[keep]
        # The view (right, up, away) is a mirror image of the world (east, north, up), so a normal worked out from
        # view-space corners points the opposite way to the one in model space: undo that before using the outward sign.
        mirrored = float(np.linalg.det(self._view @ axes)) < 0
        normal[solid] *= self._outward[keep][solid, None] * (-1.0 if mirrored else 1.0)
        away = solid & (normal[:, 2] > 0)  # the far side of a closed body: hidden behind the near side
        normal[~solid & (normal[:, 2] > 0)] *= -1  # two-sided: always shade the side facing the viewer
        light = LIGHT_VIEW / np.linalg.norm(LIGHT_VIEW)
        shade = AMBIENT + (1 - AMBIENT) * np.clip(normal @ light, 0.0, 1.0)
        shade = np.where(solid, (SOLID_LIFT + (1 - SOLID_LIFT) * shade) * (EDGE_DARKENING + (1 - EDGE_DARKENING) * np.abs(normal[:, 2])), shade)  # round bodies fall away toward their edges
        depth = -tri[:, :, 2].mean(axis=1)
        depth[away] = np.inf  # sorted to the end, then dropped
        order = np.argsort(depth)[: len(depth) - int(away.sum())]  # farthest first

        side = self.size_px * SUPERSAMPLE
        image = QImage(side, side, QImage.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = side * 0.97 / 1.0  # the model is one unit long; leave a sliver of margin
        centre = side / 2
        pixels = np.empty_like(tri[:, :, :2])
        pixels[:, :, 0] = centre + tri[:, :, 0] * scale
        pixels[:, :, 1] = centre - tri[:, :, 1] * scale
        colours = np.clip(self._colours[keep] * shade[:, None], 0.0, 1.0)
        previous = None
        for index in order:
            r, g, b = colours[index]
            rgb = (int(r * 255), int(g * 255), int(b * 255))
            if rgb != previous:
                colour = QColor(*rgb)
                painter.setBrush(colour)
                painter.setPen(QPen(colour, 0.7))  # a hairline of the same colour hides the seams between triangles
                previous = rgb
            (x0, y0), (x1, y1), (x2, y2) = pixels[index]
            painter.drawPolygon(QPolygonF([QPointF(x0, y0), QPointF(x1, y1), QPointF(x2, y2)]))
        painter.end()
        if 0 < step < PROGRESS_STEPS:  # the booster leaves through the edge of the dial rather than across the bar
            mask = QPainter(image)
            mask.setRenderHint(QPainter.Antialiasing)
            mask.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            mask.setBrush(QColor(0, 0, 0, 255))
            mask.setPen(Qt.NoPen)
            mask.drawEllipse(QPointF(side / 2, side / 2), side / 2, side / 2)
            mask.end()
        return image
