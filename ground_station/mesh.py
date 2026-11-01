"""3D models for the attitude dial: loading OBJ, STL and glTF/GLB files, and tidying them for display.

Every model is brought to one shape: centred on the origin, its long axis along +Y with the nose
up, one unit long, and no more triangles than the dial can draw quickly. Qt-free.
"""

import base64
import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SUPPORTED = (".obj", ".stl", ".glb", ".gltf")
DEFAULT_MAX_TRIANGLES = 3000


class ModelError(Exception):
    """A model file could not be used; the message says why, for the operator."""


@dataclass(frozen=True)
class FlapRig:
    """A flap that can swing: its vertices are `count` from `first`, and it turns about the vertical line through `pivot` (x, z)."""

    first: int
    count: int
    pivot: tuple[float, float]
    forward: bool  # a forward flap (just below the nose) rather than an aft one
    mirror: int  # +1 or -1: which side of the ship; folding turns it by mirror times the fold angle, away from the heat shield


@dataclass
class Mesh:
    vertices: np.ndarray  # (N, 3) float32
    faces: np.ndarray  # (M, 3) int32
    face_colors: np.ndarray | None = None  # (M, 3) float32 in 0..1, or None for one plain colour
    stage_split: float | None = None  # model height where the ship meets the booster, or None for the default split
    solid: np.ndarray | None = None  # (M,) bool: faces of a closed body round the Y axis, whose far side need not be drawn
    vertex_normals: np.ndarray | None = None  # (N, 3) float32 outward normals, so a round body shades smoothly instead of in facets
    face_gloss: np.ndarray | None = None  # (M,) float32 0..1: how shiny each face is (a highlight where it catches the light)
    face_lift: np.ndarray | None = None  # (M,) float32: how much nearer to draw a face than its depth says, for parts lying on a surface
    face_heat: np.ndarray | None = None  # (M,) float32 0..1: how much of the re-entry glow a face takes (the heat shield's black tiles)
    flaps: tuple[FlapRig, ...] = ()  # the parts that swing with the real vehicle's flaps, if the model has any

    @property
    def triangle_count(self) -> int:
        return int(len(self.faces))


# loading
def load_mesh(path: str | Path) -> Mesh:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ModelError(f"Unsupported model type '{suffix}'. Use {', '.join(SUPPORTED)}.")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ModelError(f"Could not read the file: {exc}") from exc
    try:
        if suffix == ".obj":
            mesh = _parse_obj(data.decode("utf-8", errors="replace"))
        elif suffix == ".stl":
            mesh = _parse_stl(data)
        else:
            mesh = _parse_gltf(data, path.parent, binary=suffix == ".glb")
    except ModelError:
        raise
    except (ValueError, KeyError, IndexError, TypeError, struct.error, json.JSONDecodeError) as exc:
        raise ModelError(f"The file is damaged or not what its extension says ({type(exc).__name__}: {exc}).") from exc
    if len(mesh.faces) == 0 or len(mesh.vertices) == 0:
        raise ModelError("The file contains no triangles.")
    return mesh


def _parse_obj(text: str) -> Mesh:
    vertices: list[list[float]] = []
    faces: list[tuple[int, int, int]] = []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif parts[0] == "f" and len(parts) >= 4:
            indices = []
            for token in parts[1:]:
                index = int(token.split("/")[0])
                indices.append(index - 1 if index > 0 else len(vertices) + index)
            for k in range(1, len(indices) - 1):  # fan-triangulate quads and larger faces
                faces.append((indices[0], indices[k], indices[k + 1]))
    if not vertices or not faces:
        raise ModelError("The OBJ file has no vertices or faces.")
    array = np.asarray(vertices, dtype=np.float32)
    tris = np.asarray(faces, dtype=np.int32)
    if tris.min() < 0 or tris.max() >= len(array):
        raise ModelError("The OBJ file refers to vertices that do not exist.")
    return Mesh(array, tris)


def _parse_stl(data: bytes) -> Mesh:
    if data[:5] == b"solid" and b"facet" in data[:2000]:  # ASCII STL
        values = []
        for line in data.decode("utf-8", errors="replace").splitlines():
            parts = line.split()
            if parts and parts[0] == "vertex":
                values.append([float(parts[1]), float(parts[2]), float(parts[3])])
        if len(values) % 3 or not values:
            raise ModelError("The STL file has no complete triangles.")
        vertices = np.asarray(values, dtype=np.float32)
    else:
        (count,) = struct.unpack_from("<I", data, 80)
        record = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
        if len(data) < 84 + count * record.itemsize:
            raise ModelError("The binary STL file is shorter than its header says.")
        triangles = np.frombuffer(data, dtype=record, count=count, offset=84)
        vertices = triangles["v"].reshape(-1, 3).astype(np.float32)
    faces = np.arange(len(vertices), dtype=np.int32).reshape(-1, 3)
    return Mesh(vertices, faces)


_COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _parse_gltf(data: bytes, folder: Path, binary: bool) -> Mesh:
    blobs: list[bytes | None] = []
    if binary:
        if data[:4] != b"glTF":
            raise ModelError("Not a GLB file.")
        offset, document, chunk_bin = 12, None, None
        while offset + 8 <= len(data):
            length, kind = struct.unpack_from("<II", data, offset)
            body = data[offset + 8 : offset + 8 + length]
            if kind == 0x4E4F534A:
                document = json.loads(body.decode("utf-8"))
            elif kind == 0x004E4942 and chunk_bin is None:
                chunk_bin = body
            offset += 8 + length
        if document is None:
            raise ModelError("The GLB file has no scene description.")
    else:
        document, chunk_bin = json.loads(data.decode("utf-8")), None

    for buffer in document.get("buffers", []):
        uri = buffer.get("uri")
        if uri is None:
            blobs.append(chunk_bin)
        elif uri.startswith("data:"):
            blobs.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            blobs.append((folder / uri).read_bytes())

    def read(accessor_index: int) -> np.ndarray:
        accessor = document["accessors"][accessor_index]
        view = document["bufferViews"][accessor["bufferView"]]
        dtype = np.dtype(_COMPONENT[accessor["componentType"]])
        width = _WIDTH[accessor["type"]]
        stride = view.get("byteStride") or dtype.itemsize * width
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        blob = blobs[view["buffer"]]
        array = np.ndarray((accessor["count"], width), dtype, blob, start, (stride, dtype.itemsize))
        return np.array(array)

    def local_matrix(node: dict) -> np.ndarray:
        if "matrix" in node:
            return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
        m = np.eye(4)
        x, y, z, w = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
        rotation = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        m[:3, :3] = rotation * np.asarray(node.get("scale", [1.0, 1.0, 1.0]))
        m[:3, 3] = node.get("translation", [0.0, 0.0, 0.0])
        return m

    positions: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    colours: list[np.ndarray] = []
    base = 0

    def visit(index: int, parent: np.ndarray) -> None:
        nonlocal base
        node = document["nodes"][index]
        world = parent @ local_matrix(node)
        if "mesh" in node:
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                if primitive.get("mode", 4) != 4:
                    continue  # only triangle lists
                points = read(primitive["attributes"]["POSITION"]).astype(np.float64)
                points = points @ world[:3, :3].T + world[:3, 3]
                if "indices" in primitive:
                    tri = read(primitive["indices"]).reshape(-1, 3).astype(np.int32)
                else:
                    tri = np.arange(len(points), dtype=np.int32).reshape(-1, 3)
                material = document.get("materials", [{}])[primitive.get("material", 0)] if document.get("materials") else {}
                factor = material.get("pbrMetallicRoughness", {}).get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
                positions.append(points.astype(np.float32))
                faces.append(tri + base)
                colours.append(np.tile(np.asarray(factor[:3], dtype=np.float32), (len(tri), 1)))
                base += len(points)
        for child in node.get("children", []):
            visit(child, world)

    scene = document.get("scenes", [{"nodes": list(range(len(document.get("nodes", []))))}])[document.get("scene", 0)]
    for root in scene.get("nodes", []):
        visit(root, np.eye(4))
    if not positions:
        raise ModelError("The glTF file has no triangle meshes. (Models made of lines or points cannot be used.)")
    return Mesh(np.concatenate(positions), np.concatenate(faces), np.concatenate(colours))


# tidying
_PREPARED: dict[tuple, Mesh] = {}


def load_prepared(path: str | Path, flip: bool = False) -> Mesh:
    """load_mesh + normalize, remembered per file (and its modified time) and flip, so a big model is thinned out only once:
    the panel and the bar both ask for it, and the bar asks again every time any setting changes."""
    path = Path(path)
    try:
        stamp = path.stat().st_mtime_ns
    except OSError as exc:
        raise ModelError(f"Could not read the file: {exc}") from exc
    key = (str(path), stamp, bool(flip))
    mesh = _PREPARED.get(key)
    if mesh is None:
        mesh = normalize(load_mesh(path), flip=flip)
        _PREPARED.clear()  # only the model in use is worth keeping
        _PREPARED[key] = mesh
    return mesh


