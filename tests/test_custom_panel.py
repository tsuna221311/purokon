"""engine/custom_panel.py のテスト。round9で追加した「定型に当てはまらない
自由形状パーツ」機能の中核ロジック(校正・多角形化・ミラー)を検証する。"""

import pytest

from engine.custom_panel import (
    CustomPanelError,
    calibrate_points_to_cm,
    mirror_points_x,
    points_to_segments,
    resolve_reference_cm,
    validate_label,
    validate_quantity,
)
from engine.measurements import Measurements
from engine.svgpath import bounding_box


STANDARD = Measurements(bust=84, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)


def _square_px(side=100.0):
    # (0,0)-(side,0)-(side,side)-(0,side) の正方形(ピクセル座標のつもり)。
    return [(0, 0), (side, 0), (side, side), (0, side)]


def test_calibrate_points_to_cm_scales_proportionally():
    # 参照線100px = 40cm なら、100pxの正方形は40cm四方になるはず。
    points = _square_px(100.0)
    cm_points = calibrate_points_to_cm(points, (0, 0), (100, 0), reference_cm=40.0)
    min_x, min_y, max_x, max_y = bounding_box([("M", list(cm_points[0]))] +
                                               [("L", list(p)) for p in cm_points[1:]] + [("Z", [])])
    assert max_x - min_x == pytest.approx(40.0, abs=0.01)
    assert max_y - min_y == pytest.approx(40.0, abs=0.01)


def test_calibrate_points_to_cm_normalizes_to_origin():
    points = [(50, 50), (150, 50), (150, 150), (50, 150)]
    cm_points = calibrate_points_to_cm(points, (50, 50), (150, 50), reference_cm=20.0)
    assert min(p[0] for p in cm_points) == pytest.approx(0.0, abs=1e-6)
    assert min(p[1] for p in cm_points) == pytest.approx(0.0, abs=1e-6)


def test_calibrate_rejects_too_few_points():
    with pytest.raises(CustomPanelError):
        calibrate_points_to_cm([(0, 0), (1, 1)], (0, 0), (10, 0), reference_cm=10.0)


def test_calibrate_rejects_near_zero_reference_distance():
    with pytest.raises(CustomPanelError):
        calibrate_points_to_cm(_square_px(), (0, 0), (0.5, 0), reference_cm=10.0)


def test_calibrate_rejects_reference_cm_out_of_range():
    with pytest.raises(CustomPanelError):
        calibrate_points_to_cm(_square_px(), (0, 0), (100, 0), reference_cm=0.01)
    with pytest.raises(CustomPanelError):
        calibrate_points_to_cm(_square_px(), (0, 0), (100, 0), reference_cm=10000.0)


def test_calibrate_rejects_result_too_small():
    # 参照線100px=0.5cmなら、100pxの正方形も0.5cm四方にしかならず小さすぎる。
    with pytest.raises(CustomPanelError):
        calibrate_points_to_cm(_square_px(100.0), (0, 0), (100, 0), reference_cm=0.5)


def test_calibrate_rejects_result_too_large():
    # 参照線10px=300cmなら、1000pxの正方形は30000cm四方になり大きすぎる。
    with pytest.raises(CustomPanelError):
        calibrate_points_to_cm(_square_px(1000.0), (0, 0), (10, 0), reference_cm=300.0)


def test_calibrate_rejects_malformed_points():
    with pytest.raises(CustomPanelError):
        calibrate_points_to_cm("not-a-list", (0, 0), (100, 0), reference_cm=10.0)
    with pytest.raises(CustomPanelError):
        calibrate_points_to_cm([{"x": "abc", "y": 0}] * 4, (0, 0), (100, 0), reference_cm=10.0)


def test_calibrate_accepts_dict_shaped_points():
    points = [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}, {"x": 0, "y": 100}]
    cm_points = calibrate_points_to_cm(points, {"x": 0, "y": 0}, {"x": 100, "y": 0}, reference_cm=40.0)
    assert len(cm_points) == 4


def test_resolve_reference_cm_from_manual_value():
    assert resolve_reference_cm(40.0, None, None) == 40.0


def test_resolve_reference_cm_from_measurement_field():
    assert resolve_reference_cm(None, "shoulder_width", STANDARD) == STANDARD.shoulder_width


def test_resolve_reference_cm_rejects_missing_both():
    with pytest.raises(CustomPanelError):
        resolve_reference_cm(None, None, STANDARD)


def test_resolve_reference_cm_rejects_unknown_measurement_field():
    with pytest.raises(CustomPanelError):
        resolve_reference_cm(None, "not-a-real-field", STANDARD)


def test_resolve_reference_cm_rejects_out_of_range_manual_value():
    with pytest.raises(CustomPanelError):
        resolve_reference_cm(0.001, None, None)


def test_points_to_segments_produces_closed_polygon():
    cm_points = [(0, 0), (10, 0), (10, 10), (0, 10)]
    segments = points_to_segments(cm_points)
    assert segments[0][0] == "M"
    assert segments[-1][0] == "Z"
    assert all(cmd in ("M", "L", "Z") for cmd, _ in segments)


def test_points_to_segments_repairs_self_intersection():
    # 「蝶ネクタイ」型の自己交差する四角形(bowtie)。shapelyのbuffer(0)で
    # 2つの三角形のうち大きい方に自動修復されるはず(例外にならない)。
    bowtie = [(0, 0), (10, 10), (10, 0), (0, 10)]
    segments = points_to_segments(bowtie)
    assert segments[0][0] == "M"
    assert segments[-1][0] == "Z"


def test_points_to_segments_rejects_too_few_points():
    with pytest.raises(CustomPanelError):
        points_to_segments([(0, 0), (1, 1)])


def test_mirror_points_x_flips_around_own_bounding_box():
    points = [(0, 0), (10, 0), (10, 10), (0, 10)]
    mirrored = mirror_points_x(points)
    xs = sorted(p[0] for p in mirrored)
    assert xs == [0.0, 0.0, 10.0, 10.0]
    # 元のpoints[1]=(10,0)は反転後(0,0)になるはず(左右反転)。
    assert mirrored[1] == (0.0, 0.0)


def test_mirror_points_x_empty_list_is_noop():
    assert mirror_points_x([]) == []


def test_validate_label_strips_and_enforces_length():
    assert validate_label("  マント  ") == "マント"
    with pytest.raises(CustomPanelError):
        validate_label("")
    with pytest.raises(CustomPanelError):
        validate_label("あ" * 41)
    with pytest.raises(CustomPanelError):
        validate_label(None)


def test_validate_quantity_enforces_range():
    assert validate_quantity("3") == 3
    with pytest.raises(CustomPanelError):
        validate_quantity(0)
    with pytest.raises(CustomPanelError):
        validate_quantity(100)
    with pytest.raises(CustomPanelError):
        validate_quantity("not-a-number")
