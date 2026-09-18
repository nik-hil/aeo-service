"""Demo-mode end-to-end: bit-stable health and visibility rates."""

from __future__ import annotations

import asyncio
import json

from aeo_mvp.db.models import ExperimentMetric, Recommendation, Report, ScoreComponent, VisibilityObservation
from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record


def _run(session, **opts):
    job = create_job_record(
        session,
        "https://demo.example/",
        demo_mode=True,
        options={"provider": "demo", "runs_per_prompt": 3, **opts},
    )
    session.commit()
    asyncio.run(JobOrchestrator(session).run(job.id))
    session.commit()
    session.refresh(job)
    return job


def test_demo_e2e_completes_with_report(db_session):
    job = _run(db_session)
    assert job.status == "completed"
    assert job.health_formula_version == "health-v1"
    assert job.experiment_protocol_version == "vis-exp-v1"

    health = (
        db_session.query(ScoreComponent)
        .filter_by(job_id=job.id, component="health")
        .one()
    )
    assert 0 <= health.score <= 100
    assert health.provenance in ("derived_metric", "synthetic_demo")

    obs = db_session.query(VisibilityObservation).filter_by(job_id=job.id).all()
    assert len(obs) == 15
    assert all(o.provenance == "synthetic_demo" for o in obs)

    recs = db_session.query(Recommendation).filter_by(job_id=job.id).all()
    assert len(recs) >= 1
    for r in recs:
        assert json.loads(r.evidence_ids_json)

    report = db_session.query(Report).filter_by(job_id=job.id).one()
    data = json.loads(report.report_json)
    for key in (
        "job_id",
        "methodology",
        "caveats",
        "scores",
        "experiment",
        "findings",
        "recommendations",
        "pages_crawled",
        "emitted_at",
    ):
        assert key in data
    assert data["scores"]["aeo_health"]["value"] is not None
    assert data["experiment"]["ai_mention_rate"]["value"] == 0.4
    assert abs(data["experiment"]["ai_citation_rate"]["value"] - (2/15)) < 1e-9
    assert data["experiment"]["query_coverage"]["value"] == 0.6
    assert data["status"] == "completed"
    assert data["demo_mode"] is True
    assert any("synthetic demo" in c.lower() or "not from a live model" in c.lower() for c in data["caveats"])
    banned = ["ChatGPT ranking", "Perplexity SERP", "official AI share of voice"]
    blob = json.dumps(data)
    for b in banned:
        assert b not in blob


def test_demo_two_runs_identical(db_session):
    job1 = _run(db_session)
    job2 = _run(db_session)

    def snapshot(job_id):
        health = (
            db_session.query(ScoreComponent)
            .filter_by(job_id=job_id, component="health")
            .one()
            .score
        )
        comps = {
            r.component: r.score
            for r in db_session.query(ScoreComponent).filter_by(job_id=job_id).all()
            if r.component != "health"
        }
        metrics = {
            m.metric_name: (m.value, m.numerator, m.denominator)
            for m in db_session.query(ExperimentMetric).filter_by(job_id=job_id).all()
        }
        return health, comps, metrics

    h1, c1, m1 = snapshot(job1.id)
    h2, c2, m2 = snapshot(job2.id)
    assert h1 == h2
    assert c1 == c2
    assert m1 == m2
