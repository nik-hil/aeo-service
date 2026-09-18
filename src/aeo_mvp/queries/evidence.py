"""Evidence provenance for query-quality / QSQ-EVD (Phase 4.1 / 4.1.1).

Provenance values:
- ``observed`` — extracted from crawled page signals (counts for strongest QSQ-EVD)
- ``derived`` — inferred / projected (does **not** count toward strongest QSQ-EVD)
- ``compatibility`` — legacy SiteUnderstanding synthetic fillers (does **not** count)

Only ``observed`` evidence classes count for the strongest QSQ-EVD gate (≥2 classes).

Trust boundary (Phase 4.1.1): missing/unknown provenance → ``compatibility``.
Never promote missing/unknown to ``observed``. Field/origin provenance on
SiteProfile is not EvidenceRecord provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EvidenceProvenance = Literal["observed", "derived", "compatibility"]

VALID_PROVENANCE: frozenset[str] = frozenset(
    {"observed", "derived", "compatibility"}
)


def normalize_provenance(raw: Any) -> EvidenceProvenance:
    """Canonical trust-boundary helper.

    Explicit ``observed`` | ``derived`` | ``compatibility`` are preserved.
    Missing, empty, and any other value map to ``compatibility``.
    Never invents ``observed``.
    """
    if raw in VALID_PROVENANCE:
        return raw  # type: ignore[return-value]
    return "compatibility"


@dataclass
class EvidenceRecord:
    """Normalized evidence attached to a candidate query."""

    evidence_class: str
    provenance: EvidenceProvenance = "compatibility"
    snippet: str | None = None
    url: str | None = None
    locator: str | None = None
    evidence_id: str | None = None
    page_id: str | None = None
    weight: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "evidence_class": self.evidence_class,
            "provenance": self.provenance,
        }
        if self.snippet is not None:
            d["snippet"] = self.snippet
        if self.url is not None:
            d["url"] = self.url
        if self.locator is not None:
            d["locator"] = self.locator
        if self.evidence_id is not None:
            d["evidence_id"] = self.evidence_id
        if self.page_id is not None:
            d["page_id"] = self.page_id
        if self.weight != 1.0:
            d["weight"] = self.weight
        if self.extra:
            d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> EvidenceRecord | None:
        if not raw or not isinstance(raw, dict):
            return None
        cls_name = raw.get("evidence_class") or raw.get("class") or "metadata"
        # Missing/unknown → compatibility (never promote to observed)
        provenance = normalize_provenance(raw.get("provenance"))
        known = {
            "evidence_class",
            "class",
            "provenance",
            "snippet",
            "url",
            "locator",
            "evidence_id",
            "page_id",
            "weight",
        }
        extra = {k: v for k, v in raw.items() if k not in known}
        return cls(
            evidence_class=str(cls_name),
            provenance=provenance,
            snippet=raw.get("snippet"),
            url=raw.get("url"),
            locator=raw.get("locator"),
            evidence_id=raw.get("evidence_id"),
            page_id=raw.get("page_id"),
            weight=float(raw.get("weight", 1.0) or 1.0),
            extra=extra,
        )


def normalize_evidence_list(
    items: list[dict[str, Any]] | list[EvidenceRecord] | None,
    *,
    default_provenance: EvidenceProvenance = "compatibility",
) -> list[EvidenceRecord]:
    out: list[EvidenceRecord] = []
    for item in items or []:
        if isinstance(item, EvidenceRecord):
            # Re-normalize in case a caller constructed an invalid value
            item.provenance = normalize_provenance(item.provenance)
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        rec = EvidenceRecord.from_dict(item)
        if rec is None:
            continue
        if "provenance" not in item:
            rec.provenance = normalize_provenance(default_provenance)
        out.append(rec)
    return out


def stamp_evidence_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Copy an evidence dict and normalize provenance at the trust boundary."""
    item = dict(raw)
    item["provenance"] = normalize_provenance(item.get("provenance"))
    if "evidence_class" not in item and item.get("class"):
        item["evidence_class"] = item["class"]
    return item


def observed_evidence_classes(
    items: list[dict[str, Any]] | list[EvidenceRecord] | None,
    *,
    exclude_chrome: bool = True,
) -> set[str]:
    """Distinct evidence classes with provenance=observed (strongest QSQ-EVD)."""
    classes: set[str] = set()
    for rec in normalize_evidence_list(items):
        if exclude_chrome and rec.evidence_class == "chrome":
            continue
        if rec.provenance == "observed":
            classes.add(rec.evidence_class)
    return classes


def any_evidence_classes(
    items: list[dict[str, Any]] | list[EvidenceRecord] | None,
    *,
    exclude_chrome: bool = True,
) -> set[str]:
    """All non-chrome classes regardless of provenance (diagnostics only)."""
    classes: set[str] = set()
    for rec in normalize_evidence_list(items):
        if exclude_chrome and rec.evidence_class == "chrome":
            continue
        classes.add(rec.evidence_class)
    return classes


def evidence_records_to_dicts(records: list[EvidenceRecord]) -> list[dict[str, Any]]:
    return [r.to_dict() for r in records]
