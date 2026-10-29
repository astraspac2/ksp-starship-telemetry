"""A built-in 3D Starship on its Super Heavy booster, for the attitude dial. Qt-free.

Measured from pictures of the user's KSP vessel (ship and booster alone, and the full stack):

  ship     about 44 % of the stack. Long ogive nose (a quarter of the ship), a heat shield of staggered black tiles covering
           one half of the circumference (the other half polished stainless), two swept forward flaps just below the nose and
           two large aft flaps near the bottom.
  booster  a slotted hot-stage ring on top, three lattice grid fins (the steel side has none) just under it, a dark weld belt
           about a third of the way down and a deep engine skirt whose 33 bells stick out at the bottom.

Proportions are the pictures' (ship and booster about 5.8 and 7.9 diameters long), but the body is drawn about 1.15 times wider
than that so it still reads on a small dial.

The round bodies carry smooth normals and a gloss, so the renderer shades them without facets and puts a glint on the polished
steel; the tiles stay matt.

Like every dial model it is one unit long, centred on the origin, nose up along +Y.
"""

import numpy as np

from .mesh import Mesh

SHIP_LENGTH = 0.44
SPLIT_Y = 0.5 - SHIP_LENGTH  # where the ship's bottom meets the booster, in model height
BODY_RADIUS = 0.037  # the ship is 6 diameters long, as measured on the picture of it
DIAMETER = 2 * BODY_RADIUS
NOSE_SHARE = 0.175  # of the ship's length: the ogive reaches its full width this far from the tip (measured on a picture of the ship)
NOSE_BLACK_SHARE = 0.85  # of the nose is black tile all the way round, even on the steel side
HOT_STAGE_HEIGHT = 0.022
SKIRT_TOP = -0.47  # the engine skirt runs from here down to the bells at -0.5
SEGMENTS = 28  # round the axis: enough that the silhouette is smooth at the dial's size

# Colours follow the SpaceX overlay's dial icon: a bright white booster under a dark ship.
STEEL = np.array([0.95, 0.96, 0.98])  # the booster: polished stainless
SHIP_STEEL = np.array([0.66, 0.68, 0.72])  # the ship's stainless half
TILE = np.array([0.17, 0.18, 0.21])  # the ship's heat shield: black in the game, dark enough to read as black but not lost on the dial's dark disc
BELT = np.array([0.62, 0.64, 0.68])  # the booster's weld belt
RING_LIGHT = np.array([0.84, 0.85, 0.88])  # the hot-stage ring: struts and the dark slots between them
RING_DARK = np.array([0.34, 0.35, 0.39])
ENGINES = np.array([0.20, 0.20, 0.23])
BELL = np.array([0.09, 0.09, 0.11])  # the inside of an engine bell, seen from below
FIN = np.array([0.72, 0.73, 0.77])
FIN_HOLE = np.array([0.30, 0.31, 0.36])  # the gaps in a grid fin's lattice
FLAP = np.array([0.18, 0.19, 0.22])  # the flaps are covered by the heat shield too: black tile like the shield side

GLOSS_STEEL = 0.75
GLOSS_BOOSTER = 0.85
GLOSS_TILE = 0.04
GLOSS_FLAP = 0.04

TILE_HALF_ANGLE = np.radians(94)  # the heat shield: half the circumference in the pictures, a little more so it shows from most angles
# The heat shield (and with it the flaps' lean and the one grid fin on the shield side) sits on the model's -Z side. The dial turns
# the model with the vessel's rotation, the model's +Z being the vessel's top; kRPC's vessel frame has its Z axis out of the
# bottom, and on the user's Starship that is the side with the heat shield, the lone grid fin and the aft engine. (Recorded on the
# pad: the part positions, and the vessel's Z axis pointing south.)
TILE_CENTRE = np.radians(270)  # the side of the ship the heat shield is on, as an angle round the axis (x = cos, z = sin)

FORWARD_FLAP_LEAN = np.radians(22)  # how far the forward flaps lean back from straight out sideways
AFT_FLAP_LEAN = 0.0  # the aft flaps stick out straight to each side, neither toward the heat shield nor away from it
FORWARD_FLAP_THICKNESS = 0.012
AFT_FLAP_THICKNESS = 0.016

