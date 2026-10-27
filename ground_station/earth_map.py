"""The black-and-white Earth shown in place of the engine dial.

A coastline outline (Natural Earth 1:110m land, public domain, in data/) is drawn once into a flat land/sea picture.
Each map is then the globe seen from straight above the vessel: every pixel of the round picture is turned back into a
latitude and longitude (an orthographic view), and lit from the upper left so the globe looks round, with grey land on
dark sea. North is up.
"""

import json
import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF

LAND_FILE = Path(__file__).resolve().parent.parent / "data" / "ne_110m_land.geojson"
MASK_WIDTH, MASK_HEIGHT = 1440, 720  # a quarter of a degree per pixel
STEP_DEG = 0.25  # the map is redrawn when the vessel has moved this far

_mask: np.ndarray | None = None
_mask_tried = False


def _rings(path: Path):
    data = json.loads(path.read_text(encoding="utf8"))
    for feature in data["features"]:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for polygon in polygons:
            for ring in polygon:  # the first ring is the outline, the rest are holes (lakes); all are drawn the same
                yield ring


def build_mask(path: Path = LAND_FILE) -> np.ndarray | None:
    """Land as 255 and sea as 0 on a flat latitude/longitude grid, or None if the outline file is missing or unreadable."""
    try:
        image = QImage(MASK_WIDTH, MASK_HEIGHT, QImage.Format_Grayscale8)
        image.fill(0)
        painter = QPainter(image)
        painter.setPen(QColor(0, 0, 0, 0))
        painter.setBrush(QColor(255, 255, 255))
        for ring in _rings(path):
            points = [QPointF((lon + 180.0) / 360.0 * MASK_WIDTH, (90.0 - lat) / 180.0 * MASK_HEIGHT) for lon, lat in ring]
            painter.drawPolygon(QPolygonF(points))
        painter.end()
        raw = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(MASK_HEIGHT, image.bytesPerLine())
        return raw[:, :MASK_WIDTH].copy()
    except (OSError, ValueError, KeyError):
        return None


def land_mask() -> np.ndarray | None:
    global _mask, _mask_tried
    if not _mask_tried:
        _mask, _mask_tried = build_mask(), True
    return _mask


def _sphere(size: int):
    """For each pixel of a round picture: x, y on the unit disc, its radius, and the surface's height towards the viewer."""
    axis = (np.arange(size) + 0.5) / size * 2.0 - 1.0
    dx, dy = np.meshgrid(axis, -axis)  # x to the right, y up
    r = np.hypot(dx, dy)
    z = np.sqrt(np.clip(1.0 - r * r, 0.0, 1.0))
    return dx, dy, r, z


def map_pixels(mask: np.ndarray, lat_deg: float, lon_deg: float, size: int) -> np.ndarray:
    """A size x size picture of the globe as seen from above (lat, lon): 0..255 for sea to land, -1 off the globe."""
    dx, dy, r, _ = _sphere(size)
    c = np.arcsin(np.minimum(r, 1.0))  # angular distance from the point under the viewer
    bearing = np.arctan2(dx, dy)  # clockwise from north
    lat0, lon0 = math.radians(lat_deg), math.radians(lon_deg)
    sin_lat = math.sin(lat0) * np.cos(c) + math.cos(lat0) * np.sin(c) * np.cos(bearing)
    lat = np.arcsin(np.clip(sin_lat, -1.0, 1.0))
    lon = lon0 + np.arctan2(np.sin(bearing) * np.sin(c) * math.cos(lat0), np.cos(c) - math.sin(lat0) * sin_lat)
    col = ((np.degrees(lon) + 180.0) % 360.0) / 360.0 * mask.shape[1]
    row = (90.0 - np.degrees(lat)) / 180.0 * mask.shape[0]
    values = mask[np.clip(row.astype(int), 0, mask.shape[0] - 1), np.clip(col.astype(int), 0, mask.shape[1] - 1)].astype(np.int16)
    values[r > 1.0] = -1
    return values


LIGHT = np.array([-0.35, 0.55, 0.75]) / np.linalg.norm([-0.35, 0.55, 0.75])  # from the upper left, towards the viewer


def shade_globe(land: np.ndarray, size: int) -> np.ndarray:
    """Turn a land/sea picture of the globe into lit, grey RGBA: light grey land, near-black sea, a faint bright rim."""
    dx, dy, r, z = _sphere(size)
    light = np.clip(dx * LIGHT[0] + dy * LIGHT[1] + z * LIGHT[2], 0.0, 1.0)
    on_land = land > 127
    grey = np.where(on_land, 38.0 + 170.0 * light ** 1.1, 5.0 + 20.0 * light)
    rim = np.clip((r - 0.93) / 0.07, 0.0, 1.0) * (r <= 1.0)  # a thin pale edge, like atmosphere catching the light
    grey = np.minimum(grey + 28.0 * rim * (0.4 + 0.6 * light), 255.0)
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    inside = land >= 0
    rgba[inside, 0] = rgba[inside, 1] = grey[inside]
    rgba[inside, 2] = np.minimum(grey[inside] + 3.0, 255.0)  # a hair of blue keeps the greys from looking dead
    rgba[inside, 3] = 255
    edge = np.clip((1.0 - r) * size / 2.0, 0.0, 1.0)  # soften the outline of the globe over a pixel
    rgba[..., 3] = (rgba[..., 3] * edge).astype(np.uint8)
    return rgba


class MapRenderer:
    """Round map pictures for the dial, kept for the last few positions so a steady position costs nothing."""

    def __init__(self, size_px: int):
        self.size_px = size_px
        self._cache: dict[tuple[int, int], QImage] = {}

    def render(self, lat_deg: float, lon_deg: float) -> QImage | None:
        """The globe over a position, in lit greys, or None when there is no outline data."""
        mask = land_mask()
        if mask is None:
            return None
        key = (round(lat_deg / STEP_DEG), round(lon_deg / STEP_DEG))
        image = self._cache.get(key)
        if image is None:
            land = map_pixels(mask, key[0] * STEP_DEG, key[1] * STEP_DEG, self.size_px)
            rgba = shade_globe(land, self.size_px)
            image = QImage(rgba.data, self.size_px, self.size_px, self.size_px * 4, QImage.Format_RGBA8888).copy()
            if len(self._cache) >= 12:
                self._cache.clear()
            self._cache[key] = image
        return image
