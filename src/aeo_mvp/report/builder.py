"""Assemble Report DTO from persisted job data."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from aeo_mvp.config import USER_AGENT
from aeo_mvp.db.models import (
    AnalysisEvidence,
    ExperimentConfig,
    ExperimentMetric,
    Finding,
    Job,
    Page,
    Recommendation,
    Report,
    ScoreComponent,
    SiteProfile,
    new_id,
    utc_now_iso,
)

CAVEATS = [
    "LLM mention metrics are sample estimates from controlled llm-mention-v1 experiments, not AI search visibility or engine rankings.",
    "Chat-completions / LLM mention probes (retrieval_enabled=false) are NOT equivalent to AI search visibility.",
    "AI search visibility metrics (ai-search-vis-v1) are API observations from retrieval-enabled providers (e.g. DigitalOcean Inference web_search), not consumer ChatGPT/Gemini/Perplexity UI rankings.",
    "API-based observations are not equivalent to consumer ChatGPT, Gemini, or Perplexity UI results.",
    "This product does not reproduce proprietary answer-engine ranking or retrieval.",
    "Model or provider updates can change results; compare only runs that share protocol_version, prompt_set_id, provider, model_id, and experiment_kind.",
    "robots.txt allow for an AI crawler does NOT imply AI visibility, citation, or consumer-UI ranking.",
]


def _health_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 85:
        return "strong"
    if score >= 70:
        return "good"
    if score >= 50:
        return "fair"
    return "weak"


def _build_executive_summary(
    scores: dict[str, Any],
    recommendations: list[dict[str, Any]],
    caveats: list[str],
    *,
    demo_mode: bool,
    experiment_kind: str,
    retrieval_enabled: bool,
) -> dict[str, Any]:
    named = {
        "technical": scores.get("technical", {}).get("value"),
        "content": scores.get("content", {}).get("value"),
        "entity": scores.get("entity", {}).get("value"),
        "structured_data": scores.get("structured_data", {}).get("value"),
        "answerability": scores.get("answerability", {}).get("value"),
    }
    present = {k: v for k, v in named.items() if v is not None}
    strongest = sorted(present.items(), key=lambda kv: kv[1], reverse=True)[:3]
    weakest = sorted(present.items(), key=lambda kv: kv[1])[:3]
    health_val = scores.get("aeo_health", {}).get("value")
    top_actions = [
        {
            "rank": r.get("rank"),
            "code": r.get("code"),
            "title": r.get("title"),
            "recommended_action": r.get("recommended_action"),
        }
        for r in recommendations[:3]
    ]
    provenance = {
        "health": scores.get("aeo_health", {}).get("provenance"),
        "experiment_kind": experiment_kind,
        "retrieval_enabled": retrieval_enabled,
        "demo_mode": demo_mode,
    }
    major_caveats = list(caveats[:4])
    if demo_mode:
        major_caveats.insert(
            0,
            "Demo/synthetic data used for crawl and/or visibility — not live AI search measurement.",
        )
    return {
        "overall_health": {
            "score": health_val,
            "label": _health_label(health_val),
            "formula_version": scores.get("aeo_health", {}).get("formula_version", "health-v1"),
        },
        "strongest_areas": [{"component": k, "score": v} for k, v in strongest],
        "weakest_areas": [{"component": k, "score": v} for k, v in weakest],
        "top_3_actions": top_actions,
        "data_provenance": provenance,
        "major_caveats": major_caveats,
    }


def _page_findings(
    session: Session,
    job_id: str,
    evidence: list[AnalysisEvidence],
) -> list[dict[str, Any]]:
    pages = {p.id: p for p in session.query(Page).filter(Page.job_id == job_id).all()}
    by_page: dict[str, list[AnalysisEvidence]] = {}
    for ev in evidence:
        if ev.severity not in ("low", "medium", "high"):
            continue
        if not ev.page_id or ev.page_id not in pages:
            continue
        by_page.setdefault(ev.page_id, []).append(ev)
    out: list[dict[str, Any]] = []
    for pid, evs in by_page.items():
        page = pages[pid]
        out.append(
            {
                "url": page.url,
                "title": page.title,
                "issue_count": len(evs),
                "issues": [
                    {
                        "code": e.code,
                        "severity": e.severity,
                        "message": e.message,
                        "analyzer": e.analyzer,
                    }
                    for e in sorted(
                        evs,
                        key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.severity, 9),
                    )[:8]
                ],
            }
        )
    out.sort(key=lambda x: (-x["issue_count"], x["url"]))
    return out


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
    evidence = (
        session.query(AnalysisEvidence).filter(AnalysisEvidence.job_id == job.id).all()
    )
    site_profile_row = (
        session.query(SiteProfile).filter(SiteProfile.job_id == job.id).one_or_none()
    )

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

    retrieval_enabled = bool(exp_cfg.retrieval_enabled) if exp_cfg else False
    experiment_kind = (
        (exp_cfg.experiment_kind if exp_cfg and exp_cfg.experiment_kind else "llm_mention")
    )

    # AI crawler access section from evidence
    ai_crawler_access: dict[str, Any] | None = None
    for ev in evidence:
        if ev.code == "AI_CRAWLER_CAVEAT" or ev.analyzer == "ai_crawlers":
            # Prefer SITE-level aggregate stored during orchestrator in options/report stash
            break
    # Prefer structured blob from job options pipeline stash if present
    pipeline_extras = options.get("_p1_sections") or {}
    ai_crawler_access = pipeline_extras.get("ai_crawler_access")
    site_understanding = pipeline_extras.get("site_understanding")
    discovered_queries = pipeline_extras.get("discovered_queries")
    competitors = pipeline_extras.get("competitors")
    target_site = pipeline_extras.get("target_site")
    content_optimization = pipeline_extras.get("content_optimization")

    if site_understanding is None and site_profile_row:
        try:
            site_understanding = json.loads(site_profile_row.profile_json)
        except json.JSONDecodeError:
            site_understanding = None

    if discovered_queries is None and exp_cfg and exp_cfg.discovered_queries_json:
        try:
            discovered_queries = json.loads(exp_cfg.discovered_queries_json)
        except json.JSONDecodeError:
            discovered_queries = None

    scores_block = {
        "aeo_health": score_obj("health"),
        "technical": score_obj("technical"),
        "content": score_obj("content"),
        "entity": score_obj("entity"),
        "structured_data": score_obj("structured_data"),
        "answerability": score_obj("answerability"),
    }
    if scores_block["aeo_health"].get("value") is not None:
        scores_block["aeo_health"]["formula_version"] = (
            job.health_formula_version or "health-v1"
        )

    rec_payloads: list[dict[str, Any]] = []
    for r in recs:
        details: dict[str, Any] = {}
        if r.details_json:
            try:
                details = json.loads(r.details_json)
            except json.JSONDecodeError:
                details = {}
        rec_payloads.append(
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
                "affected_urls": details.get("affected_urls", []),
                "evidence_snippets": details.get("evidence_snippets", []),
                "problem": details.get("problem", ""),
                "why_it_matters": details.get("why_it_matters", ""),
                "recommended_action": details.get("recommended_action", ""),
                "implementation_pattern": details.get("implementation_pattern", ""),
                "validation_method": details.get("validation_method", ""),
            }
        )

    page_findings = _page_findings(session, job.id, evidence)
    executive_summary = _build_executive_summary(
        scores_block,
        rec_payloads,
        caveats,
        demo_mode=bool(job.demo_mode),
        experiment_kind=experiment_kind,
        retrieval_enabled=retrieval_enabled,
    )

    caps_notes = (
        "Non-retrieval LLM mention provider; not AI search visibility."
        if not retrieval_enabled
        else (
            "Retrieval-enabled AI search visibility provider "
            "(measures_consumer_ui=false; API observation only)."
        )
    )

    experiment_block: dict[str, Any] = {
        "provider_name": exp_cfg.provider_name if exp_cfg else None,
        "model_id": exp_cfg.model_id if exp_cfg else None,
        "experiment_kind": experiment_kind,
        "retrieval_enabled": retrieval_enabled,
        "protocol_version": (
            exp_cfg.protocol_version
            if exp_cfg
            else (job.experiment_protocol_version or "llm-mention-v1")
        ),
        "provider_capabilities_notes": caps_notes,
        "observations_count": obs_count,
        "measures_consumer_ui": False,
    }

    if retrieval_enabled:
        experiment_block["ai_search_visibility"] = {
            "ai_search_mention_rate": metric_obj("ai_search_mention_rate"),
            "ai_search_citation_rate": metric_obj("ai_search_citation_rate"),
            "target_domain_appearance_rate": metric_obj(
                "target_domain_appearance_rate"
            ),
            "query_coverage": metric_obj("query_coverage"),
            "note": (
                "AI-search metrics only. llm_mention_rate / llm_url_mention_rate "
                "are not emitted for retrieval-enabled runs."
            ),
        }
        # Flat aliases for consumers that expect top-level keys under experiment
        experiment_block["ai_search_mention_rate"] = metric_obj(
            "ai_search_mention_rate"
        )
        experiment_block["ai_search_citation_rate"] = metric_obj(
            "ai_search_citation_rate"
        )
        experiment_block["target_domain_appearance_rate"] = metric_obj(
            "target_domain_appearance_rate"
        )
        experiment_block["query_coverage"] = metric_obj("query_coverage")
    else:
        experiment_block["llm_mention_rate"] = metric_obj("llm_mention_rate")
        experiment_block["llm_url_mention_rate"] = metric_obj("llm_url_mention_rate")
        experiment_block["query_coverage"] = metric_obj("query_coverage")

    methodology_block: dict[str, Any] = {
        "health_formula_version": job.health_formula_version or "health-v1",
        "experiment_protocol_version": job.experiment_protocol_version or "llm-mention-v1",
        "prompt_set_id": exp_cfg.prompt_set_id if exp_cfg else "prompt-set-v1",
        "crawl": {
            "max_pages": options.get("max_pages", 25),
            "max_depth": options.get("max_depth", 2),
            "user_agent": USER_AGENT,
        },
    }
    if content_optimization and content_optimization.get("methodology"):
        methodology_block["content_optimization_methodology"] = content_optimization[
            "methodology"
        ]

    report: dict[str, Any] = {
        "job_id": job.id,
        "base_url": job.base_url,
        "demo_mode": bool(job.demo_mode),
        "status": job.status,
        "methodology": methodology_block,
        "caveats": caveats,
        "executive_summary": executive_summary,
        "scores": scores_block,
        "experiment": experiment_block,
        "ai_crawler_access": ai_crawler_access
        or {
            "caveat": CAVEATS[-1],
            "agents": [],
            "note": "AI crawler analysis not available for this job.",
        },
        "site_understanding": site_understanding
        or {
            "organization_brand": None,
            "provenance": "derived_metric",
            "note": "Site understanding not available.",
        },
        "discovered_queries": discovered_queries
        or {
            "queries": [],
            "fallback_used": True,
            "note": "No discovered queries persisted.",
        },
        "page_findings": page_findings,
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
        "recommendations": rec_payloads,
        "pages_crawled": pages_count,
        "emitted_at": utc_now_iso(),
    }

    if retrieval_enabled and competitors and competitors.get("applicable"):
        report["competitors"] = competitors

    if target_site:
        report["target_site"] = target_site
    elif retrieval_enabled:
        # Derive from base_url when stash missing (older jobs / partial runs).
        from aeo_mvp.target_site import resolve_target_site_identity

        report["target_site"] = resolve_target_site_identity(job.base_url).to_audit_dict()

    # Phase 5 — additive/versioned; same keys as standalone when optimization ran.
    if content_optimization is not None:
        report["content_optimization"] = {
            "enabled": bool(content_optimization.get("enabled")),
            "status": content_optimization.get("status"),
            "methodology": content_optimization.get("methodology"),
            "pages_considered": content_optimization.get("pages_considered", 0),
            "pages_optimized": content_optimization.get("pages_optimized", 0),
            "page_ids": list(content_optimization.get("page_ids") or []),
            "skipped_page_ids": list(
                content_optimization.get("skipped_page_ids") or []
            ),
            "page_selection": content_optimization.get("page_selection"),
            "paid_retrieval": bool(content_optimization.get("paid_retrieval", False)),
            "paid_llm": bool(content_optimization.get("paid_llm", False)),
            "warnings": list(content_optimization.get("warnings") or []),
        }
        # Authoritative ContentOptimizationResult.to_dict keys when Phase 5 completed.
        if content_optimization.get("status") == "completed":
            if content_optimization.get("page_intelligence") is not None:
                report["page_intelligence"] = content_optimization["page_intelligence"]
            report["content_gaps"] = list(
                content_optimization.get("content_gaps") or []
            )
            report["optimization_briefs"] = list(
                content_optimization.get("optimization_briefs") or []
            )
            report["content_drafts"] = list(
                content_optimization.get("content_drafts") or []
            )
            if content_optimization.get("gap_report") is not None:
                report["gap_report"] = content_optimization["gap_report"]
            if content_optimization.get("brief") is not None:
                report["brief"] = content_optimization["brief"]
            if content_optimization.get("draft") is not None:
                report["draft"] = content_optimization["draft"]
            report["paid_retrieval"] = bool(
                content_optimization.get("paid_retrieval", False)
            )
            report["paid_llm"] = bool(content_optimization.get("paid_llm", False))

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
