from engine.classification_evidence import resolve_classification_evidence
from engine.part_classifier import ClassificationResult


def _r(part, variation, confidence):
    return ClassificationResult(part, variation, confidence)


def test_resolution_is_independent_of_input_order():
    values = [
        _r("sleeve", "bell", 0.7),
        _r("sleeve", "straight", 0.9),
        _r("sleeve", "bell", 0.8),
    ]
    forward = resolve_classification_evidence(values)[0]
    reverse = resolve_classification_evidence(list(reversed(values)))[0]
    assert forward == reverse
    assert forward.variation == "bell"
    assert forward.votes == 2


def test_close_runner_up_is_kept_as_a_conflict():
    decision = resolve_classification_evidence([
        _r("skirt", "flare", 0.9),
        _r("skirt", "tight", 0.7),
    ])[0]
    assert decision.variation == "flare"
    assert decision.conflicted is True
    assert decision.alternatives[0].variation == "tight"


def test_weak_runner_up_does_not_create_false_conflict():
    decision = resolve_classification_evidence([
        _r("collar", "shirt_collar", 0.95),
        _r("collar", "ruffle_collar", 0.2),
    ])[0]
    assert decision.conflicted is False


def test_different_parts_are_resolved_separately():
    decisions = resolve_classification_evidence([
        _r("sleeve", "straight", 0.8),
        _r("skirt", "flare", 0.9),
    ])
    assert [(item.part_type, item.variation) for item in decisions] == [
        ("sleeve", "straight"), ("skirt", "flare")]


def test_equal_evidence_uses_a_deterministic_name_tie_break():
    a = resolve_classification_evidence([
        _r("sleeve", "straight", 0.8), _r("sleeve", "bell", 0.8)])[0]
    b = resolve_classification_evidence([
        _r("sleeve", "bell", 0.8), _r("sleeve", "straight", 0.8)])[0]
    assert a == b
    assert a.variation == "bell"