def normalize(mesh: Mesh, flip: bool = False, max_triangles: int = DEFAULT_MAX_TRIANGLES) -> Mesh:
    """Centre the model, stand its long axis along +Y nose up, scale it to one unit long, and thin it out."""
    vertices = mesh.vertices.astype(np.float64)
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    axis = int(np.argmax(high - low))
    permutation = {0: (2, 0, 1), 1: (0, 1, 2), 2: (1, 2, 0)}[axis]  # cyclic, so handedness is kept
    vertices = vertices[:, permutation]
    vertices -= (vertices.min(axis=0) + vertices.max(axis=0)) / 2
    length = vertices[:, 1].max() - vertices[:, 1].min()
    if length <= 0:
        raise ModelError("The model has no size.")
    vertices /= length

    # The nose is the narrower end. Compare how far the vertices stray from the axis right at each end.
    radial = np.hypot(vertices[:, 0], vertices[:, 2])
    top, bottom = vertices[:, 1] > 0.45, vertices[:, 1] < -0.45  # the very tips: a pointed nose is far narrower there than an engine end
    top_width = radial[top].mean() if top.any() else 0.0
    bottom_width = radial[bottom].mean() if bottom.any() else 0.0
    if top_width > bottom_width:
        vertices[:, [0, 1]] *= -1  # turn it over about the Z axis so the narrow end is up
    if flip:
        vertices[:, [0, 1]] *= -1

    result = Mesh(vertices.astype(np.float32), mesh.faces, mesh.face_colors)
    return decimate(result, max_triangles) if result.triangle_count > max_triangles else result


def decimate(mesh: Mesh, max_triangles: int) -> Mesh:
    """Thin a heavy model by merging the vertices that fall in the same cell of a grid, until it is light enough.

    Each merged vertex is not the average of its cell (which pulls a round body in and rounds off its edges) but the point that
    stays closest to all the surfaces that met in the cell, found from their planes (vertex clustering with the quadric error)."""
    vertices = mesh.vertices.astype(np.float64)
    faces = mesh.faces.astype(np.int64)
    count = len(vertices)
    low = vertices.min(axis=0)
    span = float(max(vertices.max(axis=0) - low))

    # the plane of every face, as a 4x4 symmetric matrix (ten numbers) weighted by its area, handed to its three corners
    corners = vertices[faces]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    double_area = np.linalg.norm(cross, axis=1)
    safe = np.where(double_area > 0, double_area, 1.0)
    normal = cross / safe[:, None]
    offset = -np.einsum("ij,ij->i", normal, corners[:, 0])
    plane = np.column_stack([normal, offset])
    pairs = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 1), (1, 2), (1, 3), (2, 2), (2, 3), (3, 3)]
    weight = double_area / 2.0
    vertex_quadric = np.zeros((count, 10))
    for slot, (r, c) in enumerate(pairs):
        face_value = plane[:, r] * plane[:, c] * weight
        for corner in range(3):
            vertex_quadric[:, slot] += np.bincount(faces[:, corner], weights=face_value, minlength=count)

    best = mesh
    for cells in (128, 96, 72, 56, 44, 34, 26, 20, 16, 12):
        size = span / cells
        grid = np.floor((vertices - low) / size).astype(np.int64)
        key = (grid[:, 0] * (cells + 2) + grid[:, 1]) * (cells + 2) + grid[:, 2]
        _, inverse, counts = np.unique(key, return_inverse=True, return_counts=True)
        inverse = inverse.reshape(-1)
        cell_count = len(counts)
        mean = np.column_stack([np.bincount(inverse, weights=vertices[:, axis], minlength=cell_count) for axis in range(3)]) / counts[:, None]
        q = np.column_stack([np.bincount(inverse, weights=vertex_quadric[:, slot], minlength=cell_count) for slot in range(10)])
        a = np.empty((cell_count, 3, 3))
        a[:, 0, 0], a[:, 0, 1], a[:, 0, 2] = q[:, 0], q[:, 1], q[:, 2]
        a[:, 1, 0], a[:, 1, 1], a[:, 1, 2] = q[:, 1], q[:, 4], q[:, 5]
        a[:, 2, 0], a[:, 2, 1], a[:, 2, 2] = q[:, 2], q[:, 5], q[:, 7]
        b = np.column_stack([q[:, 3], q[:, 6], q[:, 8]])
        pull = 0.02 * (a[:, 0, 0] + a[:, 1, 1] + a[:, 2, 2]) / 3.0 + 1e-12  # a gentle pull toward the average, so a flat patch stays put
        a += pull[:, None, None] * np.eye(3)
        merged = np.linalg.solve(a, (-b + pull[:, None] * mean)[:, :, None])[:, :, 0]
        merged = np.clip(merged, mean - size, mean + size)  # never further than a cell from where the vertices were
        remapped = inverse[faces]
        alive = (remapped[:, 0] != remapped[:, 1]) & (remapped[:, 1] != remapped[:, 2]) & (remapped[:, 0] != remapped[:, 2])
        keep = np.flatnonzero(alive)
        ordered = np.sort(remapped[keep], axis=1)
        face_key = (ordered[:, 0] * cell_count + ordered[:, 1]) * cell_count + ordered[:, 2]
        _, first = np.unique(face_key, return_index=True)  # drop faces that became copies of each other
        keep = keep[np.sort(first)]
        best = Mesh(
            merged.astype(np.float32),
            remapped[keep].astype(np.int32),
            None if mesh.face_colors is None else mesh.face_colors[keep],
        )
        if best.triangle_count <= max_triangles:
            break
    return best


