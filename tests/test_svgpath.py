from engine.svgpath import (
    parse_path, scale_segments, segments_to_d, segments_to_polyline,
    translate_segments, rotate_segments_90, bounding_box, normalize_hv,
)


def test_parse_and_serialize_round_trip():
    d = "M 0 0 L 10 0 L 10 10 L 0 10 Z"
    segs = parse_path(d)
    assert segs[0] == ("M", [0.0, 0.0])
    assert segs[-1] == ("Z", [])
    assert segments_to_d(segs) == "M 0.000 0.000 L 10.000 0.000 L 10.000 10.000 L 0.000 10.000 Z"


def test_scale_segments_scales_each_axis_independently():
    segs = parse_path("M 2 3 L 4 5 H 8 V 9")
    scaled = scale_segments(segs, rx=2.0, ry=3.0)
    assert scaled[0] == ("M", [4.0, 9.0])
    assert scaled[1] == ("L", [8.0, 15.0])
    assert scaled[2] == ("H", [16.0])  # H only touches X
    assert scaled[3] == ("V", [27.0])  # V only touches Y


def test_bounding_box_of_square():
    segs = parse_path("M 0 0 L 10 0 L 10 5 L 0 5 Z")
    assert bounding_box(segs) == (0.0, 0.0, 10.0, 5.0)


def test_translate_segments_moves_all_points():
    segs = parse_path("M 0 0 L 10 0 H 20 V 30 Z")
    moved = translate_segments(segs, dx=5, dy=7)
    assert moved[0] == ("M", [5.0, 7.0])
    assert moved[1] == ("L", [15.0, 7.0])
    assert moved[2] == ("H", [25.0])
    assert moved[3] == ("V", [37.0])


def test_normalize_hv_expands_to_absolute_lines():
    segs = parse_path("M 1 1 H 5 V 9")
    norm = normalize_hv(segs)
    assert norm == [("M", [1.0, 1.0]), ("L", [5.0, 1.0]), ("L", [5.0, 9.0])]


def test_rotate_segments_90_preserves_shape_size():
    # 10x5の矩形を回転すると5x10になる（面積は同じ、辺の長さが入れ替わる）
    segs = parse_path("M 0 0 L 10 0 L 10 5 L 0 5 Z")
    rotated = rotate_segments_90(segs)
    min_x, min_y, max_x, max_y = bounding_box(rotated)
    assert round(max_x - min_x, 6) == 5.0
    assert round(max_y - min_y, 6) == 10.0


def test_segments_to_polyline_flattens_curves():
    segs = parse_path("M 0 0 C 0 10, 10 10, 10 0")
    points = segments_to_polyline(segs, curve_steps=4)
    assert points[0] == (0.0, 0.0)
    assert points[-1] == (10.0, 0.0)
    assert len(points) == 1 + 4  # 始点 + 4分割点
