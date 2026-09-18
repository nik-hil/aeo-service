"""Candidate query generation ``candidate-gen-v2`` (Phase 4).

Generic template families parameterized by SiteProfile fields only.
No site-/niche-hardcoded regex packs (no AI-agent special cases, no hostname gates).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from aeo_mvp.queries.generate import CandidateQuery, FunnelStage, QueryIntent
from aeo_mvp.understanding.site import SiteUnderstanding

QUERY_VERSION = "query-v2"
GENERATOR = "candidate-gen-v2"
GENERATOR_PLUGIN_ID = "generic_families_v2"
DISCOVERY_METHOD_V2 = "query-discovery-v2"

_QUESTION_LEAD = re.compile(
    r"^(who|what|when|where|why|how|is|are|can|should|does|do)\b", re.I
)
_WHITESPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[A-Za-z0-9]+")


@dataclass
class PoolPlan:
    min_candidates: int
    max_candidates: int
    grace_mode: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_candidate_pool(
    understanding: SiteUnderstanding,
    *,
    min_candidates: int = 30,
    max_candidates: int = 50,
    page_count: int | None = None,
) -> PoolPlan:
    """Adaptive 30–50 target; small-site grace never fabricates topics."""
    topics = _topic_phrases(understanding)
    strong = [t for t in topics if len(t) >= 8]
    pages = page_count
    if pages is None:
        pages = len(understanding.important_pages or []) or None
    grace = False
    warnings: list[str] = []
    lo, hi = min_candidates, max_candidates
    if len(strong) < 4 or (pages is not None and pages < 5):
        grace = True
        lo = max(12, min(12 + len(strong) * 3, 25))
        hi = max(lo, min(25, 14 + len(strong) * 4))
        warnings.append("SMALL_SITE_POOL")
    return PoolPlan(
        min_candidates=lo,
        max_candidates=hi,
        grace_mode=grace,
        warnings=warnings,
    )


def _stable_id(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
    return f"q_{h}"


def _evidence_classes_from_understanding(
    u: SiteUnderstanding,
) -> dict[str, list[dict[str, Any]]]:
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
            cls = ev.get("evidence_class") or "metadata"
            classes.setdefault(cls, []).append(ev)
    if u.topics:
        classes.setdefault("title_h1", []).append(
            {
                "snippet": u.topics[0],
                "evidence_class": "title_h1",
                "locator": "legacy_topic",
            }
        )
    if u.organization_brand:
        classes.setdefault("og_meta", []).append(
            {
                "snippet": u.organization_brand,
                "evidence_class": "og_meta",
                "locator": "legacy_brand",
            }
        )
    if u.site_genre:
        classes.setdefault("jsonld", []).append(
            {
                "snippet": u.site_genre,
                "evidence_class": "jsonld",
                "locator": "legacy_genre",
            }
        )
    return classes


def _has_min_evidence(classes: dict[str, list]) -> tuple[bool, list[str]]:
    present = {c for c, items in classes.items() if items and c != "chrome"}
    return len(present) >= 2, sorted(present)


def _clean_topic_phrase(raw: str) -> str:
    t = raw.strip()
    if t.startswith("#"):
        return t.lstrip("#").replace("-", " ")
    t = re.sub(r"\s*[—|]\s*.*$", "", t).strip()
    t = re.sub(r"\s+-\s+.*$", "", t).strip()
    return _WHITESPACE.sub(" ", t)


def _topic_phrases(u: SiteUnderstanding) -> list[str]:
    out: list[str] = []
    for t in u.topics:
        cleaned = _clean_topic_phrase(t)
        if len(cleaned) < 4:
            continue
        out.append(cleaned)
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        k = x.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    return uniq[:16]


def _is_questionish(text: str) -> bool:
    t = text.strip()
    return t.endswith("?") or bool(_QUESTION_LEAD.match(t))


def _embeddable_topic(t: str) -> str | None:
    """Phrase safe to wrap in How/What templates (not already a question)."""
    t_clean = t.rstrip("?").strip()
    if len(t_clean) < 6:
        return None
    if _is_questionish(t):
        return None
    tokens = _TOKEN.findall(t_clean)
    if len(tokens) < 2:
        return None
    return t_clean[:80]


def generate_candidates_v2(
    understanding: SiteUnderstanding,
    *,
    min_candidates: int = 30,
    max_candidates: int = 50,
    page_count: int | None = None,
) -> tuple[list[CandidateQuery], PoolPlan]:
    """Generate candidates from evidence via generic template families."""
    plan = plan_candidate_pool(
        understanding,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
        page_count=page_count,
    )
    classes = _evidence_classes_from_understanding(understanding)
    ok, present = _has_min_evidence(classes)
    if not ok:
        return [], plan

    brand = (understanding.organization_brand or "").strip()
    genre = understanding.site_genre or ""
    industry = understanding.industry_category_guess
    topics = _topic_phrases(understanding)
    audience = (
        understanding.audience_hints[0] if understanding.audience_hints else None
    )
    has_commercial = bool(understanding.commercial_intents)
    products = [p for p in understanding.products_services if not str(p).startswith("#")]

    is_personal_blog = genre == "personal_tech_blog"
    is_saas = genre in ("saas_product",) or bool(products and has_commercial)
    is_docs = genre in ("documentation", "docs", "developer_docs")
    is_ecommerce = genre in ("ecommerce", "e-commerce", "shop")

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
        if len(out) >= plan.max_candidates:
            return
        text = _WHITESPACE.sub(" ", (text or "").strip())
        if not text or len(text) < 8:
            return
        # Never emit double-interrogative wraps
        if re.search(
            r"\b(how does|what is|why does|how to)\s+(who|what|when|where|why|how)\b",
            text,
            re.I,
        ):
            return
        used = [k for k in evidence_keys if k in classes and classes[k]]
        if len(set(used)) < 2 and len(present) >= 2:
            used = present[:2]
        if len(set(used)) < 2:
            return
        ev: list[dict[str, Any]] = []
        for k in used[:3]:
            ev.extend(classes[k][:1])
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
                query_version=QUERY_VERSION,
                generator=GENERATOR,
                evidence_classes=sorted(set(used)),
            )
        )

    # --- Navigational / brand ---
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
            f"Where can I find content from {brand}?",
            topic="brand",
            entity=brand,
            funnel="awareness",
            rationale="Publication navigational",
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

    # --- Informational ---
    for t in topics[:12]:
        if _is_questionish(t):
            q = t if t.endswith("?") else t.rstrip("?") + "?"
            add(
                "informational",
                q,
                topic=t[:80],
                entity=brand or None,
                funnel="awareness",
                rationale="Evidence heading already question-shaped",
                confidence=0.36,
                evidence_keys=["title_h1", "tags_series", "jsonld"],
            )
            continue
        slot = _embeddable_topic(t)
        if not slot:
            continue
        # Skip wrapping brand name as a topical "what is"
        if brand and slot.lower() == brand.lower():
            continue
        add(
            "informational",
            f"What is {slot}?",
            topic=slot,
            entity=brand or None,
            funnel="awareness",
            rationale="Topic gloss from evidence",
            confidence=0.34,
            evidence_keys=["title_h1", "article_body", "tags_series"],
        )
        add(
            "informational",
            f"Explain {slot}",
            topic=slot,
            entity=brand or None,
            funnel="awareness",
            rationale="Topic explain from evidence",
            confidence=0.32,
            evidence_keys=["title_h1", "jsonld", "tags_series"],
        )

    # --- Problem-solving ---
    for t in topics[:10]:
        slot = _embeddable_topic(t)
        if not slot:
            continue
        if brand and slot.lower() == brand.lower():
            continue
        add(
            "problem_solving",
            f"How does {slot} work?",
            topic=slot,
            entity=brand or None,
            funnel="consideration",
            rationale="How-it-works from topic evidence",
            confidence=0.34,
            evidence_keys=["title_h1", "article_body", "tags_series"],
        )
        add(
            "problem_solving",
            f"How to get started with {slot}",
            topic=slot,
            entity=brand or None,
            funnel="consideration",
            rationale="Getting-started how-to from topic evidence",
            confidence=0.33,
            evidence_keys=["title_h1", "tags_series", "jsonld"],
        )
        if is_docs:
            add(
                "problem_solving",
                f"How do I troubleshoot {slot}?",
                topic=slot,
                entity=brand or None,
                funnel="consideration",
                rationale="Docs troubleshooting family",
                confidence=0.32,
                evidence_keys=["title_h1", "article_body", "url_path"],
            )

    # --- Recommendation ---
    for t in topics[:6]:
        slot = _embeddable_topic(t)
        if not slot:
            continue
        if brand and slot.lower() == brand.lower():
            continue
        add(
            "recommendation",
            f"What are good resources for learning {slot}?",
            topic=slot,
            entity=brand or None,
            funnel="consideration",
            rationale="Learning resource recommendation from topics",
            confidence=0.32,
            evidence_keys=["title_h1", "tags_series", "jsonld"],
        )

    if brand and topics:
        # Generic publication recommendation — topic-derived, not niche-hardcoded
        top = _embeddable_topic(topics[0]) or topics[0][:60]
        if top and (not brand or top.lower() != brand.lower()):
            add(
                "recommendation",
                f"Is {brand} a useful resource on {top}?",
                topic=top[:80],
                entity=brand,
                funnel="consideration",
                rationale="Publication recommendation grounded in primary topic",
                confidence=0.30,
                evidence_keys=["title_h1", "tags_series", "og_meta"],
            )

    # --- Comparison ---
    if is_personal_blog or is_docs:
        for t in topics[:5]:
            slot = _embeddable_topic(t)
            if not slot:
                continue
            add(
                "comparison",
                f"How does {slot} compare to other approaches?",
                topic=slot,
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

    # --- SaaS / ecommerce commercial (FORBIDDEN for personal_tech_blog) ---
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

    if is_ecommerce and products:
        for p in products[:4]:
            add(
                "commercial",
                f"Where can I buy {p}?",
                topic=str(p)[:80],
                entity=brand or str(p),
                funnel="decision",
                rationale="Ecommerce product commercial family",
                confidence=0.33,
                evidence_keys=["jsonld", "title_h1", "url_path"],
            )
            add(
                "comparison",
                f"How does {p} compare to similar products?",
                topic=str(p)[:80],
                entity=brand or str(p),
                funnel="consideration",
                rationale="Ecommerce comparison family",
                confidence=0.31,
                evidence_keys=["jsonld", "title_h1", "article_body"],
            )

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

    # --- Pad to pool target without fabricating topics ---
    if len(out) < plan.min_candidates:
        for t in topics:
            if len(out) >= plan.min_candidates:
                break
            slot = _embeddable_topic(t)
            if not slot:
                continue
            if brand and slot.lower() == brand.lower():
                continue
            add(
                "informational",
                f"What should I know about {slot}?",
                topic=slot,
                entity=brand or None,
                funnel="awareness",
                rationale="Padding informational from remaining topics",
                confidence=0.28,
                evidence_keys=["title_h1", "tags_series", "article_body"],
            )
            if len(out) >= plan.min_candidates:
                break
            add(
                "problem_solving",
                f"What are common challenges with {slot}?",
                topic=slot,
                entity=brand or None,
                funnel="consideration",
                rationale="Padding problem_solving from topics",
                confidence=0.28,
                evidence_keys=["title_h1", "article_body", "tags_series"],
            )

    # Annotate generator plugin for audit (non-breaking extra on rationale path)
    for q in out:
        if "generator_plugin" not in q.rationale:
            q.rationale = f"{q.rationale} [{GENERATOR_PLUGIN_ID}]"

    return out[: plan.max_candidates], plan
