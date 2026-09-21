"""自由形状パネルの真偽値入力を曖昧に解釈しないことを確認する。"""

import pytest

from engine.custom_panel import CustomPanelError, validate_boolean


@pytest.mark.parametrize("value, expected", [(True, True), (False, False), (None, False)])
def test_validate_boolean_accepts_json_booleans_and_an_omitted_optional_value(value, expected):
    assert validate_boolean(value, "mirror") is expected


@pytest.mark.parametrize("value", ["true", "false", 1, 0, [], {}])
def test_validate_boolean_rejects_values_that_python_would_silently_coerce(value):
    with pytest.raises(CustomPanelError, match="mirrorはtrueまたはfalse"):
        validate_boolean(value, "mirror")
