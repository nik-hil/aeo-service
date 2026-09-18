"""Deterministic site understanding from crawled HTML (P1-B + Phase 3).

Builds StructuredSiteProfile (evidence-first), then projects a legacy
SiteUnderstanding view for existing report/orchestrator consumers.

LLM enrichment is optional and off by default (requires OPENAI_API_KEY + flag).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from aeo_mvp.analyzers.base import (
    EvidenceAtom,
    homepage,
    persist_evidence,
)
from aeo_mvp.db.models import Page, SiteProfile, new_id, utc_now_iso
from aeo_mvp.understanding.builder import build_structured_profile
from aeo_mvp.understanding.profile import StructuredSiteProfile, merge_llm_field
from sqlalchemy.orm import Session

# Re-export keyword tables for tests that may patch legacy names
from aeo_mvp.understanding.builder import (  # noqa: F401
    INDUSTRY_STRONG,
    INDUSTRY_WEAK,
)


@dataclass
class SiteUnderstanding:
    """Legacy projection kept for report/orchestrator compatibility."""

    organization_brand: str | None = None
    products_services: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    audience_hints: list[str] = field(default_factory=list)
    industry_category_guess: str | None = None
    site_genre: str | None = None
    commercial_intents: list[str] = field(default_factory=list)
    important_pages: list[dict[str, Any]] = field(default_factory=list)
    provenance: str = "derived_metric"
    method: str = "site-profile-v1"
    evidence_refs: list[str] = field(default_factory=list)
    llm_used: bool = False
    structured: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    evidence_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def project_understanding(profile: StructuredSiteProfile, *, provenance: str) -> SiteUnderstanding:
    """Project StructuredSiteProfile → SiteUnderstanding (no silent industry promotion)."""
    industry = profile.assertive_industry()  # None when omitted / low confidence
    topics = profile.topic_list()
    products = profile.products.value if not profile.products.omitted else []
    # Guard: never treat hashtag tokens as products
    products = [p for p in (products or []) if not str(p).startswith("#")]
    audience = profile.audience.value if not profile.audience.omitted else []
    commercial = (
        profile.commercial_signals.value if not profile.commercial_signals.omitted else []
    )
    brand = profile.org_name.value if not profile.org_name.omitted else None
    genre = profile.genre_value()

    return SiteUnderstanding(
        organization_brand=brand,
        products_services=list(products or []),
        topics=topics,
        audience_hints=list(audience or []),
        industry_category_guess=industry,
        site_genre=genre,
        commercial_intents=list(commercial or []),
        important_pages=list(profile.important_pages),
        provenance=provenance,
        method=profile.method,
        llm_used=profile.llm_used,
        structured=profile.to_dict(),
        warnings=list(profile.warnings),
        evidence_hash=profile.evidence_hash,
    )


def infer_site_understanding(
    session: Session,
    job_id: str,
    pages: list[Page],
    base_url: str,
    *,
    provenance: str = "derived_metric",
    use_llm: bool = False,
    openai_api_key: str | None = None,
) -> SiteUnderstanding:
    """Infer site profile deterministically. LLM path is opt-in and non-overwriting."""
    structured = build_structured_profile(pages, base_url, provenance=provenance)

    # Optional LLM — only if explicitly enabled AND key present. Default off.
    # Never overwrite strong deterministic fields without justification.
    if use_llm and openai_api_key:
        # Intentionally not calling paid APIs in unit/default path.
        structured.method = f"{structured.method}+llm_flag_acknowledged_unimplemented"
        structured.llm_used = False
        structured.warnings.append("llm_assist_opt_in_but_unimplemented")
        _ = merge_llm_field  # available for future assist wiring

    understanding = project_understanding(structured, provenance=provenance)

    atoms = [
        EvidenceAtom(
            analyzer="site_understanding",
            code="SITE_PROFILE",
            severity="info",
            message=(
                f"Inferred brand={understanding.organization_brand!r} "
                f"genre={understanding.site_genre!r} "
                f"industry={understanding.industry_category_guess!r}"
            ),
            data=understanding.to_dict(),
            page_id=homepage(pages).id if homepage(pages) else None,
            provenance=provenance,
        )
    ]
    rows = persist_evidence(session, job_id, atoms)
    understanding.evidence_refs = [r.id for r in rows]

    existing = session.query(SiteProfile).filter(SiteProfile.job_id == job_id).one_or_none()
    payload = json.dumps(understanding.to_dict(), sort_keys=True)
    if existing:
        existing.profile_json = payload
        existing.method = understanding.method
        existing.updated_at = utc_now_iso()
    else:
        session.add(
            SiteProfile(
                id=new_id(),
                job_id=job_id,
                profile_json=payload,
                method=understanding.method,
                provenance=provenance,
                created_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
        )
    session.flush()
    return understanding
