import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ground_station.attitude import compass_point, rocket_view
from ground_station.mesh import builtin_rocket
from ground_station.render3d import ModelRenderer, body_to_world, view_matrix


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def opaque_pixels(image) -> int:
    return sum(1 for y in range(0, image.height(), 3) for x in range(0, image.width(), 3) if image.pixelColor(x, y).alpha() > 0)


def test_view_matrix_is_a_rotation():
    m = view_matrix()
    assert np.allclose(m @ m.T, np.eye(3))
    assert np.linalg.det(m) == pytest.approx(-1.0)  # right, up, away: a mirror of east-north-up, as expected


def test_the_noses_screen_direction_matches_the_flat_attitude_maths():
    for pitch, heading in ((90.0, 0.0), (45.0, 90.0), (30.0, 250.0), (10.0, 10.0)):
        nose_world = body_to_world(pitch, heading, 0.0)[:, 1]
        x, y, _ = view_matrix() @ nose_world
        expected = rocket_view(pitch, heading)
        assert math.degrees(math.atan2(x, y)) == pytest.approx(expected.angle_deg, abs=1e-6)


def test_body_axes_are_orthonormal_and_roll_turns_about_the_nose():
    plain, rolled = body_to_world(40.0, 120.0, 0.0), body_to_world(40.0, 120.0, 55.0)
    for matrix in (plain, rolled):
        assert np.allclose(matrix.T @ matrix, np.eye(3))
    assert np.allclose(plain[:, 1], rolled[:, 1])  # the nose does not move when it rolls
    assert not np.allclose(plain[:, 0], rolled[:, 0])


def test_straight_up_has_a_defined_orientation():
    matrix = body_to_world(90.0, 135.0, 0.0)
    assert np.allclose(matrix.T @ matrix, np.eye(3))
    assert np.allclose(matrix[:, 1], [0, 0, 1])


def test_rendering_draws_something_and_caches_by_degree():
    renderer = ModelRenderer(builtin_rocket(), 120)
    first = renderer.render(80.0, 90.0, 0.0)
    assert first.width() == 240 and opaque_pixels(first) > 200  # drawn at twice the size for smooth edges
    assert renderer.render(80.2, 90.4, 0.0) is first  # the same degree gives the same picture
    assert renderer.render(60.0, 90.0, 0.0) is not first


def test_different_attitudes_look_different():
    renderer = ModelRenderer(builtin_rocket(), 120)
    upright, leaning, rolled = renderer.render(90, 90, 0), renderer.render(30, 90, 0), renderer.render(90, 90, 90)
    assert upright != leaning
    assert upright != rolled  # the built-in rocket has fins, so rolling it changes the picture


def two_tone_stick():
    """A thin flat stick, red on the nose half and blue on the tail half, to see where the nose goes."""
    from ground_station.mesh import Mesh

    def quad(y0, y1):
        return [(-0.05, y0, 0.0), (0.05, y0, 0.0), (0.05, y1, 0.0), (-0.05, y1, 0.0)]

    vertices = np.array(quad(0.0, 0.5) + quad(-0.5, 0.0), dtype=np.float32)
    faces = np.array([(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7)], dtype=np.int32)
    colours = np.array([(1, 0.1, 0.1)] * 2 + [(0.1, 0.1, 1)] * 2, dtype=np.float32)
    return Mesh(vertices, faces, colours)


def centroids(image):
    red, blue = [], []
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            if c.alpha() > 200:
                (red if c.red() > c.blue() else blue).append((x, y))
    mean = lambda points: np.mean(points, axis=0)
    return mean(red), mean(blue)


@pytest.mark.parametrize(
    "pitch, heading, axis, sign",
    [
        (90.0, 0.0, 1, -1),  # standing up: the nose half is higher on the screen (smaller y)
        (15.0, 90.0, 0, +1),  # nearly flat heading east: the nose half is to the right
        (15.0, 270.0, 0, -1),  # heading west: to the left
    ],
)
def test_the_nose_end_goes_where_the_vessel_points(pitch, heading, axis, sign):
    renderer = ModelRenderer(two_tone_stick(), 100)
    nose, tail = centroids(renderer.render(pitch, heading, 0.0))
    assert sign * (nose[axis] - tail[axis]) > 10


