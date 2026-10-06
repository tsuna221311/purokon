import pytest

from engine.pattern_width_audit import horizontal_material_width_cm


def test_horizontal_material_width_uses_stitch_polygon_not_bounding_box():
    taper = [(0, 0), (20, 0), (10, 10), (0, 10)]
    assert horizontal_material_width_cm(taper, 5) == pytest.approx(15)


def test_horizontal_material_width_rejects_empty_or_boundary_sections():
    rectangle = [(0, 0), (20, 0), (20, 10), (0, 10)]
    with pytest.raises(ValueError, match="strictly inside"):
        horizontal_material_width_cm(rectangle, 10)
    with pytest.raises(ValueError, match="valid filled polygon"):
        horizontal_material_width_cm([(0, 0), (1, 1), (2, 2)], 1)
