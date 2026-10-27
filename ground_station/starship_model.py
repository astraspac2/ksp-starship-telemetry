"""A built-in 3D Starship on its Super Heavy booster, for the attitude dial. Qt-free.

Measured from pictures of the user's KSP vessel (ship and booster alone, and the full stack):

  ship     about 44 % of the stack. Long ogive nose (a quarter of the ship), a heat shield covering one half of the
           circumference (the other half stainless), weld belts, two swept forward flaps just below the nose and two
           large aft flaps near the bottom.
  booster  a lattice hot-stage ring on top, four flat oval grid-fin paddles (three: the steel side has none) just under it, a dark weld belt about a
           third of the way down and a deep engine skirt whose bells stick out at the bottom.

Proportions are the pictures' (ship and booster about 5.8 and 7.9 diameters long), but the body is drawn about 2 times wider
than that so it still reads on a small dial.

Like every dial model it is one unit long, centred on the origin, nose up along +Y.
"""

import numpy as np

from .mesh import Mesh

SHIP_LENGTH = 0.44
SPLIT_Y = 0.5 - SHIP_LENGTH  # where the ship's bottom meets the booster, in model height
BODY_RADIUS = 0.052
DIAMETER = 2 * BODY_RADIUS
NOSE_SHARE = 0.25  # of the ship's length
HOT_STAGE_HEIGHT = 0.022
SKIRT_TOP = -0.47  # the engine skirt runs from here down to the bells at -0.5

# Colours follow the SpaceX overlay's dial icon: a bright white booster under a dark ship. The ship is as dark as still reads
# on the dial's dark disc.
STEEL = np.array([0.95, 0.96, 0.98])  # the booster
SHIP_STEEL = np.array([0.58, 0.60, 0.64])  # the ship's stainless half
TILE = np.array([0.30, 0.32, 0.37])  # the ship's heat shield: black in the game, dark steel here so it still reads on the dial's dark disc
BELT = np.array([0.66, 0.68, 0.72])  # the booster's weld belt
RING_LIGHT = np.array([0.82, 0.83, 0.86])  # the hot-stage lattice, light and dark struts
RING_DARK = np.array([0.52, 0.53, 0.57])
ENGINES = np.array([0.20, 0.20, 0.23])
FIN = np.array([0.70, 0.71, 0.75])
FLAP = np.array([0.30, 0.31, 0.35])

TILE_HALF_ANGLE = np.radians(105)  # the heat shield: half the circumference in the pictures, a little more so it shows from most angles
# The heat shield (and with it the flaps' lean and the one grid fin on the shield side) sits on the model's -Z side. The dial turns
# the model with the vessel's rotation, the model's +Z being the vessel's top; kRPC's vessel frame has its Z axis out of the
# bottom, and on the user's Starship that is the side with the heat shield, the lone grid fin and the aft engine. (Recorded on the
# pad: the part positions, and the vessel's Z axis pointing south.)
TILE_CENTRE = np.radians(270)  # the side of the ship the heat shield is on, as an angle round the axis (x = cos, z = sin)

FORWARD_FLAP_LEAN = np.radians(22)  # how far the forward flaps lean back from straight out sideways
AFT_FLAP_LEAN = np.radians(12)  # how far the aft flaps lean forward, toward the heat shield
FORWARD_FLAP_THICKNESS = 0.012
AFT_FLAP_THICKNESS = 0.016

SHIP_BELTS: tuple[tuple[float, float], ...] = ()  # (from, to) as fractions of the ship's length from its tip; none: too fine for the dial
BOOSTER_BELT = (0.345, 0.375)  # as fractions of the booster's length from its top


def _nose_radius(s: float) -> float:
    """Ogive nose: radius at fraction s (0 at the tip, 1 where the nose meets the barrel). Fits the pictures' outline."""
    return BODY_RADIUS * (1.0 - (1.0 - s) ** 1.5)


def _body_radius(height: float) -> float:
    """The ship's radius at this height: round the nose, full on the barrel."""
    nose_length = NOSE_SHARE * SHIP_LENGTH
    if height >= 0.5 - nose_length:
        return _nose_radius(min(max((0.5 - height) / nose_length, 0.0), 1.0))
    return BODY_RADIUS


