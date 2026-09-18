"""Tests for enriched recommendation payloads."""

from __future__ import annotations

from aeo_mvp.db.models import AnalysisEvidence, Page, new_id, utc_now_iso
from aeo_mvp.recommendations.catalog import REC_CATALOG
from aeo_mvp.recommendations.enrichment import build_recommendation_details


def test_catalog_has_enrichment_fields():
    for code, rec in REC_CATALOG.items():
        assert rec.problem, code
        assert rec.why_it_matters, code
        assert rec.recommended_action, code
        assert rec.implementation_pattern, code
        assert rec.validation_method, code
        blob = " ".join(
            [
                rec.problem,
                rec.why_it_matters,
                rec.recommended_action,
                rec.rationale_template,
            ]
        ).lower()
        assert "will increase chatgpt ranking" not in blob


def test_build_recommendation_details_includes_urls_and_snippets():
    page = Page(
        id=new_id(),
        job_id="job",
        url="https://demo.example/pricing",
        depth=1,
        status_code=200,
        html="<p>thin</p>",
        title="Pricing",
    )
    ev = AnalysisEvidence(
        id=new_id(),
        job_id="job",
        page_id=page.id,
        analyzer="content",
        code="CONTENT_WORDCOUNT",
        severity="medium",
        message="Thin page",
        data_json='{"words": 12}',
        provenance="derived_metric",
        created_at=utc_now_iso(),
    )
    details = build_recommendation_details(
        "REC_EXPAND_THIN_CONTENT", [ev], {page.id: page}
    )
    assert "https://demo.example/pricing" in details["affected_urls"]
    assert details["evidence_snippets"]
    assert details["problem"]
    assert details["validation_method"]
