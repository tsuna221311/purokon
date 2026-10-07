"""Sewing instructions must report the sewn pattern, not a design target."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.pipeline import _sleeve_cap_ease_for


def _parts():
    return [SimpleNamespace(part_type=kind) for kind in (
        "front_bodice_zip_panel", "front_bodice_zip_panel",
        "back_bodice", "sleeve", "sleeve",
    )]


def test_uses_actual_cap_after_drop_shoulder_adjustment():
    parts = _parts()
    armholes = {id(part): value for part, value in zip(parts[:3],
                (20.46, 20.46, 45.50))}
    caps = {id(part): 44.715 for part in parts[3:]}
    with patch("engine.pipeline.armhole_length",
               side_effect=lambda part: armholes[id(part)]), patch(
                   "engine.pipeline.sleeve_cap_length",
                   side_effect=lambda part: caps[id(part)]):
        assert _sleeve_cap_ease_for(parts) == pytest.approx(1.51, abs=0.01)


def test_does_not_print_measured_ease_without_sleeves():
    assert _sleeve_cap_ease_for(_parts()[:3]) is None


def test_does_not_print_negative_or_unmeasurable_ease():
    parts = _parts()
    with patch("engine.pipeline.armhole_length", return_value=20.0), patch(
            "engine.pipeline.sleeve_cap_length", return_value=15.0):
        assert _sleeve_cap_ease_for(parts) is None
    with patch("engine.pipeline.armhole_length", return_value=20.0), patch(
            "engine.pipeline.sleeve_cap_length", return_value=None):
        assert _sleeve_cap_ease_for(parts) is None