def starship_stack(segments: int = 20) -> Mesh:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    colours: list[np.ndarray] = []
    solid: list[bool] = []  # per face: part of a closed body round the axis

    def tube(rings, colour_of, tiles: bool = False) -> int:
        """Rings from top to bottom as (height, radius or per-segment radii); `colour_of(upper, lower, k, half)` gives a band's colour.

        Returns the index of the first vertex of the first ring.
        """
        first, starts = len(vertices), []
        for height, radius in rings:
            starts.append(len(vertices))
            for k in range(segments):
                angle = 2 * np.pi * k / segments
                r = radius[k] if isinstance(radius, (list, tuple, np.ndarray)) else radius
                vertices.append((r * np.cos(angle), height, r * np.sin(angle)))
        for r in range(len(rings) - 1):
            for k in range(segments):
                a, b = starts[r] + k, starts[r] + (k + 1) % segments
                c, d = starts[r + 1] + k, starts[r + 1] + (k + 1) % segments
                middle = 2 * np.pi * (k + 0.5) / segments
                diff = abs((middle - TILE_CENTRE + np.pi) % (2 * np.pi) - np.pi)
                on_shield = tiles and diff < TILE_HALF_ANGLE
                faces.extend([(a, c, b), (b, c, d)])
                solid.extend([True, True])
                colours.extend(
                    [
                        TILE if on_shield else colour_of(rings[r][0], rings[r + 1][0], k, 0),
                        TILE if on_shield else colour_of(rings[r][0], rings[r + 1][0], k, 1),
                    ]
                )
        return first

    def cap(height: float, ring_start: int, colour: np.ndarray) -> None:
        """Close a tube's end with a fan to a point on the axis."""
        centre = len(vertices)
        vertices.append((0.0, height, 0.0))
        for k in range(segments):
            faces.append((centre, ring_start + (k + 1) % segments, ring_start + k))
            solid.append(False)
            colours.append(colour)

    def flap(angle: float, outline: list[tuple[float, float]], thickness: float, colour: np.ndarray) -> None:
        """A flap: a slab sticking out of the ship at this angle round its axis. `outline` is (out from the body, height)."""
        direction = np.array([np.cos(angle), np.sin(angle)])
        sideways = np.array([-direction[1], direction[0]])
        starts = []
        for level in (thickness / 2, -thickness / 2):
            starts.append(len(vertices))
            for out, height in outline:
                root = _body_radius(height) * 0.96  # sunk a little into the body so the flap is joined to it
                x, z = direction * (root if out == 0.0 else BODY_RADIUS * 0.96 + out) + sideways * level
                vertices.append((x, height, z))
            for k in range(1, len(outline) - 1):
                faces.append((starts[-1], starts[-1] + k, starts[-1] + k + 1))
                solid.append(False)
                colours.append(colour)
        upper, lower = starts
        for k in range(len(outline)):
            a, b = upper + k, upper + (k + 1) % len(outline)
            c, d = lower + k, lower + (k + 1) % len(outline)
            faces.extend([(a, c, b), (b, c, d)])
            solid.extend([False, False])
            colours.extend([colour, colour])

    def paddle(angle: float, height: float, colour: np.ndarray) -> None:
        """A grid fin: a thin, flat, rounded paddle sticking out sideways from the booster."""
        direction = np.array([np.cos(angle), np.sin(angle)])
        sideways = np.array([-direction[1], direction[0]])
        inner, outer, half_width, thickness = BODY_RADIUS * 0.9, BODY_RADIUS + 0.40 * DIAMETER, 0.15 * DIAMETER, 0.008
        outline = []
        for step in range(8):  # an oval: eight corners round the paddle
            a = 2 * np.pi * step / 8
            along = (inner + outer) / 2 + np.sign(np.cos(a)) * abs(np.cos(a)) ** 0.5 * (outer - inner) / 2
            across = np.sign(np.sin(a)) * abs(np.sin(a)) ** 0.5 * half_width
            outline.append(direction * along + sideways * across)
        starts = []
        for level in (height + thickness / 2, height - thickness / 2):
            starts.append(len(vertices))
            for x, z in outline:
                vertices.append((x, level, z))
            for k in range(1, 7):
                faces.append((starts[-1], starts[-1] + k, starts[-1] + k + 1))
                solid.append(False)
                colours.append(colour)
        upper, lower = starts
        for k in range(8):
            a, b = upper + k, upper + (k + 1) % 8
            c, d = lower + k, lower + (k + 1) % 8
            faces.extend([(a, c, b), (b, c, d)])
            solid.extend([False, False])
            colours.extend([colour, colour])

    def shade(factor: float) -> np.ndarray:
        return np.minimum(STEEL * factor, 1.0)

    # the ship: nose, then the barrel in weld bands down to the hot-stage ring
    barrel_top = 0.5 - NOSE_SHARE * SHIP_LENGTH

    def ship_height(fraction: float) -> float:
        return 0.5 - fraction * SHIP_LENGTH

    belts = [(ship_height(a), ship_height(b)) for a, b in SHIP_BELTS]  # (top, bottom) heights
    ship_rings: list[tuple[float, float]] = [(0.5, 0.0)]
    for step in range(1, 9):
        s = step / 8
        ship_rings.append((0.5 - NOSE_SHARE * SHIP_LENGTH * s, _nose_radius(s)))
    edges = {SPLIT_Y}
    for top, bottom in belts:
        edges.update((top, bottom))
    bands = 5
    edges.update(barrel_top + (SPLIT_Y - barrel_top) * i / bands for i in range(1, bands))
    for height in sorted((h for h in edges if h < barrel_top - 1e-9), reverse=True):
        ship_rings.append((height, BODY_RADIUS))

    def ship_colour(upper: float, lower: float, k: int, half: int) -> np.ndarray:
        middle = (upper + lower) / 2
        if any(bottom <= middle <= top for top, bottom in belts):
            return BELT
        return SHIP_STEEL * (0.97 if int(middle * 40) % 2 else 1.03)

    ship_first = tube(ship_rings, ship_colour, tiles=True)
    cap(SPLIT_Y + 0.001, ship_first + (len(ship_rings) - 1) * segments, ENGINES)  # the ship's bottom, so it is not hollow once it is free

    # the booster: hot-stage lattice ring, barrel in bands with a dark belt, then the engine skirt and its bells
    ring_bottom = SPLIT_Y - HOT_STAGE_HEIGHT
    booster_length = 0.5 + ring_bottom
    belt = (ring_bottom - BOOSTER_BELT[1] * booster_length, ring_bottom - BOOSTER_BELT[0] * booster_length)  # (bottom, top)
    lattice = BODY_RADIUS * 1.03
    booster_rings: list[tuple[float, float]] = [(SPLIT_Y, lattice), (ring_bottom, lattice)]
    heights = {belt[0], belt[1], SKIRT_TOP}
    heights.update(ring_bottom + (SKIRT_TOP - ring_bottom) * i / 6 for i in range(1, 6))
    for height in sorted(heights, reverse=True):
        booster_rings.append((height, BODY_RADIUS))
    bells = [BODY_RADIUS * (0.92 if k % 2 == 0 else 0.70) for k in range(segments)]  # bells and the gaps between them
    booster_rings.extend([(-0.49, [BODY_RADIUS * 0.97] * segments), (-0.5, bells)])

    def booster_colour(upper: float, lower: float, k: int, half: int) -> np.ndarray:
        if upper >= SPLIT_Y - 1e-9:  # the lattice: light and dark struts on a diagonal
            return RING_LIGHT if half == 0 else RING_DARK
        middle = (upper + lower) / 2
        if middle < SKIRT_TOP:
            return ENGINES
        if belt[0] <= middle <= belt[1]:
            return BELT
        return shade(0.97 if int(middle * 40) % 2 else 1.03)

    first = tube(booster_rings, booster_colour)
    cap(-0.5, first + (len(booster_rings) - 1) * segments, ENGINES)
    cap(SPLIT_Y - 0.001, first, RING_DARK)  # the booster's top, seen once the ship has left it (a hair either side of the split, so each belongs to its own stage)

    # grid fins: three flat paddles just below the lattice ring, on the heat-shield side and out to each side; the steel side is bare
    for turn in (0.0, np.pi / 2, -np.pi / 2):
        paddle(TILE_CENTRE + turn, ring_bottom - 0.040, FIN)

    # forward flaps (swept, just below the nose) and aft flaps (big, near the bottom of the ship)
    forward = [
        (0.0, ship_height(0.115)),
        (0.38 * DIAMETER, ship_height(0.18)),
        (0.38 * DIAMETER, ship_height(0.225)),
        (0.0, ship_height(0.225)),
    ]
    aft = [
        (0.0, ship_height(0.80)),
        (0.38 * DIAMETER, ship_height(0.86)),
        (0.38 * DIAMETER, ship_height(0.985)),
        (0.0, ship_height(0.985)),
    ]
    # seen from above (the nose pointing at you, the heat shield below): the forward flaps lean back toward the steel
    # side, the aft flaps stick out nearly straight, a little toward the heat shield
    for mirror in (1, -1):
        flap(TILE_CENTRE + mirror * (np.pi / 2 + FORWARD_FLAP_LEAN), forward, FORWARD_FLAP_THICKNESS, FLAP)
        flap(TILE_CENTRE + mirror * (np.pi / 2 - AFT_FLAP_LEAN), aft, AFT_FLAP_THICKNESS, FLAP)

    return Mesh(
        np.asarray(vertices, dtype=np.float32),
        np.asarray(faces, dtype=np.int32),
        np.asarray(colours, dtype=np.float32),
        stage_split=SPLIT_Y,
        solid=np.asarray(solid, dtype=bool),
    )
