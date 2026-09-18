"""Unit tests for deterministic site understanding."""

from __future__ import annotations

from aeo_mvp.db.models import Job, Page, SiteProfile, new_id, utc_now_iso
from aeo_mvp.understanding.site import infer_site_understanding


def _job_with_pages(session):
    job = Job(
        id=new_id(),
        base_url="https://demo.example/",
        demo_mode=1,
        status="analyzing",
        options_json="{}",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    session.add(job)
    html = """
    <html><head>
      <title>AcmeFlow — Project Management Software</title>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Organization","name":"AcmeFlow","url":"https://demo.example/"}
      </script>
    </head><body>
      <h1>AcmeFlow</h1>
      <p>AcmeFlow is project management software for teams that ship with clarity.</p>
      <h2>Pricing</h2>
      <p>Plans for startups and enterprises.</p>
    </body></html>
    """
    pages = [
        Page(
            id=new_id(),
            job_id=job.id,
            url="https://demo.example/",
            depth=0,
            status_code=200,
            html=html,
            title="AcmeFlow — Project Management Software",
        ),
        Page(
            id=new_id(),
            job_id=job.id,
            url="https://demo.example/pricing",
            depth=1,
            status_code=200,
            html="<html><head><title>AcmeFlow Pricing</title></head><body><h1>Pricing</h1><p>Buy a plan for teams.</p></body></html>",
            title="AcmeFlow Pricing",
        ),
    ]
    for p in pages:
        session.add(p)
    session.flush()
    return job, pages


def test_infer_site_understanding_deterministic(db_session):
    job, pages = _job_with_pages(db_session)
    u = infer_site_understanding(
        db_session, job.id, pages, job.base_url, provenance="synthetic_demo"
    )
    assert u.organization_brand and "acme" in u.organization_brand.lower()
    assert u.llm_used is False
    assert u.method.startswith("deterministic")
    assert any("pricing" in (p.get("url") or "") for p in u.important_pages)
    assert "pricing" in u.commercial_intents or u.commercial_intents
    profile = db_session.query(SiteProfile).filter_by(job_id=job.id).one()
    assert profile.profile_json
    assert u.evidence_refs
