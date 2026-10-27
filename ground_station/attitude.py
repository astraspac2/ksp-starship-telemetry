"""The 3D attitude dial's geometry: where the rocket and the compass points land on the screen.

The dial is a globe seen from slightly above. The equator ellipse is the horizon plane, north is a
point on it, and the rocket is a line through the centre pointing where the vessel's nose points.
Qt-free so it can be unit-tested.
"""

import math
from dataclasses import dataclass

VIEW_ELEVATION_DEG = 24.2  # camera height above the horizon plane; sin() of it is the equator's squashed height
VIEW_AZIMUTH_DEG = -35.0  # the world is turned this much about the vertical so north sits to the upper left
MIN_LENGTH_RATIO = 0.3  # a rocket pointing at the camera is still drawn, just short


@dataclass(frozen=True)
class RocketView:
    angle_deg: float  # clockwise from straight up on the screen, for a nose-up picture
    length_ratio: float  # drawn length relative to a rocket standing upright and square-on, 0..1


def _to_screen(east: float, north: float, up: float) -> tuple[float, float]:
    """Project a point of the unit globe to the screen: (x right, y up), both in units of the globe radius."""
    a = math.radians(VIEW_AZIMUTH_DEG)
    el = math.radians(VIEW_ELEVATION_DEG)
    x = east * math.cos(a) + north * math.sin(a)
    depth = -east * math.sin(a) + north * math.cos(a)  # away from the viewer
    return x, depth * math.sin(el) + up * math.cos(el)


def nose_direction(pitch_deg: float, heading_deg: float) -> tuple[float, float, float]:
    """Unit vector (east, north, up) the nose points along. Pitch is above the horizon, heading is compass degrees."""
    pitch, heading = math.radians(pitch_deg), math.radians(heading_deg)
    return (math.cos(pitch) * math.sin(heading), math.cos(pitch) * math.cos(heading), math.sin(pitch))


def rocket_view(pitch_deg: float, heading_deg: float) -> RocketView:
    x, y = _to_screen(*nose_direction(pitch_deg, heading_deg))
    upright = math.cos(math.radians(VIEW_ELEVATION_DEG))
    length = math.hypot(x, y)
    angle = math.degrees(math.atan2(x, y)) if length > 1e-6 else 0.0
    return RocketView(angle, min(max(length / upright, MIN_LENGTH_RATIO), 1.0))


def compass_point(heading_deg: float) -> tuple[float, float]:
    """Screen position (x right, y up, in globe radii) of a compass direction on the horizon ellipse."""
    heading = math.radians(heading_deg)
    return _to_screen(math.sin(heading), math.cos(heading), 0.0)


def _rotate(q: tuple[float, float, float, float], v: tuple[float, float, float]) -> tuple[float, float, float]:
    """Rotate vector v by the quaternion q = (x, y, z, w), the way kRPC turns a vessel-frame vector into the surface frame."""
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (
        v[0] + w * tx + (y * tz - z * ty),
        v[1] + w * ty + (z * tx - x * tz),
        v[2] + w * tz + (x * ty - y * tx),
    )


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def attitude_from_rotation(q: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """(pitch above the horizon, compass heading, roll) of a vessel from its rotation in kRPC's surface frame.

    The surface frame's axes are up, north, east; the vessel's own x axis points out of its right side and its y
    axis out of its nose. Roll is what the dial's renderer expects (see `body_to_world`): zero when the vessel's top
    faces up, positive when its right side swings up, so a vessel with its right wing dropping has a negative roll.
    Unlike the Euler angles kRPC reports, this stays correct when the vessel points straight up.
    """
    right_s, nose_s = _rotate(q, (1.0, 0.0, 0.0)), _rotate(q, (0.0, 1.0, 0.0))
    right = (right_s[2], right_s[1], right_s[0])  # surface frame (up, north, east) -> (east, north, up)
    nose = (nose_s[2], nose_s[1], nose_s[0])
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, nose[2]))))
    heading = math.degrees(math.atan2(nose[0], nose[1])) % 360.0
    reference = _cross(nose, (0.0, 0.0, 1.0))  # the right-hand side of a vessel with its top up
    size = math.hypot(*reference)
    if size < 1e-6:  # standing straight up: the heading says which way "right" is
        h = math.radians(heading)
        reference = (math.cos(h), -math.sin(h), 0.0)
    else:
        reference = (reference[0] / size, reference[1] / size, reference[2] / size)
    top = _cross(reference, nose)
    roll = math.degrees(math.atan2(sum(a * b for a, b in zip(right, top)), sum(a * b for a, b in zip(right, reference))))
    return pitch, heading, roll