SHIP_BELTS = ((0.328, 0.338), (0.581, 0.589), (0.865, 0.873))  # (from, to) as fractions of the ship's length from its tip, measured on the picture
SHIP_BELT = np.array([0.38, 0.39, 0.43])  # the dark seams round the ship
RACEWAY = np.array([0.82, 0.83, 0.86])  # the two pipes running down the ship's steel side
RACEWAY_OFFSET = np.radians(19.3)  # how far either side of the steel side's centre line they run
RACEWAY_FROM, RACEWAY_TO = 0.35, 0.95  # as fractions of the ship's length from its tip
WINDOWS_FROM, WINDOWS_TO = 0.200, 0.235  # the band with the two dark hatches and the logo between them, as fractions from the tip
HATCH_OFFSET = np.radians(32)  # how far either side of the steel side's centre line a hatch sits
HATCH = np.array([0.13, 0.13, 0.16])
HATCH_RIM = np.array([0.40, 0.41, 0.45])
LOGO = np.array([0.08, 0.08, 0.10])  # the black X between the hatches
HATCH_SIZE = (0.0120, 0.0085)  # round the ship, along it
LOGO_HEIGHT = 0.0125
BOOSTER_BELT = (0.345, 0.375)  # as fractions of the booster's length from its top
BELL_RADIUS = 0.0036  # one engine bell on the booster's bottom


def _nose_radius(s: float) -> float:
    """The nose: radius at fraction s (0 at the tip, 1 where the nose meets the barrel). A rounded cone that meets the barrel
    tangentially, so there is no crease where the nose starts, with a rounded tip, not a spike (the pictures of the real nose)."""
    return BODY_RADIUS * float(np.sin(0.5 * np.pi * min(max(s, 0.0), 1.0) ** 0.85))


def _body_radius(height: float) -> float:
    """The ship's radius at this height: round the nose, full on the barrel."""
    nose_length = NOSE_SHARE * SHIP_LENGTH
    if height >= 0.5 - nose_length:
        return _nose_radius(min(max((0.5 - height) / nose_length, 0.0), 1.0))
    return BODY_RADIUS


def _tile_reach(height: float) -> float:
    """How far round from the heat shield's centre line the black tiles reach at this height: about half way on the barrel, then
    opening up over the nose until they cover it all the way round, so the steel side ends in a rounded point (the pictures)."""
    barrel_top = 0.5 - NOSE_SHARE * SHIP_LENGTH
    black_bottom = 0.5 - NOSE_SHARE * SHIP_LENGTH * NOSE_BLACK_SHARE
    t = min(max((height - barrel_top) / (black_bottom - barrel_top), 0.0), 1.0)
    return TILE_HALF_ANGLE + (np.pi - TILE_HALF_ANGLE) * t * t * (3.0 - 2.0 * t)


def _engine_layout() -> list[tuple[float, float]]:
    """The 33 engines as on the booster seen from below: 3 in the centre, a ring of 10, an outer ring of 20 (as in the engine dial)."""
    points = [(0.236 * np.cos(np.radians(a)), 0.236 * np.sin(np.radians(a))) for a in (90, 210, 330)]
    points += [(0.596 * np.cos(np.radians(36 * k)), 0.596 * np.sin(np.radians(36 * k))) for k in range(10)]
    points += [(np.cos(np.radians(9 + 18 * k)), np.sin(np.radians(9 + 18 * k))) for k in range(20)]
    return points


