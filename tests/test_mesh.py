import base64
import json
import struct

import numpy as np
import pytest

from ground_station.mesh import Mesh, ModelError, builtin_rocket, decimate, load_mesh, normalize

CUBE_OBJ = """# a unit cube made of quads
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
v 0 0 1
v 1 0 1
v 1 1 1
v 0 1 1
f 1 2 3 4
f 5 8 7 6
f 1 5 6 2
f 2 6 7 3
f 3 7 8 4
f 4 8 5 1
"""


def test_obj_quads_are_split_into_triangles(tmp_path):
    path = tmp_path / "cube.obj"
    path.write_text(CUBE_OBJ)
    mesh = load_mesh(path)
    assert len(mesh.vertices) == 8 and mesh.triangle_count == 12


def test_obj_with_slashes_and_negative_indices(tmp_path):
    path = tmp_path / "tri.obj"
    path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvn 0 0 1\nf -3/1/1 -2/1/1 -1/1/1\n")
    assert load_mesh(path).faces.tolist() == [[0, 1, 2]]


def test_obj_pointing_at_missing_vertices_is_refused(tmp_path):
    path = tmp_path / "bad.obj"
    path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 9\n")
    with pytest.raises(ModelError, match="do not exist"):
        load_mesh(path)


def test_binary_stl(tmp_path):
    record = struct.pack("<3f9fH", 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)
    path = tmp_path / "one.stl"
    path.write_bytes(b"\0" * 80 + struct.pack("<I", 1) + record)
    mesh = load_mesh(path)
    assert mesh.triangle_count == 1 and mesh.vertices[1].tolist() == [1.0, 0.0, 0.0]


def test_ascii_stl(tmp_path):
    path = tmp_path / "one.stl"
    path.write_text(
        "solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"
    )
    assert load_mesh(path).triangle_count == 1


def test_truncated_binary_stl_is_refused(tmp_path):
    path = tmp_path / "short.stl"
    path.write_bytes(b"\0" * 80 + struct.pack("<I", 5) + b"\0" * 10)
    with pytest.raises(ModelError, match="shorter"):
        load_mesh(path)


def make_glb(with_colour=True) -> bytes:
    positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype="<f4").tobytes()
    indices = np.array([0, 1, 2], dtype="<u2").tobytes() + b"\0\0"
    blob = positions + indices
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "translation": [10.0, 0.0, 0.0]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1.0, 0.0, 0.0, 1.0]}}] if with_colour else [],
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36}, {"buffer": 0, "byteOffset": 36, "byteLength": 6}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
    }
    body = json.dumps(document).encode()
    body += b" " * (-len(body) % 4)
    chunks = struct.pack("<II", len(body), 0x4E4F534A) + body + struct.pack("<II", len(blob), 0x004E4942) + blob
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


def test_glb_positions_node_transform_and_material_colour(tmp_path):
    path = tmp_path / "tri.glb"
    path.write_bytes(make_glb())
    mesh = load_mesh(path)
    assert mesh.triangle_count == 1
    assert mesh.vertices[0].tolist() == [10.0, 0.0, 0.0]  # the node's translation was applied
    assert mesh.face_colors[0].tolist() == [1.0, 0.0, 0.0]


