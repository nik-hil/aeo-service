"""Analyzer tests on demo fixture HTML."""

from aeo_mvp.analyzers.content import analyze_content
from aeo_mvp.analyzers.entities import analyze_entities
from aeo_mvp.analyzers.structured_data import analyze_structured_data
from aeo_mvp.analyzers.technical import analyze_technical
from aeo_mvp.crawler.discover import crawl_demo
from aeo_mvp.db.models import Job, new_id, utc_now_iso


def _demo_job(session):
    job = Job(
        id=new_id(),
        base_url="https://demo.example/",
        demo_mode=1,
        status="crawling",
        options_json="{}",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    session.add(job)
    session.flush()
    outcome = crawl_demo(session, job.id)
    session.commit()
    return job, outcome


def test_technical_on_demo(db_session):
    job, outcome = _demo_job(db_session)
    result = analyze_technical(
        db_session, job.id, outcome.pages, robots_allowed_root=outcome.robots_allowed_root
    )
    assert result.score >= 80
    assert result.checks["T1"] == 1.0
    assert result.checks["T2"] == 1.0


def test_content_and_answerability_on_demo(db_session):
    job, outcome = _demo_job(db_session)
    result = analyze_content(db_session, job.id, outcome.pages)
    assert result.content_score > 50
    assert result.answerability_score > 50
    assert result.checks_a["A2"] == 1.0  # HowTo / steps on site
    assert result.checks_a["A4"] == 1.0  # FAQ density


def test_entities_on_demo(db_session):
    job, outcome = _demo_job(db_session)
    result = analyze_entities(db_session, job.id, outcome.pages, job.base_url)
    assert "AcmeFlow" in result.brand_tokens or any(
        "acme" in t.lower() for t in result.brand_tokens
    )
    assert result.checks["E2"] == 1.0
    assert result.score >= 70


def test_structured_data_on_demo(db_session):
    job, outcome = _demo_job(db_session)
    result = analyze_structured_data(db_session, job.id, outcome.pages)
    assert result.checks["S1"] == 1.0
    assert result.has_organization is True
    assert result.score >= 70
