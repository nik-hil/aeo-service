"""Shared analyzer helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from selectolax.parser import HTMLParser
from sqlalchemy.orm import Session

from aeo_mvp.db.models import AnalysisEvidence, Page, new_id, utc_now_iso


@dataclass
class EvidenceAtom:
    analyzer: str
    code: str
    severity: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    page_id: str | None = None
    provenance: str = "derived_metric"


@dataclass
class CheckResult:
    check_id: str
    pass_value: float
    weight: float
    evidence: list[EvidenceAtom] = field(default_factory=list)


def persist_evidence(session: Session, job_id: str, atoms: list[EvidenceAtom]) -> list[AnalysisEvidence]:
    rows: list[AnalysisEvidence] = []
    for atom in atoms:
        row = AnalysisEvidence(
            id=new_id(),
            job_id=job_id,
            page_id=atom.page_id,
            analyzer=atom.analyzer,
            code=atom.code,
            severity=atom.severity,
            message=atom.message,
            data_json=json.dumps(atom.data, sort_keys=True),
            provenance=atom.provenance,
            created_at=utc_now_iso(),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def eligible_pages(pages: list[Page]) -> list[Page]:
    return [
        p
        for p in pages
        if p.html
        and p.status_code is not None
        and 200 <= p.status_code < 300
        and not p.fetch_error
    ]


def homepage(pages: list[Page]) -> Page | None:
    depth0 = [p for p in pages if p.depth == 0]
    if depth0:
        return sorted(depth0, key=lambda p: p.url)[0]
    return pages[0] if pages else None


def parse_html(html: str) -> HTMLParser:
    return HTMLParser(html)


def visible_text(tree: HTMLParser) -> str:
    for tag in tree.css("script, style, noscript"):
        tag.decompose()
    text = tree.body.text(separator=" ") if tree.body else tree.text(separator=" ")
    return re.sub(r"\s+", " ", text or "").strip()


def word_count(text: str) -> int:
    return len([w for w in text.split() if w])


def registrable_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host


def domain_label(url: str) -> str:
    host = registrable_domain(url)
    return host.split(".")[0] if host else ""
