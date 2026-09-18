"""Unit tests for health-v1 formulas."""

from aeo_mvp.recommendations.engine import compute_priority
from aeo_mvp.scoring.health import health_from_components
from aeo_mvp.visibility.metrics import (
    aggregate_metrics,
    detect_citation,
    detect_mention,
)
from aeo_mvp.visibility.base import VisibilityObservation
from datetime import datetime, timezone


def test_health_worked_example():
    # METRICS.md §10
    h = health_from_components(80.0, 70.0, 65.0, 55.0, 75.0)
    assert h == 70.0


def test_health_clamp():
    assert health_from_components(0, 0, 0, 0, 0) == 0.0
    assert health_from_components(100, 100, 100, 100, 100) == 100.0


def test_recommendation_priority_worked_example():
    impact, priority = compute_priority(
        0.80, "S", severity="high", component_score=40.0, mention_rate=0.5, visibility_relevant=False
    )
    assert impact == 1.0
    assert priority == 1.0

    impact2, priority2 = compute_priority(
        0.70,
        "M",
        severity="medium",
        component_score=62.0,
        mention_rate=0.1,
        visibility_relevant=True,
    )
    assert abs(impact2 - 0.88) < 0.001
    assert abs(priority2 - 0.616) < 0.001


def test_mention_and_citation_rules():
    text = "AcmeFlow is great. See https://demo.example/about for details."
    assert detect_mention(text, ["AcmeFlow", "demo"])
    cited, urls = detect_citation(text, "demo.example")
    assert cited
    assert "https://demo.example/about" in urls


def test_aggregate_rates():
    obs = []
    for i in range(15):
        obs.append(
            VisibilityObservation(
                provider_name="demo",
                engine_label="demo-engine",
                query="q",
                prompt_id=f"ps{(i // 3) + 1}",
                run_index=i % 3,
                observed_at=datetime.now(timezone.utc),
                raw_response="x",
                detected_mention=i < 6,
                detected_citation=i < 3,
                cited_urls=[],
                extraction_methodology="vis-exp-v1:mention-rule-v1+citation-rule-v1",
                provenance="synthetic_demo",
            )
        )
    rates = aggregate_metrics(obs)
    assert rates.ai_mention_rate == 0.4
    assert rates.ai_citation_rate == 0.2
    assert abs(rates.query_coverage - 1.0) < 1e-9 or rates.coverage_numerator == 2
