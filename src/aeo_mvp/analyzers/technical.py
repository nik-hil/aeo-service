"""Technical Accessibility analyzer (METRICS §3)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from aeo_mvp.analyzers.base import (
    CheckResult,
    EvidenceAtom,
    eligible_pages,
    homepage,
    parse_html,
    persist_evidence,
    visible_text,
)
from aeo_mvp.db.models import Page
from sqlalchemy.orm import Session


@dataclass
class TechnicalResult:
    score: float
    checks: dict[str, float]
    weights: dict[str, float]
    evidence_ids: list[str]
    breakdown: dict[str, Any]


def _meta_description(html: str) -> str | None:
    tree = parse_html(html)
    for meta in tree.css("meta"):
        name = (meta.attributes.get("name") or "").lower()
        if name == "description":
            return meta.attributes.get("content")
    return None


def analyze_technical(
    session: Session,
    job_id: str,
    pages: list[Page],
    *,
    robots_allowed_root: float,
    provenance: str = "derived_metric",
) -> TechnicalResult:
    home = homepage(pages)
    atoms: list[EvidenceAtom] = []
    checks: dict[str, float] = {}
    weights = {
        "T1": 0.20,
        "T2": 0.15,
        "T3": 0.15,
        "T4": 0.10,
        "T5": 0.10,
        "T6": 0.10,
        "T7": 0.10,
        "T8": 0.10,
    }

    # T1 homepage status
    if home and home.status_code in (200, 203):
        checks["T1"] = 1.0
        sev = "info"
        msg = f"Homepage HTTP status {home.status_code}"
    else:
        checks["T1"] = 0.0
        sev = "high"
        msg = f"Homepage HTTP status not 200/203 (got {home.status_code if home else None})"
    atoms.append(
        EvidenceAtom(
            analyzer="technical",
            code="TECH_HOME_STATUS",
            severity=sev,
            message=msg,
            data={"pass": checks["T1"], "status_code": home.status_code if home else None},
            page_id=home.id if home else None,
            provenance=provenance,
        )
    )

    # T2 robots
    checks["T2"] = float(robots_allowed_root)
    atoms.append(
        EvidenceAtom(
            analyzer="technical",
            code="TECH_ROBOTS",
            severity="high" if checks["T2"] == 0 else ("low" if checks["T2"] < 1 else "info"),
            message=f"robots.txt allow score for AEOBot root path: {checks['T2']}",
            data={"pass": checks["T2"]},
            page_id=None,
            provenance=provenance,
        )
    )

    # T3 noindex
    robots_meta = (home.robots_meta or "").lower() if home else ""
    has_noindex = "noindex" in robots_meta
    checks["T3"] = 0.0 if has_noindex else 1.0
    atoms.append(
        EvidenceAtom(
            analyzer="technical",
            code="TECH_NOINDEX",
            severity="high" if has_noindex else "info",
            message="Homepage has noindex" if has_noindex else "Homepage is indexable",
            data={"pass": checks["T3"], "robots_meta": home.robots_meta if home else None},
            page_id=home.id if home else None,
            provenance=provenance,
        )
    )

    # T4 canonical same-host
    canonical_ok = 0.0
    if home and home.canonical_url:
        home_host = urlparse(home.final_url or home.url).netloc.lower().removeprefix("www.")
        can_host = urlparse(home.canonical_url).netloc.lower().removeprefix("www.")
        if not can_host or can_host == home_host:
            canonical_ok = 1.0
    checks["T4"] = canonical_ok
    atoms.append(
        EvidenceAtom(
            analyzer="technical",
            code="TECH_CANONICAL",
            severity="medium" if canonical_ok == 0 else "info",
            message="Canonical present and same-host" if canonical_ok else "Canonical missing or off-host",
            data={"pass": checks["T4"], "canonical_url": home.canonical_url if home else None},
            page_id=home.id if home else None,
            provenance=provenance,
        )
    )

    # T5 title
    title = (home.title or "").strip() if home else ""
    if not title:
        checks["T5"] = 0.0
    elif 15 <= len(title) <= 70:
        checks["T5"] = 1.0
    else:
        checks["T5"] = 0.5
    atoms.append(
        EvidenceAtom(
            analyzer="technical",
            code="TECH_TITLE",
            severity="low" if checks["T5"] < 1 else "info",
            message=f"Title length {len(title)}",
            data={"pass": checks["T5"], "title": title, "length": len(title)},
            page_id=home.id if home else None,
            provenance=provenance,
        )
    )

    # T6 meta description
    desc = _meta_description(home.html) if home and home.html else None
    if not desc:
        checks["T6"] = 0.0
    elif 50 <= len(desc) <= 160:
        checks["T6"] = 1.0
    else:
        checks["T6"] = 0.5
    atoms.append(
        EvidenceAtom(
            analyzer="technical",
            code="TECH_META_DESC",
            severity="low" if checks["T6"] < 1 else "info",
            message=f"Meta description pass={checks['T6']}",
            data={"pass": checks["T6"], "length": len(desc) if desc else 0},
            page_id=home.id if home else None,
            provenance=provenance,
        )
    )

    # T7 JS-risk
    js_pass = 0.0
    if home and home.html:
        html = home.html
        scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.I | re.S)
        inline_bytes = sum(len(s.encode("utf-8")) for s in scripts)
        html_bytes = max(len(html.encode("utf-8")), 1)
        ratio = inline_bytes / html_bytes
        body_len = len(visible_text(parse_html(html)))
        if ratio <= 0.35 and body_len >= 200:
            js_pass = 1.0
        elif body_len >= 200:
            js_pass = 0.5
        else:
            js_pass = 0.0
        atoms.append(
            EvidenceAtom(
                analyzer="technical",
                code="TECH_JS_RISK",
                severity="medium" if js_pass == 0 else ("low" if js_pass < 1 else "info"),
                message=f"JS-risk ratio={ratio:.3f}, body_text_len={body_len}",
                data={"pass": js_pass, "script_ratio": ratio, "body_text_len": body_len},
                page_id=home.id,
                provenance=provenance,
            )
        )
    else:
        atoms.append(
            EvidenceAtom(
                analyzer="technical",
                code="TECH_JS_RISK",
                severity="high",
                message="No homepage HTML for JS-risk check",
                data={"pass": 0.0},
                page_id=home.id if home else None,
                provenance=provenance,
            )
        )
    checks["T7"] = js_pass

    # T8 2xx share
    if pages:
        ok = sum(1 for p in pages if p.status_code and 200 <= p.status_code < 300)
        share = ok / len(pages)
        if share >= 0.8:
            checks["T8"] = 1.0
        elif share >= 0.5:
            checks["T8"] = 0.5
        else:
            checks["T8"] = 0.0
    else:
        share = 0.0
        checks["T8"] = 0.0
    atoms.append(
        EvidenceAtom(
            analyzer="technical",
            code="TECH_PAGE_SUCCESS_RATE",
            severity="medium" if checks["T8"] < 1 else "info",
            message=f"2xx page share={share:.2f}",
            data={"pass": checks["T8"], "share": share, "page_count": len(pages)},
            page_id=None,
            provenance=provenance,
        )
    )

    rows = persist_evidence(session, job_id, atoms)
    score = 100.0 * sum(weights[k] * checks[k] for k in weights)
    score = max(0.0, min(100.0, score))
    breakdown = {
        "checks": {k: {"pass": checks[k], "weight": weights[k]} for k in weights},
        "formula": "T = 100 * sum(v_i * p_i)",
    }
    return TechnicalResult(
        score=score,
        checks=checks,
        weights=weights,
        evidence_ids=[r.id for r in rows],
        breakdown=breakdown,
    )
