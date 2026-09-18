"""Query quality diagnostics ``query-quality-v1`` (Phase 4).

Decomposable per-candidate dimensions with pass/warn/fail. Diagnostic only —
never a website score; never folded into health-v1.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from aeo_mvp.queries.evidence import observed_evidence_classes
from aeo_mvp.queries.generate import CandidateQuery
from aeo_mvp.queries.normalize import (
    is_near_duplicate,
    normalize_query_text,
    tokenize,
)
from aeo_mvp.queries.quality_policy import industry_leak_detail
from aeo_mvp.understanding.site import SiteUnderstanding

QUALITY_VERSION = "query-quality-v1"
# Set-level diagnostic IDs (methodology QUERY_SET_QUALITY)
QSQ_IDS = (
    "QSQ-SPEC",
    "QSQ-ANS",
    "QSQ-REL",
    "QSQ-ENT",
    "QSQ-EVD",
    "QSQ-DEDUP",
    "QSQ-DIV",
    "QSQ-LEAK",
    "QSQ-DET",
    "QSQ-COV",
)

DimStatus = Literal["pass", "fail", "warn"]
GateStatus = Literal["accept", "reject", "accept_with_warning"]

# Title-wrap / double-interrogative garbage (generic — not genre policy)
DOUBLE_INTERROGATIVE_RE = re.compile(
    r"\b(how does|what is|why does|how to|explain)\s+"
    r"(who|what|when|where|why|how|is|are|does|do)\b",
    re.I,
)
TEMPLATE_GLUE_RE = re.compile(
    r"\b(how does how|what is what|why does why|key concepts in .+blog|"
    r"common (pitfalls|challenges) (when working )?with .+blog)\b",
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
    quality_version: str = QUALITY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "dimensions": [d.to_dict() for d in self.dimensions],
            "query_id": self.query_id,
            "quality_version": self.quality_version,
        }


def _dim_relevance(q: CandidateQuery, u: SiteUnderstanding) -> DimensionResult:
    topics = [t.lower() for t in u.topics]
    text = q.text.lower()
    if q.topic and any(
        q.topic.lower()[:20] in t or t[:20] in text for t in topics if t
    ):
        return DimensionResult("relevance", "pass", "topic aligns with site evidence")
    if u.organization_brand and u.organization_brand.lower() in text:
        return DimensionResult("relevance", "pass", "brand navigational relevance")
    if q.intent in ("informational", "problem_solving") and q.topic:
        return DimensionResult("relevance", "warn", "topic weakly grounded")
    return DimensionResult("relevance", "fail", "no topic/brand alignment")


def _dim_specificity(q: CandidateQuery) -> DimensionResult:
    tokens = list(tokenize(q.text))
    if len(tokens) < 3:
        return DimensionResult("specificity", "fail", "too short / generic")
    if len(tokens) > 24:
        return DimensionResult("specificity", "warn", "overly long")
    vague = {"best tools", "leading options", "top software", "what is ai"}
    if normalize_query_text(q.text) in vague:
        return DimensionResult("specificity", "fail", "generic template")
    # Heading-literal paste: topic equals full text minus punctuation and is very long
    if q.topic and normalize_query_text(q.topic) == normalize_query_text(q.text):
        if len(tokens) > 14:
            return DimensionResult(
                "specificity", "fail", "heading-literal paste without template shape"
            )
    return DimensionResult("specificity", "pass", "adequate specificity")


def _dim_answerability(q: CandidateQuery) -> DimensionResult:
    if DOUBLE_INTERROGATIVE_RE.search(q.text) or TEMPLATE_GLUE_RE.search(q.text):
        return DimensionResult(
            "answerability", "fail", "ungrammatical / nonsensical template"
        )
    if q.intent in ("informational", "problem_solving", "navigational"):
        return DimensionResult("answerability", "pass", "question-form intent")
    if q.intent == "commercial" and "cost" in q.text.lower():
        return DimensionResult("answerability", "warn", "pricing may be unknowable")
    return DimensionResult("answerability", "pass", "answerable intent")


def _dim_grammaticality(q: CandidateQuery) -> DimensionResult:
    text = q.text.strip()
    if DOUBLE_INTERROGATIVE_RE.search(text):
        return DimensionResult(
            "grammaticality_lint",
            "fail",
            "double-interrogative / title-wrap garbage",
        )
    if TEMPLATE_GLUE_RE.search(text):
        return DimensionResult(
            "grammaticality_lint", "fail", "template glue failure"
        )
    # Nested question marks or "How does Why"
    if re.search(r"\?\s*\?", text):
        return DimensionResult("grammaticality_lint", "fail", "double question marks")
    if re.search(r"\b(How does|What is|Why does)\s+(Why|What|How|Who)\b", text):
        return DimensionResult(
            "grammaticality_lint", "fail", "stacked question words"
        )
    return DimensionResult("grammaticality_lint", "pass", "no lint failures")


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
    """Strongest QSQ-EVD: only provenance=observed classes count (≥2 required)."""
    observed = observed_evidence_classes(q.source_evidence)
    # Fallback: evidence_classes alone without source_evidence → treat as
    # compatibility (legacy), which does NOT satisfy strongest QSQ-EVD.
    if not q.source_evidence and q.evidence_classes:
        return DimensionResult(
            "evidence_support",
            "fail",
            "evidence_classes without observed provenance (compatibility/legacy)",
        )
    if len(observed) >= 2:
        return DimensionResult(
            "evidence_support",
            "pass",
            f"observed_classes={sorted(observed)}",
        )
    if len(observed) == 1:
        return DimensionResult(
            "evidence_support",
            "fail",
            f"only one observed evidence class ({sorted(observed)}); "
            "derived/compatibility do not count toward strongest QSQ-EVD",
        )
    return DimensionResult(
        "evidence_support",
        "fail",
        "no observed evidence classes (derived/compatibility-only insufficient)",
    )


def _dim_duplication(
    q: CandidateQuery, accepted_texts: list[str]
) -> DimensionResult:
    for prev in accepted_texts:
        if is_near_duplicate(q.text, prev):
            return DimensionResult("duplication", "fail", f"near-dup of {prev[:60]}")
    return DimensionResult("duplication", "pass", "unique vs accepted set")


def _dim_intent_consistency(q: CandidateQuery) -> DimensionResult:
    text = q.text.lower()
    if q.intent == "navigational" and not any(
        x in text for x in ("what is", "where can", "who is", "find")
    ):
        return DimensionResult(
            "intent_label_consistency", "warn", "navigational shape weak"
        )
    if q.intent == "commercial" and not any(
        x in text for x in ("cost", "price", "buy", "trial", "paid", "sponsor")
    ):
        return DimensionResult(
            "intent_label_consistency", "warn", "commercial shape weak"
        )
    if q.intent == "comparison" and "compar" not in text and "alternative" not in text:
        return DimensionResult(
            "intent_label_consistency", "warn", "comparison shape weak"
        )
    return DimensionResult("intent_label_consistency", "pass", "intent matches surface")


def _dim_industry_leak(q: CandidateQuery, u: SiteUnderstanding) -> DimensionResult:
    leak = industry_leak_detail(q, u)
    if leak is None:
        return DimensionResult("WEAK_INDUSTRY_LEAK", "pass", "no industry leak")
    status, detail = leak
    dim_status: DimStatus = "fail" if status == "fail" else "warn"
    return DimensionResult("WEAK_INDUSTRY_LEAK", dim_status, detail)


def evaluate_query_v2(
    q: CandidateQuery,
    understanding: SiteUnderstanding,
    *,
    accepted_texts: list[str] | None = None,
) -> GateDecision:
    dims = [
        _dim_relevance(q, understanding),
        _dim_specificity(q),
        _dim_answerability(q),
        _dim_grammaticality(q),
        _dim_entity(q, understanding),
        _dim_evidence(q),
        _dim_duplication(q, accepted_texts or []),
        _dim_intent_consistency(q),
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


def gate_candidates_v2(
    candidates: list[CandidateQuery],
    understanding: SiteUnderstanding,
) -> tuple[
    list[tuple[CandidateQuery, GateDecision]],
    list[tuple[CandidateQuery, GateDecision]],
]:
    accepted: list[tuple[CandidateQuery, GateDecision]] = []
    rejected: list[tuple[CandidateQuery, GateDecision]] = []
    accepted_texts: list[str] = []
    for q in candidates:
        decision = evaluate_query_v2(q, understanding, accepted_texts=accepted_texts)
        if decision.status in ("accept", "accept_with_warning"):
            accepted.append((q, decision))
            accepted_texts.append(q.text)
        else:
            rejected.append((q, decision))
    return accepted, rejected


def aggregate_set_diagnostics(
    *,
    selected_texts: list[str],
    rejected_count: int,
    accepted_count: int,
    intent_breakdown: dict[str, int],
    topic_breakdown: dict[str, int],
    fingerprint: str | None = None,
) -> dict[str, Any]:
    """Descriptive set-level panels — never a single website quality score."""
    total = accepted_count + rejected_count
    reject_rate = (rejected_count / total) if total else 0.0
    max_topic_share = 0.0
    if topic_breakdown and selected_texts:
        max_topic_share = max(topic_breakdown.values()) / max(len(selected_texts), 1)
    panels = {
        "QSQ-DEDUP": {
            "verdict": "pass",
            "detail": "selected set built after near-dup gate",
        },
        "QSQ-DIV": {
            "verdict": "pass" if len(intent_breakdown) >= 3 else "warn",
            "intent_breakdown": intent_breakdown,
        },
        "QSQ-COV": {
            "verdict": "warn" if max_topic_share > 0.40 else "pass",
            "max_topic_share": round(max_topic_share, 3),
            "topic_breakdown": dict(list(topic_breakdown.items())[:12]),
        },
        "QSQ-DET": {
            "verdict": "pass" if fingerprint else "warn",
            "fingerprint": fingerprint,
        },
    }
    return {
        "quality_version": QUALITY_VERSION,
        "reject_rate": round(reject_rate, 3),
        "panels": panels,
        # Forbidden product language guardrail in payload comments via key naming
        "note": "query-set diagnostics only — not an AEO/site grade",
    }