def test_the_bar_takes_a_model_file_and_falls_back_when_it_is_bad(tmp_path):
    from ground_station.bar import TelemetryBar

    bar = TelemetryBar()
    builtin = bar.model_triangles
    model = tmp_path / "stick.obj"
    model.write_text("v -0.1 0 0\nv 0.1 0 0\nv 0 0 0.1\nv 0 1 0\nf 1 2 4\nf 2 3 4\nf 3 1 4\nf 1 3 2\n")
    assert bar.set_vessel_model(str(model)) is None and bar.model_triangles == 4
    problem = bar.set_vessel_model(str(tmp_path / "missing.glb"))
    assert problem and "Could not read" in problem
    assert bar.model_triangles == builtin  # the built-in rocket is back in place
    assert bar.set_vessel_model("") is None


def test_a_thousand_triangle_model_renders_quickly():
    import time

    from ground_station.mesh import Mesh

    rng = np.random.default_rng(3)
    mesh = Mesh(rng.random((1500, 3)).astype(np.float32) - 0.5, rng.integers(0, 1500, (2200, 3)).astype(np.int32))
    renderer = ModelRenderer(mesh, 120)
    start = time.perf_counter()
    renderer.render(33.0, 77.0, 0.0)
    assert time.perf_counter() - start < 0.5


def test_separation_animation_drops_the_booster_and_ends_on_the_ship_alone():
    from ground_station.mesh import builtin_rocket
    from ground_station.render3d import SHIP_SHARE_OF_DIAL, ModelRenderer

    renderer = ModelRenderer(builtin_rocket(), 120)

    def height_used(image):
        rows = [y for y in range(image.height()) if any(image.pixelColor(x, y).alpha() > 40 for x in range(0, image.width(), 2))]
        return (rows[-1] - rows[0]) / image.height() if rows else 0.0

    whole = renderer.render(90.0, 0.0, 0.0, 0.0)  # standing upright, nothing separated
    middle = renderer.render(90.0, 0.0, 0.0, 0.5)
    ship_only = renderer.render(90.0, 0.0, 0.0, 1.0)
    assert whole.size() == middle.size() == ship_only.size()
    assert height_used(whole) > 0.9  # the stack fills the picture
    assert height_used(ship_only) == pytest.approx(0.97 * SHIP_SHARE_OF_DIAL, abs=0.05)  # the lone ship is smaller, not blown up
    assert renderer.render(90.0, 0.0, 0.0, 0.0) is whole  # cached, and the animation steps are cached separately
    assert middle is not whole
    assert renderer.render(90.0, 0.0, 0.0, 1.7) is ship_only  # beyond the end is just the finished state


def test_the_bar_shows_the_starship_unless_asked_for_the_dummy_rocket(tmp_path):
    from ground_station.bar import TelemetryBar
    from ground_station.mesh import builtin_rocket
    from ground_station.starship_model import starship_stack

    bar = TelemetryBar()
    assert bar.set_vessel_model("", False, starship=True) is None and bar.model_triangles == starship_stack().triangle_count
    assert bar.set_vessel_model("", False, starship=False) is None and bar.model_triangles == builtin_rocket().triangle_count
    model = tmp_path / "own.obj"
    model.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 2 3\nf 1 2 4\nf 2 3 4\nf 1 3 4\n")
    assert bar.set_vessel_model(str(model), False, starship=True) is None and bar.model_triangles == 4  # the user's own model wins
    assert bar.set_vessel_model(str(tmp_path / "missing.glb"), False, starship=True)  # a bad file falls back, and says why
    assert bar.model_triangles == starship_stack().triangle_count


def test_the_starship_renders_standing_and_separating():
    from ground_station.starship_model import starship_stack

    renderer = ModelRenderer(starship_stack(), 120)
    whole = renderer.render(0, 0, 0)
    assert not whole.isNull() and whole.width() > 0
    ship_only = renderer.render(0, 0, 0, separation=1.0)
    assert not ship_only.isNull()


