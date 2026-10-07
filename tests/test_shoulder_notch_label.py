"""The special sleeve shoulder mark must be distinguishable on paper."""

from types import SimpleNamespace

import pytest

from engine.pdf_export import _shoulder_notch_label_point


def _placed(kind="sleeve", notch_count=4):
    return SimpleNamespace(part=SimpleNamespace(
        part_type=kind, notches=[None] * notch_count))


def test_only_fourth_sleeve_notch_receives_shoulder_label():
    notch = ((2.0, 4.0), (2.0, 3.0))
    assert _shoulder_notch_label_point(_placed(), 3, notch) == pytest.approx(
        (2.0, 4.45))
    assert _shoulder_notch_label_point(_placed(), 0, notch) is None
    assert _shoulder_notch_label_point(_placed(notch_count=3), 3, notch) is None
    assert _shoulder_notch_label_point(_placed(kind="back_bodice"), 3, notch) is None


def test_label_stays_inside_when_placed_part_is_rotated():
    assert _shoulder_notch_label_point(
        _placed(), 3, ((4.0, 2.0), (5.0, 2.0))) == pytest.approx((3.55, 2.0))
    assert _shoulder_notch_label_point(
        _placed(), 3, ((4.0, 2.0), (4.0, 2.0))) is None