# the model used when none is chosen
def builtin_rocket(segments: int = 20) -> Mesh:
    """A stacked rocket: a dark ship with a pointed nose and flaps on a light booster with grid fins."""
    ship = (0.50, 0.54, 0.60)  # dark metal, light enough to read against the dial's dark disc
    rings: list[tuple[float, float, tuple[float, float, float]]] = [  # (height, radius, colour)
        (0.50, 0.000, ship),
        (0.44, 0.030, ship),
        (0.36, 0.052, ship),
        (0.26, 0.062, ship),
        (0.04, 0.062, ship),
        (0.04, 0.062, (0.88, 0.90, 0.92)),
        (-0.46, 0.062, (0.88, 0.90, 0.92)),
        (-0.50, 0.050, (0.40, 0.43, 0.47)),
    ]
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    colours: list[tuple[float, float, float]] = []
    ring_start = []
    for height, radius, _ in rings:
        ring_start.append(len(vertices))
        for k in range(segments):
            angle = 2 * np.pi * k / segments
            vertices.append((radius * np.cos(angle), height, radius * np.sin(angle)))
    for r in range(len(rings) - 1):
        colour = rings[r + 1][2]
        for k in range(segments):
            a, b = ring_start[r] + k, ring_start[r] + (k + 1) % segments
            c, d = ring_start[r + 1] + k, ring_start[r + 1] + (k + 1) % segments
            faces += [(a, c, b), (b, c, d)]
            colours += [colour, colour]
    bottom = len(vertices)
    vertices.append((0.0, -0.5, 0.0))
    for k in range(segments):
        faces.append((bottom, ring_start[-1] + (k + 1) % segments, ring_start[-1] + k))
        colours.append((0.28, 0.30, 0.33))

    def fin(side_x: float, side_z: float, top: float, depth: float, reach: float, colour) -> None:
        base = len(vertices)
        vertices.extend(
            [
                (side_x * 0.062, top, side_z * 0.062),
                (side_x * (0.062 + reach), top - depth * 0.3, side_z * (0.062 + reach)),
                (side_x * (0.062 + reach), top - depth, side_z * (0.062 + reach)),
                (side_x * 0.062, top - depth, side_z * 0.062),
            ]
        )
        faces.extend([(base, base + 1, base + 2), (base, base + 2, base + 3), (base, base + 2, base + 1), (base, base + 3, base + 2)])
        colours.extend([colour] * 4)

    for sx, sz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        fin(sx, sz, 0.00, 0.07, 0.05, (0.45, 0.48, 0.52))  # grid fins just below the join
    for sx, sz in ((1, 0), (-1, 0)):
        fin(sx, sz, 0.20, 0.17, 0.07, (0.40, 0.43, 0.48))  # the ship's flaps
        fin(sx, sz, 0.38, 0.08, 0.05, (0.40, 0.43, 0.48))
    return Mesh(np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.int32), np.asarray(colours, dtype=np.float32))