def two_coloured_cylinder(segments: int = 24):
    """A closed tube round the Y axis: red on its +Z side, blue on its -Z side."""
    from ground_station.mesh import Mesh

    heights, radius = (-0.4, 0.4), 0.1
    vertices = [(radius * math.cos(2 * math.pi * k / segments), y, radius * math.sin(2 * math.pi * k / segments)) for y in heights for k in range(segments)]
    faces, colours = [], []
    for k in range(segments):
        a, b, c, d = k, (k + 1) % segments, segments + k, segments + (k + 1) % segments
        faces += [(a, c, b), (b, c, d)]
        middle = 2 * math.pi * (k + 0.5) / segments
        colours += [(1.0, 0.0, 0.0) if math.sin(middle) > 0 else (0.0, 0.0, 1.0)] * 2
    return Mesh(
        np.asarray(vertices, dtype=np.float32),
        np.asarray(faces, dtype=np.int32),
        np.asarray(colours, dtype=np.float32),
        solid=np.ones(len(faces), dtype=bool),
    )


def axes_with_top_facing_the_viewer(toward: bool) -> np.ndarray:
    """Model axes (right, nose, top) with the model's +Z side turned at the camera, or straight away from it."""
    top = -view_matrix()[2] * (1.0 if toward else -1.0)  # view z grows away from the viewer
    up = np.array([0.0, 0.0, 1.0])
    nose = up - top * float(up @ top)
    nose /= np.linalg.norm(nose)
    return np.column_stack([np.cross(nose, top), nose, top])


@pytest.mark.parametrize("toward, colour", [(True, "red"), (False, "blue")])
def test_a_closed_body_shows_the_side_facing_the_camera_not_the_far_inside_wall(toward, colour):
    """The view is a mirror image of the world, which once made the hidden-face test keep the far wall and drop the near one."""
    renderer = ModelRenderer(two_coloured_cylinder(), 200)
    image = renderer.render_matrix(axes_with_top_facing_the_viewer(toward))
    pixel = image.pixelColor(image.width() // 2, image.height() // 2)
    assert pixel.alpha() > 0
    seen = {"red": pixel.red() > pixel.blue() + 60, "blue": pixel.blue() > pixel.red() + 60}
    assert seen[colour], (pixel.red(), pixel.green(), pixel.blue())


def test_hiding_the_far_side_leaves_no_holes_in_the_starship():
    from ground_station.mesh import Mesh
    from ground_station.starship_model import starship_stack

    mesh = starship_stack()
    plain = Mesh(mesh.vertices, mesh.faces, mesh.face_colors, mesh.stage_split, None)
    with_culling, without = ModelRenderer(mesh, 160), ModelRenderer(plain, 160)

    def coverage(renderer, axes, separation):
        image = renderer.render_matrix(axes, separation)
        return np.array([[image.pixelColor(x, y).alpha() > 30 for x in range(0, 160, 2)] for y in range(0, 160, 2)])

    for pitch, heading, roll, separation in ((90, 0, 0, 0.0), (35, 120, 20, 0.0), (-50, 250, 70, 0.0), (50, 100, 20, 0.5), (50, 100, 20, 1.0)):
        axes = body_to_world(pitch, heading, roll)
        assert (coverage(with_culling, axes, separation) != coverage(without, axes, separation)).mean() < 0.01


def test_the_heat_shield_faces_the_dial_when_the_vessel_stands_on_the_pad(monkeypatch):
    """Recorded on the user's Starship on the pad: kRPC's vessel axes were x west, y up and z, which it calls the bottom, south."""
    from ground_station import starship_model
    from ground_station.attitude import attitude_from_rotation

    monkeypatch.setattr(starship_model, "TILE", np.array([1.0, 0.0, 0.0]))  # the heat shield
    monkeypatch.setattr(starship_model, "SHIP_STEEL", np.array([0.0, 0.0, 1.0]))  # the stainless back
    pitch, heading, roll = attitude_from_rotation((0.5001, 0.4987, -0.5, 0.5012))
    image = ModelRenderer(starship_model.starship_stack(), 300).render_matrix(body_to_world(pitch, heading, roll))
    reds = blues = 0
    for y in range(0, 300, 2):
        for x in range(0, 300, 2):
            c = image.pixelColor(x, y)
            reds += c.alpha() > 200 and c.red() > c.blue() + 60
            blues += c.alpha() > 200 and c.blue() > c.red() + 60
    assert reds > 5 * max(blues, 1), (reds, blues)  # the black belly toward the viewer, only a sliver of steel at the edge
