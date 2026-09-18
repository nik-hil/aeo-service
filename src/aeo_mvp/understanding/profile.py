"""Structured SiteProfile schema (Phase 3 / ADR-024).

Every assertive field is wrapped with confidence, provenance, and evidence.
Heuristic confidence is capped at 0.40; low-confidence values stay low or are omitted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FieldProvenance = Literal[
    "observed",
    "derived_metric",
    "synthetic_demo",
    "estimate",
    "heuristic",
    "llm_assist",
]

EvidenceClass = Literal[
    "title_h1",
    "tags_series",
    "about_bio",
    "jsonld",
    "og_meta",
    "article_body",
    "chrome",
    "url_path",
    "metadata",
]

HEURISTIC_CONFIDENCE_CAP = 0.40
STRONG_DETERMINISTIC_FLOOR = 0.70
PROFILE_METHOD = "deterministic_html_v1+site-profile-v1"
QUERY_DISCOVERY_METHOD = "query-discovery-v1"


@dataclass
class EvidenceRef:
    evidence_id: str
    url: str | None = None
    snippet: str | None = None
    locator: str | None = None
    page_id: str | None = None
    evidence_class: EvidenceClass | None = None
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SiteProfileField:
    """Wrapped field — never silently promote weak heuristics to facts."""

    value: Any = None
    confidence: float = 0.0
    provenance: FieldProvenance = "heuristic"
    evidence: list[EvidenceRef] = field(default_factory=list)
    method: str = PROFILE_METHOD
    omitted: bool = False
    omit_reason: str | None = None
    model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None
    justification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "value": self.value,
            "confidence": round(self.confidence, 3),
            "provenance": self.provenance,
            "evidence": [e.to_dict() for e in self.evidence],
            "method": self.method,
            "omitted": self.omitted,
        }
        if self.omit_reason:
            d["omit_reason"] = self.omit_reason
        if self.model:
            d["model"] = self.model
        if self.provider:
            d["provider"] = self.provider
        if self.prompt_version:
            d["prompt_version"] = self.prompt_version
        if self.justification:
            d["justification"] = self.justification
        return d

    @classmethod
    def omitted_field(
        cls,
        *,
        reason: str,
        provenance: FieldProvenance = "heuristic",
        method: str = PROFILE_METHOD,
    ) -> SiteProfileField:
        return cls(
            value=None,
            confidence=0.0,
            provenance=provenance,
            omitted=True,
            omit_reason=reason,
            method=method,
        )

    @classmethod
    def from_heuristic(
        cls,
        value: Any,
        *,
        confidence: float,
        evidence: list[EvidenceRef] | None = None,
        provenance: FieldProvenance = "heuristic",
        method: str = PROFILE_METHOD,
    ) -> SiteProfileField:
        conf = min(float(confidence), HEURISTIC_CONFIDENCE_CAP)
        if value is None or value == [] or value == "":
            return cls.omitted_field(reason="empty_value", provenance=provenance, method=method)
        return cls(
            value=value,
            confidence=conf,
            provenance=provenance,
            evidence=list(evidence or []),
            method=method,
            omitted=False,
        )


@dataclass
class EntityMention:
    name: str
    type: str = "concept"  # person | org | product | concept | technology
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _omit(reason: str = "unset") -> SiteProfileField:
    return SiteProfileField.omitted_field(reason=reason)


@dataclass
class StructuredSiteProfile:
    """Evidence-first site profile. Assertive industry is often omitted."""

    org_name: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    hostname: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    description: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    primary_topics: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    secondary_topics: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    entities: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    products: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    authors: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    audience: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    content_types: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    industry_category: SiteProfileField = field(
        default_factory=lambda: _omit("industry_defaults_to_omit")
    )
    site_genre: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    commercial_signals: SiteProfileField = field(default_factory=lambda: _omit("unset"))
    important_pages: list[dict[str, Any]] = field(default_factory=list)
    method: str = PROFILE_METHOD
    llm_used: bool = False
    warnings: list[str] = field(default_factory=list)
    evidence_hash: str | None = None
    profile_version: str = "site-profile-v1"

    def to_dict(self) -> dict[str, Any]:
        fields = (
            "org_name",
            "hostname",
            "description",
            "primary_topics",
            "secondary_topics",
            "entities",
            "products",
            "authors",
            "audience",
            "content_types",
            "industry_category",
            "site_genre",
            "commercial_signals",
        )
        out: dict[str, Any] = {
            "profile_version": self.profile_version,
            "method": self.method,
            "llm_used": self.llm_used,
            "warnings": list(self.warnings),
            "evidence_hash": self.evidence_hash,
            "important_pages": self.important_pages,
        }
        for name in fields:
            fld: SiteProfileField = getattr(self, name)
            # Ensure omitted defaults constructed correctly
            if not isinstance(fld, SiteProfileField):
                continue
            out[name] = fld.to_dict()
        return out

    def assertive_industry(self) -> str | None:
        """Return industry only when not omitted and confidence justifies assertion."""
        f = self.industry_category
        if f.omitted or f.value is None:
            return None
        if f.confidence < 0.25:
            return None
        return str(f.value)

    def genre_value(self) -> str | None:
        f = self.site_genre
        if f.omitted or f.value is None:
            return None
        return str(f.value)

    def topic_list(self) -> list[str]:
        primary = self.primary_topics.value if not self.primary_topics.omitted else []
        secondary = self.secondary_topics.value if not self.secondary_topics.omitted else []
        out: list[str] = []
        for item in list(primary or []) + list(secondary or []):
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out


def merge_llm_field(
    deterministic: SiteProfileField,
    llm: SiteProfileField,
    *,
    justification: str,
) -> SiteProfileField:
    """LLM assist cannot overwrite conf≥0.70 deterministic without justification."""
    if (
        not deterministic.omitted
        and deterministic.confidence >= STRONG_DETERMINISTIC_FLOOR
        and deterministic.provenance != "llm_assist"
    ):
        if not justification:
            raise ValueError("justification required to overwrite strong deterministic field")
        # Keep deterministic; attach llm as rejected assist note
        kept = SiteProfileField(
            value=deterministic.value,
            confidence=deterministic.confidence,
            provenance=deterministic.provenance,
            evidence=list(deterministic.evidence),
            method=deterministic.method,
            justification=f"llm_assist_rejected: {justification}",
        )
        return kept
    if llm.omitted:
        return deterministic
    return SiteProfileField(
        value=llm.value,
        confidence=min(llm.confidence, HEURISTIC_CONFIDENCE_CAP),
        provenance="llm_assist",
        evidence=list(llm.evidence) or list(deterministic.evidence),
        method=llm.method or "llm_assist_v1",
        model=llm.model,
        provider=llm.provider,
        prompt_version=llm.prompt_version,
        justification=justification,
    )
