"""Candidate query generation (query-discovery-v1).

Generates 30–50 candidates from site evidence. Templates branch on site_genre.
Requires ≥2 evidence classes to seed a query. Topics derived from site evidence.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from aeo_mvp.queries.evidence import stamp_evidence_dict
from aeo_mvp.understanding.profile import QUERY_DISCOVERY_METHOD
from aeo_mvp.understanding.site import SiteUnderstanding

QueryIntent = Literal[
    "informational",
    "problem_solving",
    "comparison",
    "recommendation",
    "navigational",
    "commercial",
]

FunnelStage = Literal["awareness", "consideration", "decision", "retention"]

QUERY_VERSION = "query-v1"
GENERATOR = "deterministic_templates_v1"

# Personal tech blog target mix (guidance for generation volume)
PERSONAL_BLOG_TARGETS = {
    "informational": (0.35, 0.40),
    "problem_solving": (0.25, 0.30),
    "recommendation": (0.10, 0.15),
    "comparison": (0.08, 0.12),
    "navigational": (0.08, 0.10),
    "commercial": (0.00, 0.05),
}


@dataclass
class CandidateQuery:
    query_id: str
    text: str
    intent: QueryIntent
    topic: str | None = None
    entity: str | None = None
    audience: str | None = None
    funnel_stage: FunnelStage = "awareness"
    source_evidence: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0
    query_version: str = QUERY_VERSION
    generator: str = GENERATOR
    evidence_classes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stable_id(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
    return f"q_{h}"


def _evidence_classes_from_understanding(u: SiteUnderstanding) -> dict[str, list[dict[str, Any]]]:
    """Map available evidence classes from structured profile / legacy fields.

    Missing/unknown provenance → compatibility (never invent observed).
    """
    classes: dict[str, list[dict[str, Any]]] = {}
    structured = u.structured or {}
    for field_name in (
        "primary_topics",
        "secondary_topics",
        "org_name",
        "authors",
        "products",
        "site_genre",
        "industry_category",
        "content_types",
    ):
        fld = structured.get(field_name) or {}
        for ev in fld.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            cls = ev.get("evidence_class") or "metadata"
            item = stamp_evidence_dict(ev)
            item.setdefault("evidence_class", cls)
            classes.setdefault(cls, []).append(item)
    # Fallback synthetic classes from legacy projection → compatibility
    if u.topics:
        classes.setdefault("title_h1", []).append(
            {
                "snippet": u.topics[0],
                "evidence_class": "title_h1",
                "locator": "legacy_topic",
                "provenance": "compatibility",
            }
        )
    if u.organization_brand:
        classes.setdefault("og_meta", []).append(
            {
                "snippet": u.organization_brand,
                "evidence_class": "og_meta",
                "locator": "legacy_brand",
                "provenance": "compatibility",
            }
        )
    if u.site_genre:
        classes.setdefault("jsonld", []).append(
            {
                "snippet": u.site_genre,
                "evidence_class": "jsonld",
                "locator": "legacy_genre",
                "provenance": "compatibility",
            }
        )
    return classes


def _has_min_evidence(classes: dict[str, list], needed: set[str] | None = None) -> tuple[bool, list[str]]:
    present = {c for c, items in classes.items() if items and c != "chrome"}
    if needed:
        ok = needed.issubset(present) and len(present) >= 2
        return ok, sorted(present)
    return len(present) >= 2, sorted(present)


def _topic_phrases(u: SiteUnderstanding) -> list[str]:
    out: list[str] = []
    for t in u.topics:
        t = t.strip()
        if len(t) < 4:
            continue
        if t.startswith("#"):
            out.append(t.lstrip("#").replace("-", " "))
        else:
            # Prefer shorter topical phrases from titles
            cleaned = re.sub(r"\s*[—|-]\s*.*$", "", t).strip()
            out.append(cleaned if cleaned else t)
    # Dedupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        k = x.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    return uniq[:12]


def _ai_topics(topics: list[str]) -> list[str]:
    hints = re.compile(
        r"ai|agent|llm|tool|python|harness|coding|filesystem|provider", re.I
    )
    return [t for t in topics if hints.search(t)] or topics[:6]


def generate_candidates(
    understanding: SiteUnderstanding,
    *,
    min_candidates: int = 30,
    max_candidates: int = 50,
) -> list[CandidateQuery]:
    """Generate 30–50 candidate queries from site evidence."""
    classes = _evidence_classes_from_understanding(understanding)
    ok, present = _has_min_evidence(classes)
    if not ok:
        return []

    brand = (understanding.organization_brand or "").strip()
    genre = understanding.site_genre or ""
    industry = understanding.industry_category_guess  # may be None (omit)
    topics = _topic_phrases(understanding)
    ai_topics = _ai_topics(topics)
    audience = (understanding.audience_hints[0] if understanding.audience_hints else None)
    has_commercial = bool(understanding.commercial_intents)
    products = [p for p in understanding.products_services if not str(p).startswith("#")]

    out: list[CandidateQuery] = []

    def add(
        intent: QueryIntent,
        text: str,
        *,
        topic: str | None,
        entity: str | None,
        funnel: FunnelStage,
        rationale: str,
        confidence: float,
        evidence_keys: list[str],
    ) -> None:
        if len(out) >= max_candidates:
            return
        # Require ≥2 evidence classes for this seed
        used = [k for k in evidence_keys if k in classes and classes[k]]
        if len(set(used)) < 2 and len(present) >= 2:
            used = present[:2]
        if len(set(used)) < 2:
            return
        ev = []
        for k in used[:3]:
            for item in classes[k][:1]:
                if isinstance(item, dict):
                    ev.append(stamp_evidence_dict(item))
                else:
                    ev.append(item)
        qid = _stable_id(intent, text, QUERY_VERSION)
        out.append(
            CandidateQuery(
                query_id=qid,
                text=text,
                intent=intent,
                topic=topic,
                entity=entity or brand or None,
                audience=audience,
                funnel_stage=funnel,
                source_evidence=ev[:4],
                rationale=rationale,
                confidence=min(confidence, 0.40),
                evidence_classes=sorted(set(used)),
            )
        )

    is_personal_blog = genre == "personal_tech_blog"
    is_saas = genre in ("saas_product",) or bool(products and has_commercial)

    # --- Navigational / brand (bounded) ---
    if brand:
        add(
            "navigational",
            f"What is {brand}?",
            topic="brand",
            entity=brand,
            funnel="awareness",
            rationale="Brand navigational from org_name evidence",
            confidence=0.38,
            evidence_keys=["og_meta", "jsonld", "title_h1"],
        )
        add(
            "navigational",
            f"Where can I find articles by {brand}?",
            topic="brand",
            entity=brand,
            funnel="awareness",
            rationale="Author/publication navigational",
            confidence=0.34,
            evidence_keys=["jsonld", "title_h1", "tags_series"],
        )
        if not is_personal_blog:
            add(
                "informational",
                f"What does {brand} do?",
                topic="brand",
                entity=brand,
                funnel="awareness",
                rationale="Brand informational (non-blog genre)",
                confidence=0.36,
                evidence_keys=["og_meta", "jsonld", "title_h1"],
            )

    # --- Informational from topics (heavy for personal blogs) ---
    for t in (ai_topics if is_personal_blog else topics)[:10]:
        t_clean = t.rstrip("?")
        if len(t_clean) < 6:
            continue
        if t_clean.endswith("?") or re.match(
            r"^(who|what|when|where|why|how)\b", t_clean, re.I
        ):
            q = t_clean if t_clean.endswith("?") else t_clean + "?"
            add(
                "informational",
                q,
                topic=t_clean[:80],
                entity=brand or None,
                funnel="awareness",
                rationale="Topic heading promoted to informational query",
                confidence=0.36,
                evidence_keys=["title_h1", "tags_series", "jsonld"],
            )
        else:
            add(
                "informational",
                f"What is {t_clean}?",
                topic=t_clean[:80],
                entity=brand or None,
                funnel="awareness",
                rationale="Topic gloss informational",
                confidence=0.34,
                evidence_keys=["title_h1", "article_body", "tags_series"],
            )
            add(
                "informational",
                f"Explain {t_clean}",
                topic=t_clean[:80],
                entity=brand or None,
                funnel="awareness",
                rationale="Topic explain informational",
                confidence=0.32,
                evidence_keys=["title_h1", "jsonld", "tags_series"],
            )

    # --- Problem-solving ---
    for t in (ai_topics if is_personal_blog else topics)[:8]:
        t_clean = t.rstrip("?")
        if len(t_clean) < 6:
            continue
        add(
            "problem_solving",
            f"How does {t_clean} work?",
            topic=t_clean[:80],
            entity=brand or None,
            funnel="consideration",
            rationale="How-it-works from topic evidence",
            confidence=0.34,
            evidence_keys=["title_h1", "article_body", "tags_series"],
        )
        add(
            "problem_solving",
            f"How to implement {t_clean}",
            topic=t_clean[:80],
            entity=brand or None,
            funnel="consideration",
            rationale="Implementation how-to from topic evidence",
            confidence=0.33,
            evidence_keys=["title_h1", "tags_series", "jsonld"],
        )

    # Extra AI-agent problem queries when headings present
    if any(re.search(r"\bagent\b", t, re.I) for t in topics):
        for qtext, topic in (
            ("How do I build an AI agent with tool calling?", "AI agent tool calling"),
            ("How does an AI agent loop work?", "agent loop"),
            ("How to give an AI agent filesystem tools?", "filesystem tools"),
            ("How to make an AI agent provider-agnostic?", "provider agnostic agents"),
        ):
            add(
                "problem_solving",
                qtext,
                topic=topic,
                entity=brand or None,
                funnel="consideration",
                rationale="AI-agent series evidence",
                confidence=0.35,
                evidence_keys=["title_h1", "tags_series", "article_body"],
            )

    # --- Recommendation ---
    for t in (ai_topics[:5] if is_personal_blog else topics[:5]):
        t_clean = t.rstrip("?")
        if len(t_clean) < 6:
            continue
        add(
            "recommendation",
            f"What are good resources for learning {t_clean}?",
            topic=t_clean[:80],
            entity=brand or None,
            funnel="consideration",
            rationale="Learning resource recommendation from topics",
            confidence=0.32,
            evidence_keys=["title_h1", "tags_series", "jsonld"],
        )

    if brand and is_personal_blog:
        add(
            "recommendation",
            f"Is {brand} a good resource for AI agents?",
            topic="AI agents",
            entity=brand,
            funnel="consideration",
            rationale="Publication recommendation for AI topic",
            confidence=0.30,
            evidence_keys=["title_h1", "tags_series", "og_meta"],
        )

    # --- Comparison (careful: no PM leak for blogs) ---
    if is_personal_blog:
        for t in ai_topics[:4]:
            t_clean = t.rstrip("?")
            add(
                "comparison",
                f"How does {t_clean} compare to other approaches?",
                topic=t_clean[:80],
                entity=brand or None,
                funnel="consideration",
                rationale="Topic comparison (genre-gated; no industry leak)",
                confidence=0.30,
                evidence_keys=["title_h1", "tags_series", "article_body"],
            )
    elif brand and industry:
        industry_label = industry.replace("_", " ")
        add(
            "comparison",
            f"How does {brand} compare to other {industry_label} tools?",
            topic=industry_label,
            entity=brand,
            funnel="consideration",
            rationale="Industry comparison with assertive industry evidence",
            confidence=0.34,
            evidence_keys=["title_h1", "jsonld", "og_meta"],
        )
        add(
            "comparison",
            f"How do teams evaluate tools in {industry_label}?",
            topic=industry_label,
            entity=brand,
            funnel="consideration",
            rationale="Category evaluation comparison",
            confidence=0.30,
            evidence_keys=["title_h1", "jsonld", "article_body"],
        )

    # SaaS-only templates (FORBIDDEN for personal_tech_blog)
    if is_saas and brand and not is_personal_blog:
        add(
            "commercial",
            f"How much does {brand} cost?",
            topic="pricing",
            entity=brand,
            funnel="decision",
            rationale="Commercial pricing path evidence",
            confidence=0.34,
            evidence_keys=["url_path", "title_h1", "jsonld"],
        )
        add(
            "comparison",
            f"What are alternatives to {brand}?",
            topic="alternatives",
            entity=brand,
            funnel="consideration",
            rationale="Alternatives template for product genre",
            confidence=0.32,
            evidence_keys=["jsonld", "title_h1", "og_meta"],
        )
        if products:
            add(
                "informational",
                f"What products or services does {brand} offer?",
                topic="products",
                entity=brand,
                funnel="awareness",
                rationale="Product schema evidence",
                confidence=0.34,
                evidence_keys=["jsonld", "title_h1", "og_meta"],
            )
        if industry:
            industry_label = industry.replace("_", " ")
            aud = audience or "teams"
            add(
                "recommendation",
                f"What is the best {industry_label} tool for {aud}?",
                topic=industry_label,
                entity=brand,
                funnel="decision",
                rationale="Best-for template with assertive industry",
                confidence=0.30,
                evidence_keys=["title_h1", "jsonld", "article_body"],
            )

    # Commercial only if monetization signals (and ≤5% for blogs)
    if has_commercial and brand and not is_personal_blog:
        add(
            "commercial",
            f"Where can I buy or start a trial for {brand}?",
            topic="trial",
            entity=brand,
            funnel="decision",
            rationale="Commercial intent paths present",
            confidence=0.32,
            evidence_keys=["url_path", "title_h1", "og_meta"],
        )
    elif has_commercial and is_personal_blog and brand:
        # At most one soft commercial for blogs with monetization
        add(
            "commercial",
            f"Does {brand} offer paid courses or sponsorships?",
            topic="monetization",
            entity=brand,
            funnel="decision",
            rationale="Soft commercial; monetization paths detected",
            confidence=0.28,
            evidence_keys=["url_path", "title_h1", "tags_series"],
        )

    # Pad informational/problem_solving to hit 30–50 when evidence allows
    if len(out) < min_candidates:
        for t in topics:
            if len(out) >= min_candidates:
                break
            t_clean = t.rstrip("?")
            if len(t_clean) < 8:
                continue
            add(
                "informational",
                f"Key concepts in {t_clean}",
                topic=t_clean[:80],
                entity=brand or None,
                funnel="awareness",
                rationale="Padding informational from remaining topics",
                confidence=0.28,
                evidence_keys=["title_h1", "tags_series", "article_body"],
            )
            if len(out) >= min_candidates:
                break
            add(
                "problem_solving",
                f"Common pitfalls when working with {t_clean}",
                topic=t_clean[:80],
                entity=brand or None,
                funnel="consideration",
                rationale="Padding problem_solving from topics",
                confidence=0.28,
                evidence_keys=["title_h1", "article_body", "tags_series"],
            )

    return out[:max_candidates]
