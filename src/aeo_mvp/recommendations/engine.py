"""Finding synthesis and recommendation prioritization."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from aeo_mvp.db.models import (
    AnalysisEvidence,
    Finding,
    Page,
    Recommendation,
    new_id,
)
from aeo_mvp.recommendations.catalog import (
    EFFORT_WEIGHT,
    REC_CATALOG,
    VISIBILITY_RELEVANT_CODES,
    RecDef,
)
from aeo_mvp.recommendations.enrichment import build_recommendation_details

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3}
SEVERITY_BOOST = {"high": 0.15, "medium": 0.08, "low": 0.03, "info": 0.0}


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_priority(
    impact_base: float,
    effort: str,
    *,
    severity: str = "info",
    component_score: float | None = None,
    mention_rate: float | None = None,
    visibility_relevant: bool = False,
) -> tuple[float, float]:
    """Return (impact, priority_score). Matches RECOMMENDATIONS.md worked examples."""
    severity_boost = SEVERITY_BOOST.get(severity, 0.0)
    score_gap_boost = 0.0
    if component_score is not None:
        if component_score < 50:
            score_gap_boost = 0.10
        elif component_score < 70:
            score_gap_boost = 0.05
    visibility_boost = 0.0
    if visibility_relevant and mention_rate is not None and mention_rate < 0.2:
        visibility_boost = 0.05
    impact = clamp01(impact_base + severity_boost + score_gap_boost + visibility_boost)
    priority = impact * EFFORT_WEIGHT[effort]
    return impact, priority


@dataclass
class TriggerContext:
    tech_checks: dict[str, float]
    content_page_checks: list[dict[str, float]]
    entity_checks: dict[str, float]
    sd_checks: dict[str, float]
    ans_checks: dict[str, float]
    has_organization: bool
    parse_error_evidence_ids: list[str]
    component_scores: dict[str, float]
    mention_rate: float | None
    citation_rate: float | None
    used_demo_fallback: bool
    evidence_by_code: dict[str, list[AnalysisEvidence]]
    home_answer_first: float | None


def synthesize_findings(
    session: Session,
    job_id: str,
    evidence: list[AnalysisEvidence],
    *,
    mention_rate: float | None = None,
    citation_rate: float | None = None,
    used_demo_fallback: bool = False,
    observation_ids: list[str] | None = None,
) -> list[Finding]:
    """Group notable evidence into findings."""
    findings: list[Finding] = []
    by_code: dict[str, list[AnalysisEvidence]] = defaultdict(list)
    for ev in evidence:
        by_code[ev.code].append(ev)

    def add_finding(
        category: str,
        title: str,
        summary: str,
        evs: list[AnalysisEvidence],
        obs: list[str] | None = None,
    ) -> Finding:
        sev = "info"
        for e in evs:
            if SEVERITY_ORDER.get(e.severity, 0) > SEVERITY_ORDER.get(sev, 0):
                sev = e.severity
        row = Finding(
            id=new_id(),
            job_id=job_id,
            category=category,
            title=title,
            summary=summary,
            evidence_ids_json=json.dumps([e.id for e in evs]),
            observation_ids_json=json.dumps(obs or []),
            severity=sev,
        )
        session.add(row)
        findings.append(row)
        return row

    # Readiness groupings for weak checks
    notable = [e for e in evidence if e.severity in ("low", "medium", "high")]
    buckets: dict[str, list[AnalysisEvidence]] = defaultdict(list)
    for e in notable:
        buckets[e.analyzer].append(e)
    for analyzer, evs in buckets.items():
        add_finding(
            "readiness",
            f"{analyzer.replace('_', ' ').title()} issues detected",
            f"{len(evs)} evidence item(s) with severity ≥ low from {analyzer} analyzer.",
            evs,
        )

    if mention_rate is not None and mention_rate < 0.2:
        add_finding(
            "visibility",
            "Low sample LLM mention rate",
            f"Estimated LLM mention rate is {mention_rate:.2f} under llm-mention-v1 (sample, not a ranking).",
            [],
            obs=observation_ids or [],
        )
    if citation_rate is not None and citation_rate < 0.15:
        add_finding(
            "visibility",
            "Low sample LLM URL-mention rate",
            f"Estimated LLM URL-mention rate is {citation_rate:.2f} under llm-mention-v1 (sample, not a ranking).",
            [],
            obs=observation_ids or [],
        )
    if used_demo_fallback:
        add_finding(
            "meta",
            "DemoProvider used (no live credentials)",
            "Visibility observations are synthetic_demo because no API key was available or demo mode was forced.",
            [],
        )

    session.flush()
    return findings


def _min_component(scores: dict[str, float], components: tuple[str, ...]) -> float | None:
    vals = [scores[c] for c in components if c in scores and c != "visibility" and c != "meta"]
    return min(vals) if vals else None


def prioritize_recommendations(
    session: Session,
    job_id: str,
    findings: list[Finding],
    ctx: TriggerContext,
) -> list[Recommendation]:
    """Map catalog triggers to ranked recommendations with evidence links."""
    finding_by_category = defaultdict(list)
    for f in findings:
        finding_by_category[f.category].append(f)

    def evidence_ids_for(*codes: str) -> list[str]:
        ids: list[str] = []
        for code in codes:
            for e in ctx.evidence_by_code.get(code, []):
                ids.append(e.id)
        return ids

    def severity_for(ids: list[str], code_hints: list[str]) -> str:
        sev = "info"
        for code in code_hints:
            for e in ctx.evidence_by_code.get(code, []):
                if SEVERITY_ORDER.get(e.severity, 0) > SEVERITY_ORDER.get(sev, 0):
                    sev = e.severity
        return sev

    def pick_finding(category: str, fallback_any: bool = True) -> Finding | None:
        if finding_by_category.get(category):
            return finding_by_category[category][0]
        if fallback_any and findings:
            return findings[0]
        return None

    candidates: list[tuple[RecDef, list[str], Finding, str]] = []

    def maybe(code: str, triggered: bool, ev_ids: list[str], category: str = "readiness") -> None:
        if not triggered:
            return
        if not ev_ids and code not in ("REC_IMPROVE_CITABLE_URLS", "REC_CLARIFY_BRAND_IN_COPY", "REC_REVIEW_DEMO_ONLY"):
            return
        rec_def = REC_CATALOG[code]
        finding = pick_finding(category if category != "visibility" else "visibility")
        if finding is None and category == "meta":
            finding = pick_finding("meta")
        if finding is None:
            # create a synthetic finding link target already exists from synthesize
            finding = pick_finding("readiness") or (findings[0] if findings else None)
        if finding is None:
            return
        # For pure visibility/meta without evidence, allow observation-backed findings
        if not ev_ids:
            # use finding's observation ids as stand-in — still need evidence_ids_json non-empty
            # Create a meta evidence? Spec says ≥1 analysis_evidence OR observation via findings.
            # We'll attach finding id and use a placeholder evidence from any related weak signal.
            pass
        sev = severity_for(ev_ids, [])
        # infer severity from linked evidence
        for eid in ev_ids:
            for lst in ctx.evidence_by_code.values():
                for e in lst:
                    if e.id == eid and SEVERITY_ORDER.get(e.severity, 0) > SEVERITY_ORDER.get(sev, 0):
                        sev = e.severity
        candidates.append((rec_def, ev_ids, finding, sev))

    t = ctx.tech_checks
    maybe("REC_FIX_HOME_HTTP", t.get("T1", 1) == 0, evidence_ids_for("TECH_HOME_STATUS"))
    maybe("REC_FIX_ROBOTS_BLOCK", t.get("T2", 1) == 0, evidence_ids_for("TECH_ROBOTS"))
    maybe("REC_REMOVE_NOINDEX", t.get("T3", 1) == 0, evidence_ids_for("TECH_NOINDEX"))
    maybe("REC_ADD_CANONICAL", t.get("T4", 1) == 0, evidence_ids_for("TECH_CANONICAL"))
    maybe("REC_IMPROVE_TITLE", t.get("T5", 1) <= 0.5, evidence_ids_for("TECH_TITLE"))
    maybe("REC_ADD_META_DESCRIPTION", t.get("T6", 1) == 0, evidence_ids_for("TECH_META_DESC"))
    maybe("REC_REDUCE_JS_DEPENDENCY", t.get("T7", 1) == 0, evidence_ids_for("TECH_JS_RISK"))

    if ctx.content_page_checks:
        weak_h = sum(1 for c in ctx.content_page_checks if c.get("C1", 1) < 1) / len(ctx.content_page_checks)
        weak_wc = sum(1 for c in ctx.content_page_checks if c.get("C5", 1) < 0.5) / len(ctx.content_page_checks)
        maybe(
            "REC_FIX_HEADING_HIERARCHY",
            weak_h >= 0.3,
            evidence_ids_for("CONTENT_HEADINGS"),
        )
        maybe(
            "REC_EXPAND_THIN_CONTENT",
            weak_wc >= 0.3,
            evidence_ids_for("CONTENT_WORDCOUNT"),
        )

    home_af = ctx.home_answer_first
    if home_af is not None:
        maybe("REC_ADD_ANSWER_FIRST", home_af == 0, evidence_ids_for("CONTENT_ANSWER_FIRST"))

    maybe(
        "REC_ADD_FAQ_SECTION",
        ctx.ans_checks.get("A4", 1) < 1 or all(
            c.get("C3", 1) == 0 for c in ctx.content_page_checks
        ) if ctx.content_page_checks else False,
        evidence_ids_for("CONTENT_FAQ_SHAPE", "ANS_FAQ_DENSITY"),
    )

    e = ctx.entity_checks
    maybe("REC_CONSOLIDATE_BRAND_NAME", e.get("E1", 1) < 1 or e.get("E4", 1) < 1, evidence_ids_for("ENTITY_BRAND_CONSISTENCY", "ENTITY_AMBIGUITY"))
    maybe("REC_ADD_ORG_SIGNAL", e.get("E2", 1) == 0, evidence_ids_for("ENTITY_ORG_SIGNAL"))
    maybe("REC_ADD_CONTACT_OR_SAMEAS", e.get("E3", 1) == 0, evidence_ids_for("ENTITY_CONTACT_SAMEAS"))

    s = ctx.sd_checks
    maybe(
        "REC_ADD_JSONLD_ORG",
        s.get("S1", 1) == 0 or not ctx.has_organization,
        evidence_ids_for("SD_HOME_JSONLD", "ENTITY_ORG_SIGNAL", "SD_ID_SAMEAS"),
    )
    maybe("REC_BROADEN_JSONLD_COVERAGE", s.get("S2", 1) <= 0.5, evidence_ids_for("SD_COVERAGE"))
    maybe("REC_ADD_TYPE_FIT_SCHEMA", s.get("S3", 1) == 0, evidence_ids_for("SD_TYPE_FIT"))
    maybe(
        "REC_FIX_JSONLD_PARSE",
        bool(ctx.parse_error_evidence_ids),
        ctx.parse_error_evidence_ids or evidence_ids_for("SD_PARSE_ERROR"),
    )

    a = ctx.ans_checks
    maybe("REC_ADD_HOWTO_OR_STEPS", a.get("A2", 1) == 0, evidence_ids_for("ANS_HOWTO"))
    maybe("REC_ADD_QUESTION_HEADINGS", a.get("A3", 1) == 0, evidence_ids_for("ANS_QUESTION_HEADINGS"))

    if ctx.citation_rate is not None and ctx.citation_rate < 0.15:
        # link to coverage evidence as site pages exist
        ev = evidence_ids_for("TECH_PAGE_SUCCESS_RATE") or evidence_ids_for("SD_COVERAGE")
        if not ev and findings:
            # attach any readiness evidence id so linking rule holds
            try:
                ev = json.loads(findings[0].evidence_ids_json) or []
            except json.JSONDecodeError:
                ev = []
        maybe("REC_IMPROVE_CITABLE_URLS", True, ev, category="visibility")

    if ctx.mention_rate is not None and ctx.mention_rate < 0.2 and (
        e.get("E1", 1) < 1 or e.get("E2", 1) < 1
    ):
        maybe(
            "REC_CLARIFY_BRAND_IN_COPY",
            True,
            evidence_ids_for("ENTITY_BRAND_CONSISTENCY", "ENTITY_ORG_SIGNAL"),
            category="visibility",
        )

    if ctx.used_demo_fallback:
        # Ensure evidence link: use any meta finding's empty evidence — create from TECH_ROBOTS info if needed
        ev = evidence_ids_for("TECH_ROBOTS") or evidence_ids_for("TECH_HOME_STATUS")
        maybe("REC_REVIEW_DEMO_ONLY", True, ev, category="meta")

    ranked_rows: list[Recommendation] = []
    scored: list[tuple[float, int, str, RecDef, list[str], Finding, float, float]] = []
    for rec_def, ev_ids, finding, sev in candidates:
        if not ev_ids:
            continue  # mandatory evidence link
        comp_score = _min_component(ctx.component_scores, rec_def.components)
        vis_rel = rec_def.code in VISIBILITY_RELEVANT_CODES or rec_def.visibility_relevant
        impact, priority = compute_priority(
            rec_def.impact_base,
            rec_def.effort,
            severity=sev,
            component_score=comp_score,
            mention_rate=ctx.mention_rate,
            visibility_relevant=vis_rel,
        )
        scored.append(
            (
                -priority,
                -SEVERITY_ORDER.get(sev, 0),
                rec_def.code,
                rec_def,
                ev_ids,
                finding,
                impact,
                priority,
            )
        )

    scored.sort()
    pages = session.query(Page).filter(Page.job_id == job_id).all()
    pages_by_id = {p.id: p for p in pages}
    for rank, item in enumerate(scored, start=1):
        _, _, _, rec_def, ev_ids, finding, impact, priority = item
        # Enrich with actionable fields + evidence snippets
        ev_rows: list[AnalysisEvidence] = []
        for code_key, lst in ctx.evidence_by_code.items():
            for e in lst:
                if e.id in ev_ids:
                    ev_rows.append(e)
        details = build_recommendation_details(rec_def.code, ev_rows, pages_by_id)

        row = Recommendation(
            id=new_id(),
            job_id=job_id,
            code=rec_def.code,
            title=rec_def.title,
            rationale=rec_def.rationale_template,
            effort=rec_def.effort,
            impact=impact,
            priority_score=priority,
            evidence_ids_json=json.dumps(ev_ids),
            finding_ids_json=json.dumps([finding.id]),
            rank=rank,
            details_json=json.dumps(details, sort_keys=True),
        )
        session.add(row)
        ranked_rows.append(row)
    session.flush()
    return ranked_rows
