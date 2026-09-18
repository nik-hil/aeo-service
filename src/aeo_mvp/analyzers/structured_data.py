"""Structured Data analyzer (METRICS §6)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aeo_mvp.analyzers.base import (
    EvidenceAtom,
    eligible_pages,
    homepage,
    parse_html,
    persist_evidence,
)
from aeo_mvp.db.models import Page
from sqlalchemy.orm import Session

FIT_TYPES = {
    "Organization",
    "WebSite",
    "WebPage",
    "Article",
    "FAQPage",
    "Product",
    "HowTo",
    "BreadcrumbList",
    "LocalBusiness",
    "AboutPage",
}


@dataclass
class StructuredDataResult:
    score: float
    checks: dict[str, float]
    has_organization: bool
    parse_errors: int
    breakdown: dict[str, Any]
    evidence_ids: list[str]


def _parse_blocks(html: str) -> tuple[list[dict], list[str]]:
    tree = parse_html(html)
    nodes: list[dict] = []
    errors: list[str] = []
    for script in tree.css('script[type="application/ld+json"]'):
        raw = (script.text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        if isinstance(data, list):
            nodes.extend([x for x in data if isinstance(x, dict)])
        elif isinstance(data, dict):
            if isinstance(data.get("@graph"), list):
                nodes.extend([x for x in data["@graph"] if isinstance(x, dict)])
            else:
                nodes.append(data)
    return nodes, errors


def _types(node: dict) -> list[str]:
    t = node.get("@type")
    if isinstance(t, list):
        return [str(x) for x in t]
    if t:
        return [str(t)]
    return []


def analyze_structured_data(
    session: Session,
    job_id: str,
    pages: list[Page],
    *,
    provenance: str = "derived_metric",
) -> StructuredDataResult:
    home = homepage(pages)
    elig = eligible_pages(pages)
    atoms: list[EvidenceAtom] = []

    home_nodes: list[dict] = []
    home_errors: list[str] = []
    if home and home.html:
        home_nodes, home_errors = _parse_blocks(home.html)

    s1 = 1.0 if home_nodes else 0.0
    atoms.append(
        EvidenceAtom(
            analyzer="structured_data",
            code="SD_HOME_JSONLD",
            severity="high" if s1 == 0 else "info",
            message="Homepage has parseable JSON-LD" if s1 else "Homepage missing parseable JSON-LD",
            data={"pass": s1, "node_count": len(home_nodes)},
            page_id=home.id if home else None,
            provenance=provenance,
        )
    )
    for err in home_errors:
        atoms.append(
            EvidenceAtom(
                analyzer="structured_data",
                code="SD_PARSE_ERROR",
                severity="medium",
                message=f"JSON-LD parse error on homepage: {err}",
                data={"error": err},
                page_id=home.id if home else None,
                provenance=provenance,
            )
        )

    pages_with = 0
    all_nodes: list[dict] = []
    parse_errors = len(home_errors)
    for p in elig:
        if not p.html:
            continue
        nodes, errors = _parse_blocks(p.html)
        parse_errors += len(errors)
        for err in errors:
            if p is home:
                continue
            atoms.append(
                EvidenceAtom(
                    analyzer="structured_data",
                    code="SD_PARSE_ERROR",
                    severity="medium",
                    message=f"JSON-LD parse error: {err}",
                    data={"error": err, "url": p.url},
                    page_id=p.id,
                    provenance=provenance,
                )
            )
        if nodes:
            pages_with += 1
            all_nodes.extend(nodes)

    share = pages_with / len(elig) if elig else 0.0
    if share >= 0.4:
        s2 = 1.0
    elif share >= 0.2:
        s2 = 0.5
    else:
        s2 = 0.0
    atoms.append(
        EvidenceAtom(
            analyzer="structured_data",
            code="SD_COVERAGE",
            severity="medium" if s2 < 1 else "info",
            message=f"JSON-LD coverage share={share:.2f}",
            data={"pass": s2, "share": share},
            provenance=provenance,
        )
    )

    type_set: set[str] = set()
    for n in all_nodes:
        type_set.update(_types(n))
    s3 = 1.0 if type_set & FIT_TYPES else 0.0
    atoms.append(
        EvidenceAtom(
            analyzer="structured_data",
            code="SD_TYPE_FIT",
            severity="medium" if s3 == 0 else "info",
            message=f"Type fit types={sorted(type_set & FIT_TYPES)}",
            data={"pass": s3, "types": sorted(type_set)},
            provenance=provenance,
        )
    )

    if all_nodes:
        with_type = sum(1 for n in all_nodes if _types(n))
        frac = with_type / len(all_nodes)
        if frac >= 0.9:
            s4 = 1.0
        elif frac >= 0.5:
            s4 = 0.5
        else:
            s4 = 0.0
    else:
        frac = 0.0
        s4 = 0.0
    atoms.append(
        EvidenceAtom(
            analyzer="structured_data",
            code="SD_HYGIENE",
            severity="low" if s4 < 1 else "info",
            message=f"@type hygiene fraction={frac:.2f}",
            data={"pass": s4, "fraction": frac},
            provenance=provenance,
        )
    )

    has_org = False
    s5 = 0.0
    for n in all_nodes:
        types = _types(n)
        if any(t in ("Organization", "WebSite", "LocalBusiness") for t in types):
            if any(t in ("Organization", "LocalBusiness") for t in types):
                has_org = True
            if n.get("@id") or n.get("sameAs"):
                s5 = 1.0
    atoms.append(
        EvidenceAtom(
            analyzer="structured_data",
            code="SD_ID_SAMEAS",
            severity="low" if s5 == 0 else "info",
            message="@id/sameAs on Organization/WebSite" if s5 else "No @id/sameAs on org/website nodes",
            data={"pass": s5, "has_organization": has_org},
            provenance=provenance,
        )
    )

    weights = {"S1": 0.30, "S2": 0.20, "S3": 0.25, "S4": 0.15, "S5": 0.10}
    checks = {"S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5}
    score = max(0.0, min(100.0, 100.0 * sum(weights[k] * checks[k] for k in weights)))
    rows = persist_evidence(session, job_id, atoms)
    breakdown = {
        "checks": {k: {"pass": checks[k], "weight": weights[k]} for k in weights},
        "coverage_share": share,
        "types": sorted(type_set),
        "parse_errors": parse_errors,
        "has_organization": has_org,
    }
    return StructuredDataResult(
        score=score,
        checks=checks,
        has_organization=has_org,
        parse_errors=parse_errors,
        breakdown=breakdown,
        evidence_ids=[r.id for r in rows],
    )
