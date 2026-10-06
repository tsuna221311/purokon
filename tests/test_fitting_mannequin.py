import pytest

from engine.fitting_mannequin import axes_for_circumference, ellipse_circumference


def test_sized_ellipse_matches_requested_hip_circumference():
    x_radius, y_radius = axes_for_circumference(91)
    assert x_radius > y_radius
    assert ellipse_circumference(x_radius, y_radius) / .02 == pytest.approx(91)


def test_invalid_body_dimensions_are_rejected():
    with pytest.raises(ValueError):
        axes_for_circumference(0)