def test_gltf_with_an_embedded_buffer(tmp_path):
    glb = make_glb(with_colour=False)
    json_length = struct.unpack_from("<I", glb, 12)[0]
    document = json.loads(glb[20 : 20 + json_length])
    blob_start = 20 + json_length + 8
    document["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(glb[blob_start:]).decode()
    path = tmp_path / "tri.gltf"
    path.write_text(json.dumps(document))
    assert load_mesh(path).triangle_count == 1


def test_unknown_and_damaged_files_give_a_clear_error(tmp_path):
    with pytest.raises(ModelError, match="Unsupported"):
        load_mesh(tmp_path / "model.fbx")
    broken = tmp_path / "broken.glb"
    broken.write_bytes(b"glTF" + b"\0" * 20)
    with pytest.raises(ModelError):
        load_mesh(broken)
    with pytest.raises(ModelError, match="Could not read"):
        load_mesh(tmp_path / "missing.obj")


def cone_along(axis: int, nose_positive: bool = True, scale: float = 1.0) -> Mesh:
    """A wide base and a pointed tip along the chosen axis, long and thin like a rocket."""
    segments = 12
    ring = [(np.cos(2 * np.pi * k / segments) * 0.2, np.sin(2 * np.pi * k / segments) * 0.2) for k in range(segments)]
    vertices = [(-0.5, a, b) for a, b in ring] + [(0.5, 0.0, 0.0), (-0.5, 0.0, 0.0)]
    faces = []
    for k in range(segments):
        n = (k + 1) % segments
        faces += [(k, n, segments), (k, segments + 1, n)]
    vertices = np.asarray(vertices, dtype=np.float32) * scale
    if not nose_positive:
        vertices[:, 0] *= -1
    order = {0: [0, 1, 2], 1: [2, 0, 1], 2: [1, 2, 0]}[axis]  # put the long axis on X, Y or Z
    return Mesh(vertices[:, order], np.asarray(faces, dtype=np.int32))


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("nose_positive", [True, False])
def test_any_model_ends_up_nose_up_along_y(axis, nose_positive):
    result = normalize(cone_along(axis, nose_positive, scale=37.0))
    v = result.vertices
    assert v[:, 1].max() - v[:, 1].min() == pytest.approx(1.0, abs=1e-5)  # one unit long
    assert np.abs((v.min(axis=0) + v.max(axis=0)) / 2).max() < 1e-5  # centred on the origin
    tip = v[np.argmax(v[:, 1])]
    assert np.hypot(tip[0], tip[2]) < 0.05  # the pointed end is the top


def test_flip_turns_the_model_over():
    normal, flipped = normalize(cone_along(1)), normalize(cone_along(1), flip=True)
    assert normal.vertices[:, 1].argmax() != flipped.vertices[:, 1].argmax() or not np.allclose(normal.vertices, flipped.vertices)
    tip = flipped.vertices[np.argmax(flipped.vertices[:, 1])]
    assert np.hypot(tip[0], tip[2]) > 0.1  # now the wide end is on top


def dense_cylinder(rings: int, segments: int) -> Mesh:
    """A closed-ish tube with rings * segments * 2 triangles, like a finely modelled rocket body."""
    heights = np.linspace(-0.5, 0.5, rings)
    angles = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    vertices = np.array([[0.1 * np.cos(a), h, 0.1 * np.sin(a)] for h in heights for a in angles], dtype=np.float32)
    faces = []
    for r in range(rings - 1):
        for k in range(segments):
            a, b = r * segments + k, r * segments + (k + 1) % segments
            c, d = a + segments, b + segments
            faces += [(a, c, b), (b, c, d)]
    return Mesh(vertices, np.asarray(faces, dtype=np.int32))


def test_heavy_models_are_thinned_to_the_budget_and_keep_their_shape():
    heavy = dense_cylinder(300, 100)
    assert heavy.triangle_count > 50000
    thinned = decimate(heavy, 2200)
    assert 0 < thinned.triangle_count <= 2200
    assert thinned.vertices[:, 1].max() - thinned.vertices[:, 1].min() > 0.8  # still about as tall as before
    assert thinned.faces.max() < len(thinned.vertices)


def test_light_models_are_left_alone():
    mesh = cone_along(1)
    assert normalize(mesh).triangle_count == mesh.triangle_count


def test_decimation_keeps_colours_in_step_with_faces():
    mesh = cone_along(1, scale=3.0)
    mesh.face_colors = np.random.default_rng(2).random((mesh.triangle_count, 3)).astype(np.float32)
    thinned = decimate(mesh, 8)
    assert thinned.face_colors is not None and len(thinned.face_colors) == thinned.triangle_count


def test_builtin_rocket_is_ready_to_draw():
    mesh = builtin_rocket()
    assert mesh.face_colors is not None and len(mesh.face_colors) == mesh.triangle_count
    assert mesh.vertices[:, 1].max() == pytest.approx(0.5) and mesh.vertices[:, 1].min() == pytest.approx(-0.5)
    assert mesh.faces.max() < len(mesh.vertices)


def test_starship_stack_is_ready_to_draw_and_split_where_the_ship_meets_the_booster():
    from ground_station.starship_model import SHIP_LENGTH, SPLIT_Y, starship_stack

    mesh = starship_stack()
    assert mesh.vertices.shape[1] == 3 and mesh.faces.max() < len(mesh.vertices) and mesh.faces.min() >= 0
    assert len(mesh.face_colors) == mesh.triangle_count and mesh.triangle_count < 2200
    assert mesh.vertices[:, 1].max() == pytest.approx(0.5) and mesh.vertices[:, 1].min() == pytest.approx(-0.5)
    assert mesh.stage_split == pytest.approx(SPLIT_Y) and SPLIT_Y == pytest.approx(0.5 - SHIP_LENGTH)
    assert np.abs(mesh.vertices[:, [0, 2]]).max() < 0.2  # slim, centred on the axis, fins included
    assert (mesh.face_colors >= 0).all() and (mesh.face_colors <= 1).all()
    # the nose comes to a point and the booster's engines end in a closed skirt
    assert np.hypot(*mesh.vertices[mesh.vertices[:, 1] > 0.499][:, [0, 2]].T).max() == pytest.approx(0.0)


def test_the_ship_is_the_part_above_the_split():
    from ground_station.render3d import ModelRenderer
    from ground_station.starship_model import SPLIT_Y, starship_stack

    mesh = starship_stack()
    renderer = ModelRenderer(mesh, 100)
    heights = mesh.vertices[mesh.faces][:, :, 1].mean(axis=1)
    assert (renderer._is_booster == (heights < SPLIT_Y)).all()
    assert renderer._is_booster.sum() > 100 and (~renderer._is_booster).sum() > 100
    assert renderer._ship_zoom == pytest.approx(0.6 / (0.5 - SPLIT_Y))


def test_the_ship_flaps_are_joined_to_the_body_not_floating():
    from ground_station.starship_model import NOSE_SHARE, SHIP_LENGTH, _body_radius, starship_stack

    mesh = starship_stack()
    top = 0.5 - 0.115 * SHIP_LENGTH  # where the forward flaps' roots start, on the narrowing nose
    assert top > 0.5 - NOSE_SHARE * SHIP_LENGTH
    roots = mesh.vertices[np.isclose(mesh.vertices[:, 1], top, atol=1e-6)]
    assert len(roots) == 4  # two flaps, two faces each
    assert (np.hypot(roots[:, 0], roots[:, 2]) <= _body_radius(top) + 1e-4).all()  # inside the nose, not beside it


def test_the_booster_has_three_grid_fins_and_none_on_the_steel_side():
    from ground_station.starship_model import BODY_RADIUS, HOT_STAGE_HEIGHT, SPLIT_Y, TILE_CENTRE, starship_stack

    mesh = starship_stack()
    level = SPLIT_Y - HOT_STAGE_HEIGHT - 0.040
    fins = mesh.vertices[(np.abs(mesh.vertices[:, 1] - level) < 0.01) & (np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 2]) > BODY_RADIUS * 1.1)]
    angles = np.degrees(np.arctan2(fins[:, 2], fins[:, 0])) % 360
    shield = np.degrees(TILE_CENTRE) % 360
    away = np.abs((angles - shield + 180) % 360 - 180)  # distance from the heat-shield side
    assert (away < 150).all()  # nothing on the opposite (steel) side
    for turn in (0, 90, -90):
        assert (np.abs((angles - (shield + turn) + 180) % 360 - 180) < 25).any()  # a fin on the shield side and one out to each side
