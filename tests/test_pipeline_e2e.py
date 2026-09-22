"""End-to-end pipeline tests with mocks (no live network)."""

from pathlib import Path

from aeo_mvp.llm import llm_used, reset_execution_flags, retrieval_used
from aeo_mvp.pipeline import run_pipeline

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "sample_article.md"


def test_pipeline_dry_run_flow_and_artifacts(tmp_path):
    reset_execution_flags()
    report = run_pipeline(
        FIXTURE,
        dry_run=True,
        write_artifacts_dir=tmp_path,
    )
    assert report.article.title
    assert report.queries.selected
    assert report.opportunities or report.recommendations is not None
    assert report.current_markdown
    assert report.recommended_markdown
    assert report.auto_publish is False
    assert report.llm_used is False
    assert report.retrieval_used is False
    assert (tmp_path / "CURRENT.md").is_file()
    assert (tmp_path / "RECOMMENDED.md").is_file()
    assert (tmp_path / "DIFF.patch").is_file()
    # Flags match actual execution, not config.
    assert llm_used() is False
    assert retrieval_used() is False


def test_pipeline_report_dict_shape():
    report = run_pipeline(text=FIXTURE.read_text(encoding="utf-8"), dry_run=True)
    d = report.to_dict()
    assert "queries_selected" in d
    assert "visibility" in d
    assert d["auto_publish"] is False
    assert d["llm_used"] is False


def test_no_auto_publish_constant():
    report = run_pipeline(FIXTURE, dry_run=True)
    assert report.auto_publish is False
