"""Actionable recommendation enrichment helpers (P1-E)."""

from __future__ import annotations

import json
from typing import Any

from aeo_mvp.db.models import AnalysisEvidence, Page
from aeo_mvp.recommendations.catalog import REC_CATALOG, RecDef

# Honest framing — never promise ranking lifts.
NO_RANKING_CLAIMS = (
    "will increase ChatGPT ranking",
    "will increase Perplexity ranking",
    "guaranteed citation",
    "official AI share of voice",
)


def enrichment_from_catalog(rec_def: RecDef) -> dict[str, Any]:
    return {
        "problem": rec_def.problem,
        "why_it_matters": rec_def.why_it_matters,
        "recommended_action": rec_def.recommended_action,
        "implementation_pattern": rec_def.implementation_pattern,
        "validation_method": rec_def.validation_method,
    }


def build_recommendation_details(
    code: str,
    evidence_rows: list[AnalysisEvidence],
    pages_by_id: dict[str, Page],
) -> dict[str, Any]:
    rec_def = REC_CATALOG.get(code)
    base = enrichment_from_catalog(rec_def) if rec_def else {
        "problem": "Issue detected from analysis evidence.",
        "why_it_matters": "Addressing on-site readiness issues improves extractability for humans and retrieval systems.",
        "recommended_action": "Review linked evidence and apply the smallest durable fix on owned pages.",
        "implementation_pattern": "Edit HTML/CMS content; redeploy; re-crawl.",
        "validation_method": "Re-run AEO analysis and confirm the related check pass values improve.",
    }
    affected_urls: list[str] = []
    snippets: list[dict[str, Any]] = []
    for ev in evidence_rows:
        if ev.page_id and ev.page_id in pages_by_id:
            url = pages_by_id[ev.page_id].url
            if url and url not in affected_urls:
                affected_urls.append(url)
        data = {}
        try:
            data = json.loads(ev.data_json or "{}")
        except json.JSONDecodeError:
            data = {}
        snippets.append(
            {
                "evidence_id": ev.id,
                "code": ev.code,
                "message": ev.message,
                "severity": ev.severity,
                "data_preview": {k: data[k] for k in list(data)[:6]} if isinstance(data, dict) else {},
            }
        )
    out = {
        **base,
        "affected_urls": affected_urls,
        "evidence_snippets": snippets[:8],
    }
    # Safety: strip forbidden marketing claims if somehow present
    blob = json.dumps(out).lower()
    for banned in NO_RANKING_CLAIMS:
        if banned in blob:
            out["why_it_matters"] = (
                "Improves on-site readiness and extractability; "
                "does not guarantee consumer AI ranking changes."
            )
            break
    return out
