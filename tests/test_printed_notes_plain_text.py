"""Warnings that reach the paper specification must print as plain text."""

from engine.hood import hood_notes, plan_hood
from engine.layering import layering_notes, plan_layer


def test_estimated_hood_warning_has_no_literal_markdown():
    notes = hood_notes(plan_hood(42.0))
    assert any("頭囲を測っていない" in note for note in notes)
    assert all("**" not in note for note in notes)


def test_layering_fabric_warning_has_no_literal_markdown():
    notes = layering_notes(plan_layer(82.0, 90.0))
    assert any("布の厚みは見込んでいません" in note for note in notes)
    assert all("**" not in note for note in notes)
