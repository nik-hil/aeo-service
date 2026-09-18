"""Assemble Report DTO from persisted job data."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from aeo_mvp.config import USER_AGENT
from aeo_mvp.db.models import (
    ExperimentConfig,
    ExperimentMetric,
    Finding,
    Job,
    Page,
    Recommendation,
    Report,
    ScoreComponent,
    new_id,
    utc_now_iso,
)

CAVEATS = [
    "AI visibility metrics are sample estimates from controlled experiments (protocol vis-exp-v1), not engine rankings.",
    "API-based observations are not equivalent to consumer ChatGPT, Gemini, or Perplexity UI results.",
    "This product does not reproduce proprietary answer-engine ranking or retrieval.",
    "Model or provider updates can change results; compare only runs that share protocol_version, prompt_set_id, provider, and model_id.",
]


def build_report(session: Session, job: Job) -> dict[str, Any]:
    scores_rows = (
        session.query(ScoreComponent).filter(ScoreComponent.job_id == job.id).all()
    )
    by_comp = {r.component: r for r in scores_rows}
    pages_count = session.query(Page).filter(Page.job_id == job.id).count()
    findings = session.query(Finding).filter(Finding.job_id == job.id).all()
    recs = (
        session.query(Recommendation)
        .filter(Recommendation.job_id == job.id)
        .order_by(Recommendation.rank)
        .all()
    )
    metrics = (
        session.query(ExperimentMetric).filter(ExperimentMetric.job_id == job.id).all()
    )
    metrics_by = {m.metric_name: m for m in metrics}
    exp_cfg = (
        session.query(ExperimentConfig)
        .filter(ExperimentConfig.job_id == job.id)
        .order_by(ExperimentConfig.created_at.desc())
        .first()
    )
    options = json.loads(job.options_json or "{}")

    def score_obj(name: str, display: str | None = None) -> dict[str, Any]:
        key = name
        row = by_comp.get(key)
        if not row:
            return {"value": None, "provenance": "derived_metric"}
        out: dict[str, Any] = {
            "value": round(row.score, 1),
            "provenance": row.provenance,
        }
        if key == "health":
            out["formula_version"] = row.formula_version
        return out

    caveats = list(CAVEATS)
    if job.demo_mode:
        caveats.append(
            "This job used synthetic demo fixtures; visibility data is not from a live model."
        )

    def metric_obj(name: str) -> dict[str, Any]:
        m = metrics_by.get(name)
        if not m:
            return {"value": None, "numerator": 0, "denominator": 0, "provenance": "estimate"}
        return {
            "value": m.value,
            "numerator": m.numerator,
            "denominator": m.denominator,
            "provenance": m.provenance,
        }

    obs_count = 0
    if exp_cfg:
        prompts = json.loads(exp_cfg.prompts_json)
        obs_count = len(prompts) * exp_cfg.runs_per_prompt

    report: dict[str, Any] = {
        "job_id": job.id,
        "base_url": job.base_url,
        "demo_mode": bool(job.demo_mode),
        "status": job.status,
        "methodology": {
            "health_formula_version": job.health_formula_version or "health-v1",
            "experiment_protocol_version": job.experiment_protocol_version or "vis-exp-v1",
            "prompt_set_id": exp_cfg.prompt_set_id if exp_cfg else "prompt-set-v1",
            "crawl": {
                "max_pages": options.get("max_pages", 25),
                "max_depth": options.get("max_depth", 2),
                "user_agent": USER_AGENT,
            },
        },
        "caveats": caveats,
        "scores": {
            "aeo_health": score_obj("health"),
            "technical": score_obj("technical"),
            "content": score_obj("content"),
            "entity": score_obj("entity"),
            "structured_data": score_obj("structured_data"),
            "answerability": score_obj("answerability"),
        },
        "experiment": {
            "provider_name": exp_cfg.provider_name if exp_cfg else None,
            "model_id": exp_cfg.model_id if exp_cfg else None,
            "observations_count": obs_count,
            "ai_mention_rate": metric_obj("ai_mention_rate"),
            "ai_citation_rate": metric_obj("ai_citation_rate"),
            "query_coverage": metric_obj("query_coverage"),
        },
        "findings": [
            {
                "id": f.id,
                "category": f.category,
                "title": f.title,
                "summary": f.summary,
                "severity": f.severity,
                "evidence_ids": json.loads(f.evidence_ids_json or "[]"),
            }
            for f in findings
        ],
        "recommendations": [
            {
                "id": r.id,
                "code": r.code,
                "title": r.title,
                "rationale": r.rationale,
                "effort": r.effort,
                "impact": r.impact,
                "priority_score": r.priority_score,
                "rank": r.rank,
                "evidence_ids": json.loads(r.evidence_ids_json or "[]"),
                "finding_ids": json.loads(r.finding_ids_json or "[]"),
            }
            for r in recs
        ],
        "pages_crawled": pages_count,
        "emitted_at": utc_now_iso(),
    }

    # Ensure formula_version on aeo_health
    if report["scores"]["aeo_health"].get("value") is not None:
        report["scores"]["aeo_health"]["formula_version"] = (
            job.health_formula_version or "health-v1"
        )

    emitted = report["emitted_at"]
    existing = session.query(Report).filter(Report.job_id == job.id).one_or_none()
    payload = json.dumps(report, sort_keys=True)
    if existing:
        existing.report_json = payload
        existing.emitted_at = emitted
    else:
        session.add(
            Report(id=new_id(), job_id=job.id, report_json=payload, emitted_at=emitted)
        )
    session.flush()
    return report
