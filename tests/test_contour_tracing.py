"""engine/segmentation.py の trace_boundary_pixels (Moore-neighbor tracing、
round9で追加)のテスト。カスタムパーツ機能の「画像から自動抽出」の根幹となる
輪郭追跡アルゴリズムを、既知の形状の合成マスクで検証する。
"""

import numpy as np
import pytest
import shapely.geometry as sg

from engine.segmentation import trace_boundary_pixels


def _polygon_from_boundary(boundary):
    return sg.Polygon(boundary)


def test_returns_none_for_empty_mask():
    mask = np.zeros((10, 10), dtype=bool)
    assert trace_boundary_pixels(mask) is None


def test_returns_none_for_single_pixel():
    mask = np.zeros((10, 10), dtype=bool)
    mask[5, 5] = True
    assert trace_boundary_pixels(mask) is None


def test_traces_solid_square_with_correct_area():
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:15, 5:15] = True  # 10x10の正方形(100ピクセル)
    boundary = trace_boundary_pixels(mask)
    assert boundary is not None
    poly = _polygon_from_boundary(boundary)
    assert poly.is_valid
    # ピクセル中心を頂点とする輪郭なので、正確に100にはならないが
    # 10x10前後(81〜121程度)の妥当な範囲に収まるはず。
    assert 70 <= poly.area <= 130


def test_traces_rectangle_with_correct_aspect_ratio():
    mask = np.zeros((30, 60), dtype=bool)
    mask[5:25, 10:50] = True  # 縦20 x 横40の長方形
    boundary = trace_boundary_pixels(mask)
    assert boundary is not None
    xs = [p[0] for p in boundary]
    ys = [p[1] for p in boundary]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    assert width == pytest.approx(40, abs=2)
    assert height == pytest.approx(20, abs=2)


def test_traces_l_shape_without_bridging_the_concave_notch():
    # L字型(凹型): 右上の10x10の切り欠きがある20x20のマスク。
    mask = np.zeros((20, 20), dtype=bool)
    mask[0:20, 0:20] = True
    mask[0:10, 10:20] = False  # 右上をくり抜く
    boundary = trace_boundary_pixels(mask)
    assert boundary is not None
    poly = _polygon_from_boundary(boundary)
    assert poly.is_valid
    # L字の面積は20*20 - 10*10 = 300。ピクセル中心ベースの近似なので
    # ある程度の誤差を許容する。
    assert 250 <= poly.area <= 350
    # 凹みが埋まって単純な正方形(面積400近く)になっていないことを確認する
    # (=くり抜いた切り欠きが輪郭に正しく反映されている)。
    assert poly.area < 380


def test_traces_diamond_shape():
    # ひし形(45度回転した正方形)。斜めの直線的な境界でも正しく1周できるか
    # を確認する。
    size = 21
    mask = np.zeros((size, size), dtype=bool)
    center = size // 2
    for y in range(size):
        for x in range(size):
            if abs(x - center) + abs(y - center) <= center - 2:
                mask[y, x] = True
    boundary = trace_boundary_pixels(mask)
    assert boundary is not None
    poly = _polygon_from_boundary(boundary)
    assert poly.is_valid
    assert poly.area > 0


def test_boundary_forms_a_closed_ring_without_gaps():
    # 追跡した輪郭上の隣接点同士が常に8近傍以内(離れすぎていない)である
    # ことを確認する(輪郭が「飛び地」を作らず連続していることの検証)。
    mask = np.zeros((25, 25), dtype=bool)
    mask[3:22, 3:22] = True
    boundary = trace_boundary_pixels(mask)
    assert boundary is not None
    for i in range(len(boundary)):
        x0, y0 = boundary[i]
        x1, y1 = boundary[(i + 1) % len(boundary)]
        assert max(abs(x1 - x0), abs(y1 - y0)) <= 1
