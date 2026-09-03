"""SimpleSilhouetteSegmenter.auto_trace_outline (round9で追加)のテスト。

trace_boundary_pixels自体の正しさは tests/test_contour_tracing.py で
検証済み。ここでは「画像→前景マスク→輪郭抽出→単純化→元解像度への
逆変換」という一連の流れが実際のPIL画像に対して正しく動くことを確認する。
"""

import pytest
from PIL import Image, ImageDraw

from engine.segmentation import SimpleSilhouetteSegmenter


def _segmenter():
    return SimpleSilhouetteSegmenter()


def test_auto_trace_outline_returns_none_for_blank_image():
    image = Image.new("RGB", (200, 200), "white")
    assert _segmenter().auto_trace_outline(image) is None


def test_auto_trace_outline_returns_none_when_foreground_fills_whole_image():
    image = Image.new("RGB", (100, 100), "black")
    assert _segmenter().auto_trace_outline(image) is None


def test_auto_trace_outline_matches_bounding_box_of_drawn_shape():
    image = Image.new("RGB", (400, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([100, 150, 300, 500], fill="black")
    points = _segmenter().auto_trace_outline(image)
    assert points is not None
    assert len(points) >= 3
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    # 追跡はピクセル中心ベースのため、厳密な境界とは数ピクセルの誤差がある。
    assert min(xs) == pytest.approx(100, abs=3)
    assert max(xs) == pytest.approx(300, abs=3)
    assert min(ys) == pytest.approx(150, abs=3)
    assert max(ys) == pytest.approx(500, abs=3)


def test_auto_trace_outline_respects_alpha_transparency():
    image = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([50, 50, 250, 250], fill=(10, 20, 30, 255))
    points = _segmenter().auto_trace_outline(image)
    assert points is not None
    assert len(points) >= 8  # 円形なので数点の多角形にはならないはず


def test_auto_trace_outline_preserves_concave_notch():
    # 下端中央に凹みのある五角形。単純な外接矩形近似では表現できない
    # 凹みが、単純化後も点として残っていることを確認する。
    image = Image.new("RGB", (400, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(100, 50), (300, 50), (300, 550), (200, 450), (100, 550)], fill="black")
    points = _segmenter().auto_trace_outline(image)
    assert points is not None
    ys_near_notch = [p[1] for p in points if 100 < p[0] < 300 and p[1] < 550]
    # 凹み頂点(200, 450)付近の点が輪郭に含まれているはず。
    assert any(400 < y < 470 for y in ys_near_notch)


def test_auto_trace_outline_point_count_is_bounded():
    image = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([20, 20, 580, 580], fill=(0, 0, 0, 255))
    points = _segmenter().auto_trace_outline(image)
    assert points is not None
    from engine.custom_panel import MAX_CUSTOM_PANEL_POINTS
    assert len(points) <= MAX_CUSTOM_PANEL_POINTS
