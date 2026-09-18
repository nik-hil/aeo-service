"""Query quality gate — diagnostic accept/reject (NOT website ranking).

Dimensions: relevance, specificity, answerability, entity_alignment,
evidence_support, duplication, plus WEAK_INDUSTRY_LEAK.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from aeo_mvp.queries.generate import CandidateQuery
from aeo_mvp.queries.normalize import is_near_duplicate, normalize_query_text
from aeo_mvp.understanding.site import SiteUnderstanding

DimStatus = Literal["pass", "fail", "warn"]
GateStatus = Literal["accept", "reject", "accept_with_warning"]

PM_LEAK_RE = re.compile(
    r"\bproject management\b|\btask board\b|\bbest .{0,40}\btool for teams\b",
    re.I,
)
FORBIDDEN_BLOG_RE = re.compile(
    r"how much does .+ cost\?|alternatives to .+|what products or services does .+ offer\?",
    re.I,
)


@dataclass
class DimensionResult:
    name: str
    status: DimStatus
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateDecision:
    status: GateStatus
    reasons: list[str] = field(default_factory=list)
    dimensions: list[DimensionResult] = field(default_factory=list)
    query_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "dimensions": [d.to_dict() for d in self.dimensions],
            "query_id": self.query_id,
        }


def _dim_relevance(q: CandidateQuery, u: SiteUnderstanding) -> DimensionResult:
    topics = [t.lower() for t in u.topics]
    text = q.text.lower()
    if q.topic and any(q.topic.lower()[:20] in t or t[:20] in text for t in topics):
        return DimensionResult("relevance", "pass", "topic aligns with site evidence")
    if u.organization_brand and u.organization_brand.lower() in text:
        return DimensionResult("relevance", "pass", "brand navigational relevance")
    if q.intent in ("informational", "problem_solving") and q.topic:
        return DimensionResult("relevance", "warn", "topic weakly grounded")
    return DimensionResult("relevance", "fail", "no topic/brand alignment")


def _dim_specificity(q: CandidateQuery) -> DimensionResult:
    tokens = normalize_query_text(q.text).split()
    if len(tokens) < 3:
        return DimensionResult("specificity", "fail", "too short / generic")
    if len(tokens) > 24:
        return DimensionResult("specificity", "warn", "overly long")
    vague = {"best tools", "leading options", "top software"}
    if normalize_query_text(q.text) in vague:
        return DimensionResult("specificity", "fail", "generic template")
    return DimensionResult("specificity", "pass", "adequate specificity")


def _dim_answerability(q: CandidateQuery) -> DimensionResult:
    if q.intent in ("informational", "problem_solving", "navigational"):
        return DimensionResult("answerability", "pass", "question-form intent")
    if q.intent == "commercial" and "cost" in q.text.lower():
        return DimensionResult("answerability", "warn", "pricing may be unknowable")
    return DimensionResult("answerability", "pass", "answerable intent")


def _dim_entity(q: CandidateQuery, u: SiteUnderstanding) -> DimensionResult:
    if not q.entity and not u.organization_brand:
        return DimensionResult("entity_alignment", "warn", "no entity bound")
    brand = (u.organization_brand or "").lower()
    if brand and brand in q.text.lower():
        return DimensionResult("entity_alignment", "pass", "brand present in query")
    if q.entity:
        return DimensionResult("entity_alignment", "pass", "entity field set from evidence")
    return DimensionResult("entity_alignment", "warn", "entity loosely aligned")


def _dim_evidence(q: CandidateQuery) -> DimensionResult:
    classes = {c for c in q.evidence_classes if c != "chrome"}
    if len(classes) >= 2:
        return DimensionResult("evidence_support", "pass", f"classes={sorted(classes)}")
    if len(classes) == 1:
        return DimensionResult("evidence_support", "fail", "only one evidence class")
    return DimensionResult("evidence_support", "fail", "no evidence classes")


def _dim_duplication(
    q: CandidateQuery, accepted_texts: list[str]
) -> DimensionResult:
    for prev in accepted_texts:
        if is_near_duplicate(q.text, prev):
            return DimensionResult("duplication", "fail", f"near-dup of {prev[:60]}")
    return DimensionResult("duplication", "pass", "unique vs accepted set")


def _dim_industry_leak(q: CandidateQuery, u: SiteUnderstanding) -> DimensionResult:
    """WEAK_INDUSTRY_LEAK: PM/SaaS language without assertive industry evidence."""
    text = q.text
    genre = u.site_genre or ""
    industry = u.industry_category_guess

    if genre == "personal_tech_blog" and FORBIDDEN_BLOG_RE.search(text):
        return DimensionResult(
            "WEAK_INDUSTRY_LEAK",
            "fail",
            "forbidden commercial/alternatives template for personal_tech_blog",
        )

    if PM_LEAK_RE.search(text):
        if industry != "project_management":
            return DimensionResult(
                "WEAK_INDUSTRY_LEAK",
                "fail",
                "project_management language without assertive industry evidence",
            )
        if genre == "personal_tech_blog":
            return DimensionResult(
                "WEAK_INDUSTRY_LEAK",
                "fail",
                "PM language incompatible with personal_tech_blog genre",
            )
    # Generic industry tool templates when industry omitted
    if industry is None and re.search(r"\bother \w+ tools\b|\bbest \w+ tool\b", text, re.I):
        return DimensionResult(
            "WEAK_INDUSTRY_LEAK",
            "fail",
            "industry tool template while industry_category omitted",
        )
    return DimensionResult("WEAK_INDUSTRY_LEAK", "pass", "no industry leak")


def evaluate_query(
    q: CandidateQuery,
    understanding: SiteUnderstanding,
    *,
    accepted_texts: list[str] | None = None,
) -> GateDecision:
    dims = [
        _dim_relevance(q, understanding),
        _dim_specificity(q),
        _dim_answerability(q),
        _dim_entity(q, understanding),
        _dim_evidence(q),
        _dim_duplication(q, accepted_texts or []),
        _dim_industry_leak(q, understanding),
    ]
    fails = [d for d in dims if d.status == "fail"]
    warns = [d for d in dims if d.status == "warn"]
    reasons: list[str] = []
    for d in dims:
        if d.status != "pass":
            reasons.append(f"{d.name}:{d.status}:{d.detail}")

    if fails:
        return GateDecision(
            status="reject",
            reasons=reasons,
            dimensions=dims,
            query_id=q.query_id,
        )
    if warns:
        return GateDecision(
            status="accept_with_warning",
            reasons=reasons,
            dimensions=dims,
            query_id=q.query_id,
        )
    return GateDecision(
        status="accept",
        reasons=["all_dimensions_pass"],
        dimensions=dims,
        query_id=q.query_id,
    )


def gate_candidates(
    candidates: list[CandidateQuery],
    understanding: SiteUnderstanding,
) -> tuple[list[tuple[CandidateQuery, GateDecision]], list[tuple[CandidateQuery, GateDecision]]]:
    """Return (accepted, rejected) with decisions. Diagnostic only — not a ranking score."""
    accepted: list[tuple[CandidateQuery, GateDecision]] = []
    rejected: list[tuple[CandidateQuery, GateDecision]] = []
    accepted_texts: list[str] = []
    for q in candidates:
        decision = evaluate_query(q, understanding, accepted_texts=accepted_texts)
        if decision.status in ("accept", "accept_with_warning"):
            accepted.append((q, decision))
            accepted_texts.append(q.text)
        else:
            rejected.append((q, decision))
    return accepted, rejected
