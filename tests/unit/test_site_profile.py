"""Phase 3 site profile + Hashnode topic/entity extraction tests."""

from __future__ import annotations

from pathlib import Path

from aeo_mvp.db.models import Job, Page, SiteProfile, new_id, utc_now_iso
from aeo_mvp.understanding.builder import build_structured_profile
from aeo_mvp.understanding.profile import (
    HEURISTIC_CONFIDENCE_CAP,
    SiteProfileField,
    merge_llm_field,
)
from aeo_mvp.understanding.site import infer_site_understanding

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hashnode"
HASHNODE_BASE = "https://nik-hil.hashnode.dev/"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _hashnode_pages(job_id: str) -> list[Page]:
    specs = [
        ("agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling", "article_agent_loop.html", 0),
        ("", "homepage.html", 1),
        ("series/agent-zero-2-hero", "series.html", 1),
        ("tag/python", "tag_python.html", 1),
    ]
    pages: list[Page] = []
    for path, file, depth in specs:
        html = _load(file)
        url = HASHNODE_BASE.rstrip("/") + "/" + path if path else HASHNODE_BASE
        # title from html
        title = None
        if "<title>" in html:
            title = html.split("<title>", 1)[1].split("</title>", 1)[0]
        pages.append(
            Page(
                id=new_id(),
                job_id=job_id,
                url=url,
                depth=depth,
                status_code=200,
                html=html,
                title=title,
            )
        )
    return pages


def test_hashnode_not_project_management(db_session):
    job = Job(
        id=new_id(),
        base_url=HASHNODE_BASE,
        demo_mode=0,
        status="analyzing",
        options_json="{}",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(job)
    pages = _hashnode_pages(job.id)
    for p in pages:
        db_session.add(p)
    db_session.flush()

    u = infer_site_understanding(
        db_session, job.id, pages, job.base_url, provenance="derived_metric"
    )
    assert u.industry_category_guess != "project_management"
    assert u.site_genre == "personal_tech_blog"
    # Tags must be topics, not products
    assert not any(str(p).startswith("#") for p in u.products_services)
    assert any("agent" in t.lower() or "ai" in t.lower() or "python" in t.lower() for t in u.topics)
    structured = u.structured
    assert structured["industry_category"]["omitted"] or structured["industry_category"]["value"] != "project_management"
    # If industry asserted, must be ai_ml (genre gate), else omitted
    ind = u.industry_category_guess
    assert ind in (None, "ai_ml")


def test_hashnode_structured_profile_evidence():
    pages = _hashnode_pages("fixture-job")
    profile = build_structured_profile(pages, HASHNODE_BASE)
    assert profile.genre_value() == "personal_tech_blog"
    assert profile.assertive_industry() != "project_management"
    assert profile.primary_topics.omitted is False
    topics = profile.topic_list()
    assert any("agent" in t.lower() or "#python" in t.lower() or "python" in t.lower() for t in topics)
    # Heuristic confidence capped
    assert profile.org_name.confidence <= HEURISTIC_CONFIDENCE_CAP
    # Bare roadmap in chrome must not assert PM
    assert profile.assertive_industry() != "project_management"
    assert "project_management" not in (profile.assertive_industry() or "")


def test_unrelated_category_rejected_without_evidence():
    """project_management without compound evidence must be omitted."""
    html = """
    <html><head><title>My Travel Diary</title>
    <meta property="og:site_name" content="Travel Notes"/>
    <script type="application/ld+json">
    {"@type":"BlogPosting","headline":"Hiking in Nepal","author":{"@type":"Person","name":"Alex"}}
    </script>
    </head><body>
    <aside><h2>Command Palette</h2><p>roadmap</p></aside>
    <main><h1>Hiking in Nepal</h1><p>Mountains and trails. A kanban of packing tips.</p></main>
    </body></html>
    """
    pages = [
        Page(
            id=new_id(),
            job_id="x",
            url="https://alex.example/hiking",
            depth=0,
            status_code=200,
            html=html,
            title="My Travel Diary",
        )
    ]
    profile = build_structured_profile(pages, "https://alex.example/")
    assert profile.assertive_industry() != "project_management"
    assert profile.industry_category.omitted or profile.assertive_industry() is None


def test_acme_still_gets_pm_with_strong_evidence(db_session):
    """Legitimate PM SaaS with title evidence still classifies (regression)."""
    job = Job(
        id=new_id(),
        base_url="https://demo.example/",
        demo_mode=1,
        status="analyzing",
        options_json="{}",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(job)
    html = """
    <html><head>
      <title>AcmeFlow — Project Management Software</title>
      <meta name="description" content="AcmeFlow is project management software with task board workflows."/>
      <script type="application/ld+json">
      {"@type":"SoftwareApplication","name":"AcmeFlow","applicationCategory":"ProjectManagementApplication"}
      </script>
      <script type="application/ld+json">
      {"@type":"Organization","name":"AcmeFlow","description":"Project management for teams"}
      </script>
    </head><body>
      <h1>AcmeFlow Project Management</h1>
      <p>AcmeFlow is project management software for teams that ship with clarity. Task board included.</p>
      <h2>Pricing</h2>
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
            html="<html><head><title>Pricing</title></head><body><h1>Pricing</h1><p>Buy project management plans.</p></body></html>",
            title="Pricing",
        ),
    ]
    for p in pages:
        db_session.add(p)
    db_session.flush()
    u = infer_site_understanding(db_session, job.id, pages, job.base_url)
    assert u.industry_category_guess == "project_management"
    assert u.site_genre == "saas_product"
    assert db_session.query(SiteProfile).filter_by(job_id=job.id).one()


def test_heuristic_confidence_cap_and_llm_merge_guard():
    strong = SiteProfileField(
        value="acme",
        confidence=0.75,
        provenance="observed",
        omitted=False,
    )
    llm = SiteProfileField(
        value="other",
        confidence=0.9,
        provenance="llm_assist",
        omitted=False,
        model="gpt",
        provider="openai",
        prompt_version="v0",
    )
    kept = merge_llm_field(strong, llm, justification="prefer deterministic brand")
    assert kept.value == "acme"
    assert "llm_assist_rejected" in (kept.justification or "")

    weak = SiteProfileField.from_heuristic("x", confidence=0.9, evidence=[])
    assert weak.confidence <= HEURISTIC_CONFIDENCE_CAP


def test_insufficient_evidence_omits_industry():
    pages = [
        Page(
            id=new_id(),
            job_id="y",
            url="https://thin.example/",
            depth=0,
            status_code=200,
            html="<html><head><title>Hi</title></head><body><h1>Hi</h1></body></html>",
            title="Hi",
        )
    ]
    profile = build_structured_profile(pages, "https://thin.example/")
    assert profile.industry_category.omitted is True
    assert profile.assertive_industry() is None