def starship_stack(segments: int = SEGMENTS) -> Mesh:
    vertices: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    colours: list[np.ndarray] = []
    gloss: list[float] = []
    solid: list[bool] = []  # per face: part of a closed body round the axis

    def add_face(corners: tuple[int, int, int], colour: np.ndarray, shine: float, closed: bool) -> None:
        faces.append(corners)
        colours.append(colour)
        gloss.append(shine)
        solid.append(closed)

    def tube(rings, colour_of, tiles: bool = False) -> int:
        """Rings from top to bottom as (height, radius or per-segment radii); `colour_of(upper, lower, k, band)` gives a band's
        (colour, gloss). Two rings at the same height make a step. Returns the index of the first vertex of the first ring."""
        first, starts = len(vertices), []
        slopes = []  # for each band, how fast the radius grows going down: it tilts the band's normal up
        for r in range(len(rings) - 1):
            (h0, r0), (h1, r1) = rings[r], rings[r + 1]
            mean0 = float(np.mean(r0)) if isinstance(r0, (list, tuple, np.ndarray)) else r0
            mean1 = float(np.mean(r1)) if isinstance(r1, (list, tuple, np.ndarray)) else r1
            slopes.append(None if h0 - h1 < 1e-6 else (mean1 - mean0) / (h0 - h1))
        for index, (height, radius) in enumerate(rings):
            starts.append(len(vertices))
            around = [s for s in (slopes[index - 1] if index > 0 else None, slopes[index] if index < len(slopes) else None) if s is not None]
            lean = float(np.mean(around)) if around else 0.0
            for k in range(segments):
                angle = 2 * np.pi * k / segments
                r = radius[k] if isinstance(radius, (list, tuple, np.ndarray)) else radius
                vertices.append((r * np.cos(angle), height, r * np.sin(angle)))
                n = np.array([np.cos(angle), lean, np.sin(angle)])
                n /= np.linalg.norm(n)
                normals.append((n[0], n[1], n[2]))
        for r in range(len(rings) - 1):
            step = rings[r][0] - rings[r + 1][0] < 1e-6
            for k in range(segments):
                a, b = starts[r] + k, starts[r] + (k + 1) % segments
                c, d = starts[r + 1] + k, starts[r + 1] + (k + 1) % segments
                middle = 2 * np.pi * (k + 0.5) / segments
                diff = abs((middle - TILE_CENTRE + np.pi) % (2 * np.pi) - np.pi)
                if tiles and diff < _tile_reach((rings[r][0] + rings[r + 1][0]) / 2):
                    # staggered tiles: a slight chequer of brightness, offset on alternate rows, as on the shield
                    shade = 1.0 + 0.05 * (((k + r % 2) % 2) - 0.5) + 0.025 * (((k * 5 + r * 3) % 4) - 1.5)
                    colour, shine = TILE * shade, GLOSS_TILE
                else:
                    colour, shine = colour_of(rings[r][0], rings[r + 1][0], k, r)
                for corners in ((a, c, b), (b, c, d)):
                    add_face(corners, colour, shine, not step)
        return first

    def cap(height: float, ring_start: int, colour: np.ndarray) -> None:
        """Close a tube's end with a fan to a point on the axis."""
        centre = len(vertices)
        vertices.append((0.0, height, 0.0))
        normals.append((0.0, 0.0, 0.0))
        for k in range(segments):
            add_face((centre, ring_start + (k + 1) % segments, ring_start + k), colour, 0.0, False)

    def flat(points: list[tuple[float, float, float]], colour: np.ndarray, shine: float) -> None:
        """A flat convex polygon (a fan from its first corner), drawn from both sides."""
        base = len(vertices)
        for point in points:
            vertices.append(point)
            normals.append((0.0, 0.0, 0.0))
        for k in range(1, len(points) - 1):
            add_face((base, base + k, base + k + 1), colour, shine, False)

    def slab(corner_rows: list[list[tuple[float, float, float]]], colour: np.ndarray, shine: float) -> None:
        """A thin slab given as its upper and lower outlines: both faces and the rim."""
        upper, lower = corner_rows
        start = len(vertices)
        for point in upper + lower:
            vertices.append(point)
            normals.append((0.0, 0.0, 0.0))
        count = len(upper)
        for k in range(1, count - 1):
            add_face((start, start + k, start + k + 1), colour, shine, False)
            add_face((start + count, start + count + k, start + count + k + 1), colour, shine, False)
        for k in range(count):
            a, b = start + k, start + (k + 1) % count
            c, d = start + count + k, start + count + (k + 1) % count
            add_face((a, c, b), colour, shine, False)
            add_face((b, c, d), colour, shine, False)

    def flap(angle: float, outline: list[tuple[float, float]], thickness: float) -> None:
        """A flap: a slab sticking out of the ship at this angle round its axis. `outline` is (out from the body, height)."""
        direction = np.array([np.cos(angle), np.sin(angle)])
        sideways = np.array([-direction[1], direction[0]])
        rows = []
        for level in (thickness / 2, -thickness / 2):
            row = []
            for out, height in outline:
                root = _body_radius(height) * 0.96  # sunk a little into the body so the flap is joined to it
                x, z = direction * (root if out == 0.0 else BODY_RADIUS * 0.96 + out) + sideways * level
                row.append((x, height, z))
            rows.append(row)
        slab(rows, FLAP, GLOSS_FLAP)

    def grid_fin(angle: float, height: float) -> None:
        """A grid fin: a flat lattice sticking out sideways from the booster, bars with dark gaps between them."""
        direction = np.array([np.cos(angle), np.sin(angle)])
        sideways = np.array([-direction[1], direction[0]])
        inner, outer = BODY_RADIUS * 0.9, BODY_RADIUS + 0.30 * DIAMETER
        half_width, thickness = 0.19 * DIAMETER, 0.008
        along_cells, across_cells = 5, 5
        def at(along: float, across: float, level: float) -> tuple[float, float, float]:
            x, z = direction * along + sideways * across
            return (float(x), level, float(z))

        for i in range(along_cells):
            for j in range(across_cells):
                lo, hi = inner + (outer - inner) * i / along_cells, inner + (outer - inner) * (i + 1) / along_cells
                left, right = -half_width + 2 * half_width * j / across_cells, -half_width + 2 * half_width * (j + 1) / across_cells
                hole = i % 2 == 1 and j % 2 == 1  # a frame all round and bars between four open windows: a lattice
                for level in (height + thickness / 2, height - thickness / 2):
                    flat([at(lo, left, level), at(hi, left, level), at(hi, right, level), at(lo, right, level)], FIN_HOLE if hole else FIN, 0.2)

    # the ship: nose, then the barrel in weld bands down to the bottom
    barrel_top = 0.5 - NOSE_SHARE * SHIP_LENGTH

    def ship_height(fraction: float) -> float:
        return 0.5 - fraction * SHIP_LENGTH

    belts = [(ship_height(a), ship_height(b)) for a, b in SHIP_BELTS]  # (top, bottom) heights
    ship_rings: list[tuple[float, float]] = [(0.5, 0.0)]
    for step in range(1, 15):
        s = (step / 14) ** 1.35  # more rings near the tip, where it curves most
        ship_rings.append((0.5 - NOSE_SHARE * SHIP_LENGTH * s, _nose_radius(s)))
    edges = {SPLIT_Y}
    for top, bottom in belts:
        edges.update((top, bottom))
    bands = 7
    edges.update(barrel_top + (SPLIT_Y - barrel_top) * i / bands for i in range(1, bands))
    for height in sorted((h for h in edges if h < barrel_top - 1e-9), reverse=True):
        ship_rings.append((height, BODY_RADIUS))

    nose_black_bottom = 0.5 - NOSE_SHARE * SHIP_LENGTH * NOSE_BLACK_SHARE
    steel_centre = TILE_CENTRE + np.pi

    def ship_colour(upper: float, lower: float, k: int, band: int) -> tuple[np.ndarray, float]:
        middle = (upper + lower) / 2
        if middle > nose_black_bottom:  # the tip of the nose is black tile all the way round
            return TILE * (1.0 + 0.04 * (((k + band % 2) % 2) - 0.5)), GLOSS_TILE
        if middle > barrel_top:  # the steel part of the nose: shinier lower down, matt up by the black tip, so no bright crescent shows there
            fade = (middle - barrel_top) / max(nose_black_bottom - barrel_top, 1e-9)
            return SHIP_STEEL, GLOSS_STEEL - (GLOSS_STEEL - 0.25) * min(max(fade, 0.0), 1.0)
        if any(bottom <= middle <= top for top, bottom in belts):
            return SHIP_BELT, GLOSS_STEEL
        side = abs((2 * np.pi * (k + 0.5) / segments - steel_centre + np.pi) % (2 * np.pi) - np.pi)  # how far round from the steel side's centre line
        if abs(side - RACEWAY_OFFSET) < np.radians(3) and ship_height(RACEWAY_TO) <= middle <= ship_height(RACEWAY_FROM):
            return RACEWAY, 0.5
        # stainless panels: alternate bands a touch light and dark, and a faint seam every few segments
        return SHIP_STEEL * (1.0 + 0.03 * (((k // 3 + band) % 2) - 0.5)) * (0.985 if k % 7 == 0 else 1.0), GLOSS_STEEL

    ship_first = tube(ship_rings, ship_colour, tiles=True)
    cap(SPLIT_Y + 0.001, ship_first + (len(ship_rings) - 1) * segments, ENGINES)  # the ship's bottom, so it is not hollow once it is free


    def decal(points: list[tuple[float, float]], height: float, colour: np.ndarray, lift: float) -> None:
        """A flat shape on the ship's steel side: (u, v) is how far round the ship from the steel side's centre line, and up it."""
        corners = []
        for u, v in points:
            angle = steel_centre + u / BODY_RADIUS
            corners.append(((BODY_RADIUS + lift) * np.cos(angle), height + v, (BODY_RADIUS + lift) * np.sin(angle)))
        flat(corners, colour, 0.0)

    def rounded(width: float, depth: float, corner: float) -> list[tuple[float, float]]:
        pts = []
        for cx, cy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
            for step in range(4):
                a = np.radians(a0 + 90 * step / 3)
                pts.append((cx * (width / 2 - corner) + corner * np.cos(a), cy * (depth / 2 - corner) + corner * np.sin(a)))
        return pts

    window_height = ship_height((WINDOWS_FROM + WINDOWS_TO) / 2)
    for side in (-1, 1):  # the two hatches, a rim and a dark centre
        u = side * HATCH_OFFSET * BODY_RADIUS
        decal([(u + x, y) for x, y in rounded(HATCH_SIZE[0] * 1.14, HATCH_SIZE[1] * 1.18, 0.0020)], window_height, HATCH_RIM, 0.0016)
        decal([(u + x, y) for x, y in rounded(*HATCH_SIZE, 0.0018)], window_height, HATCH, 0.0020)
    h = LOGO_HEIGHT / 2  # the logo: a long thin curved stroke crossed by a short bar
    decal([(-0.0030, -h), (-0.0014, -h), (0.0042, h * 0.94), (0.0034, h)], window_height, LOGO, 0.0023)
    decal([(-0.0046, -0.0006), (0.0034, 0.0012), (0.0036, 0.0001), (-0.0044, -0.0018)], window_height, LOGO, 0.0023)

    # the raised ablative edge: a thin ridge along each side where the black shield meets the steel, from the nose down to the tail
    ridge_heights = [h for h, _ in ship_rings if h < 0.5 - NOSE_SHARE * SHIP_LENGTH * NOSE_BLACK_SHARE]
    for side in (-1, 1):
        for h0, h1 in zip(ridge_heights, ridge_heights[1:]):
            corners = []
            for height in (h0, h1):
                angle = TILE_CENTRE + side * _tile_reach(height)
                radius = _body_radius(height) + 0.0016
                half = 0.0020 / max(radius, 1e-6)
                corners.append([(radius * np.cos(angle - half), height, radius * np.sin(angle - half)), (radius * np.cos(angle + half), height, radius * np.sin(angle + half))])
            flat([corners[0][0], corners[0][1], corners[1][1], corners[1][0]], TILE * 0.7, 0.1)

    # the booster: slotted hot-stage ring, barrel in bands with a dark belt, then the engine skirt and its bells
    ring_bottom = SPLIT_Y - HOT_STAGE_HEIGHT
    booster_length = 0.5 + ring_bottom
    belt = (ring_bottom - BOOSTER_BELT[1] * booster_length, ring_bottom - BOOSTER_BELT[0] * booster_length)  # (bottom, top)
    lattice = BODY_RADIUS * 1.03
    booster_rings: list[tuple[float, float]] = [(SPLIT_Y, lattice), (ring_bottom, lattice), (ring_bottom, BODY_RADIUS)]
    heights = {belt[0], belt[1], SKIRT_TOP}
    heights.update(ring_bottom + (SKIRT_TOP - ring_bottom) * i / 8 for i in range(1, 8))
    for height in sorted(heights, reverse=True):
        booster_rings.append((height, BODY_RADIUS))
    bells = [BODY_RADIUS * (0.92 if k % 2 == 0 else 0.70) for k in range(segments)]  # bells and the gaps between them
    booster_rings.extend([(-0.49, [BODY_RADIUS * 0.97] * segments), (-0.5, bells)])

    def booster_colour(upper: float, lower: float, k: int, band: int) -> tuple[np.ndarray, float]:
        if upper >= SPLIT_Y - 1e-9:  # the slotted ring: struts and the dark slots between them
            return (RING_LIGHT if (k // 2) % 2 == 0 else RING_DARK), 0.3
        middle = (upper + lower) / 2
        if middle < SKIRT_TOP:
            return ENGINES, 0.2
        if belt[0] <= middle <= belt[1]:
            return BELT, GLOSS_BOOSTER
        return STEEL * (0.985 if band % 2 else 1.015) * (0.985 if k % 6 == 0 else 1.0), GLOSS_BOOSTER

    first = tube(booster_rings, booster_colour)
    for ux, uy in _engine_layout():  # the 33 bells, a dark hexagon each, on the skirt's flat bottom
        cx, cz = ux * BODY_RADIUS * 0.80, uy * BODY_RADIUS * 0.80
        flat(
            [(cx + BELL_RADIUS * np.cos(a), -0.5, cz + BELL_RADIUS * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 6, endpoint=False)],
            BELL,
            0.0,
        )
    cap(-0.4995, first + (len(booster_rings) - 1) * segments, ENGINES)  # a hair above the bells, so they are drawn over it
    cap(SPLIT_Y - 0.001, first, RING_DARK)  # the booster's top, seen once the ship has left it (a hair either side of the split, so each belongs to its own stage)

    # grid fins: three lattices just below the ring, on the heat-shield side and out to each side; the steel side is bare
    for turn in (0.0, np.pi / 2, -np.pi / 2):
        grid_fin(TILE_CENTRE + turn, ring_bottom - 0.040)

    # forward flaps (swept, just below the nose) and aft flaps (big, near the bottom of the ship)
    forward = [  # measured on the picture: the leading edge slants out from the nose to the tip, a short straight outer edge
        (0.0, ship_height(0.069)),
        (0.35 * DIAMETER, ship_height(0.145)),
        (0.35 * DIAMETER, ship_height(0.186)),
        (0.0, ship_height(0.190)),
    ]
    aft = [  # measured on the picture: a long slanted top edge, a straight outer edge down almost to the bottom
        (0.0, ship_height(0.730)),
        (0.42 * DIAMETER, ship_height(0.851)),
        (0.42 * DIAMETER, ship_height(0.979)),
        (0.0, ship_height(0.985)),
    ]
    # seen from above (the nose pointing at you, the heat shield below): the forward flaps lean back toward the steel
    # side, the aft flaps stick out straight to each side
    for mirror in (1, -1):
        flap(TILE_CENTRE + mirror * (np.pi / 2 + FORWARD_FLAP_LEAN), forward, FORWARD_FLAP_THICKNESS)
        flap(TILE_CENTRE + mirror * (np.pi / 2 - AFT_FLAP_LEAN), aft, AFT_FLAP_THICKNESS)

    return Mesh(
        np.asarray(vertices, dtype=np.float32),
        np.asarray(faces, dtype=np.int32),
        np.asarray(colours, dtype=np.float32),
        stage_split=SPLIT_Y,
        solid=np.asarray(solid, dtype=bool),
        vertex_normals=np.asarray(normals, dtype=np.float32),
        face_gloss=np.asarray(gloss, dtype=np.float32),
    )
