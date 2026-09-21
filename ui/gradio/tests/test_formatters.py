"""KPI formatter tests."""

from __future__ import annotations

from services import formatters as fmt


def test_format_score_object_and_empty():
    assert fmt.format_score({"value": 87.92}) == "87.9"
    assert fmt.format_score(None) == "—"
    assert fmt.format_score({"value": None}) == "—"


def test_format_pct_rate():
    assert fmt.format_pct_rate({"value": 0.4}) == "40%"
    assert fmt.format_pct_rate({"value": 40}) == "40%"


def test_health_label_bands():
    assert fmt.health_label(90) == "Strong"
    assert fmt.health_label(65) == "Moderate"
    assert fmt.health_label(45) == "Needs work"
    assert fmt.health_label(10) == "Weak"
    assert fmt.health_label(None) == "Unavailable"


def test_severity_rank_order():
    assert fmt.severity_rank("high") < fmt.severity_rank("medium")
    assert fmt.severity_rank("unknown") == 99
