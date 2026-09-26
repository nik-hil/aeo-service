"""SUMMARY.md grounded in same-run artifacts (no network)."""

from __future__ import annotations

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.evaluation import QualityEvaluation
from aeo_mvp.pipeline import AEOReport, run_pipeline
from aeo_mvp.queries import Query, QuerySet
from aeo_mvp.recommendations import Opportunity, RecommendationBundle, SectionEdit
from aeo_mvp.summary import build_summary_markdown, publish_verdict
from aeo_mvp.visibility import VisibilityObservation, VisibilityReport

from test_pipeline_e2e import E2EMock, FIXTURE


def _base_report(**overrides) -> AEOReport:
    article = load_hashnode_markdown(FIXTURE)
    current = article.markdown
    recommended = current + "\n\nExtra clarifying sentence.\n"
    diff = "".join(
        [
            "--- CURRENT.md\n",
            "+++ RECOMMENDED.md\n",
            "@@ -1,0 +1,1 @@\n",
            "+Extra clarifying sentence.\n",
        ]
    )
    report = AEOReport(
        article=article,
        queries=QuerySet(
            candidates=[],
            selected=[
                Query(
                    text="What is an agent loop for tool calling?",
                    importance="high",
                    reason="core",
                    article_topics_or_evidence="The agent loop",
                )
            ],
            quality_notes="ok",
        ),
        visibility=VisibilityReport(
            observations=[],
            mention_rate=0.0,
            citation_rate=0.0,
        ),
        recommendations=RecommendationBundle(
            opportunities=[
                Opportunity(
                    question="What is an agent loop for tool calling?",
                    gap="Could state the loop more directly for extractability.",
                    evidence_quote="The agent loop is the control flow",
                    target_heading="What is an agent loop?",
                    recommended_change="Clarify the lead definition.",
                    answerability="weak",
                )
            ],
            recommended_markdown=recommended,
            change_explanations=["Clarified agent loop wording."],
            section_edits=[
                SectionEdit(
                    target_heading="What is an agent loop?",
                    replacement_body="body",
                )
            ],
        ),
        quality_eval=QualityEvaluation(
            passed=True,
            summary="Questions are realistic; edit is small.",
        ),
        current_markdown=current,
        recommended_markdown=recommended,
        diff=diff,
        llm_used=True,
        retrieval_used=False,
        model="mock-summary",
        auto_publish=False,
    )
    for key, value in overrides.items():
        setattr(report, key, value)
    return report


def test_summary_sections_and_grounding():
    report = _base_report()
    text = build_summary_markdown(report)
    assert "# Publish pack SUMMARY" in text
    assert "## What was weak for AI visibility" in text
    assert "## What RECOMMENDED fixes" in text
    assert "## Patch at a glance" in text
    assert "## Ready to publish vs review first" in text
    assert "Could state the loop more directly" in text
    assert "Clarified agent loop wording." in text
    assert "What is an agent loop?" in text
    assert "ready_to_publish" in text
    assert "auto_publish" in text.lower()
    assert "SUMMARY.md" in text
    # No invented live visibility claims when retrieval was off
    assert "No OBSERVED visibility rows" in text
    assert "mention_rate: 100%" not in text


def test_summary_includes_observed_visibility_when_present():
    obs = VisibilityObservation(
        query="What is an agent loop for tool calling?",
        answer="…",
        mentioned=False,
        cited=False,
        target_domain_in_sources=False,
    )
    report = _base_report(
        retrieval_used=True,
        visibility=VisibilityReport(
            observations=[obs],
            mention_rate=0.0,
            citation_rate=0.0,
            target_in_sources_rate=0.0,
            query_coverage=1.0,
        ),
    )
    text = build_summary_markdown(report)
    assert "OBSERVED" in text
    assert "mention_rate: 0%" in text
    assert "mentioned=False, cited=False" in text
    assert obs.query in text


def test_publish_verdict_review_first_on_failed_quality():
    report = _base_report(
        quality_eval=QualityEvaluation(
            passed=False,
            summary="Unsupported claim.",
            unsupported_claims=["invented stat"],
        )
    )
    verdict, reasons = publish_verdict(report)
    assert verdict == "review_first"
    assert any("quality_eval.passed is false" in r for r in reasons)
    text = build_summary_markdown(report)
    assert "review_first" in text
    assert "unsupported claim" in text.lower()
    # Do not echo claim bodies that could be mistaken for product wins
    assert "invented stat" not in text


def test_publish_verdict_review_first_on_empty_diff():
    report = _base_report(diff="")
    verdict, reasons = publish_verdict(report)
    assert verdict == "review_first"
    assert any("DIFF is empty" in r for r in reasons)


def test_pipeline_e2e_writes_summary_consistent_with_artifacts(tmp_path):
    report = run_pipeline(
        FIXTURE,
        dry_run=True,
        write_artifacts_dir=tmp_path,
        client=E2EMock(),  # type: ignore[arg-type]
    )
    summary_path = tmp_path / "SUMMARY.md"
    assert summary_path.is_file()
    summary = summary_path.read_text(encoding="utf-8")
    assert report.summary_markdown == summary

    assert "Clarified agent loop wording." in summary
    assert "What is an agent loop?" in summary
    assert "Could state the loop more directly" in summary

    # Claims must match written pack siblings
    current = (tmp_path / "CURRENT.md").read_text(encoding="utf-8")
    recommended = (tmp_path / "RECOMMENDED.md").read_text(encoding="utf-8")
    diff = (tmp_path / "DIFF.patch").read_text(encoding="utf-8")
    assert current == report.current_markdown
    assert recommended == report.recommended_markdown
    assert diff == report.diff
    assert "Extra clarifying" not in summary  # no invented prose
    # Diff / patch glance stays honest
    assert "Section edits applied: 1" in summary
    assert "Headings touched: What is an agent loop?" in summary
    assert diff.strip()
    assert "ready_to_publish" in summary or "review_first" in summary
