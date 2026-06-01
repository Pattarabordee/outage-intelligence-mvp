from __future__ import annotations

import pytest

from apps.api.rules import evaluate_text_signal


@pytest.mark.parametrize(
    ("text", "reason_code", "eta_hours"),
    [
        ("pole down near segment A", "STRUCTURAL_DAMAGE", 7.0),
        ("conductor snapped near segment A", "BROKEN_CONDUCTOR", 7.0),
        ("tree on line near segment B", "VEGETATION_CONTACT", 6.0),
        ("breaker trip reported", "PROTECTION_OPERATION", 3.5),
        ("patrol underway", "PATROL_UNDERWAY", 3.0),
        ("power restored and load normalized", "RESTORED", 0.0),
        ("crew is checking the area", "UNCLASSIFIED_FIELD_SIGNAL", 4.0),
    ],
)
def test_rule_keyword_mapping(text, reason_code, eta_hours):
    result = evaluate_text_signal(text)

    assert result.reason_code == reason_code
    assert result.predicted_eta_hours == eta_hours


def test_rule_conflict_uses_highest_eta_signal():
    result = evaluate_text_signal("breaker trip and pole down near segment A")

    assert result.reason_code == "STRUCTURAL_DAMAGE"
    assert result.predicted_eta_hours == 7.0
