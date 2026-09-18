"""Entity Clarity analyzer (METRICS §5)."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from aeo_mvp.analyzers.base import (
    EvidenceAtom,
    domain_label,
    eligible_pages,
    homepage,
    parse_html,
    persist_evidence,
)
from aeo_mvp.db.models import Page
from sqlalchemy.orm import Session


@dataclass
class EntityResult:
    score: float
    checks: dict[str, float]
    brand_tokens: list[str]
    breakdown: dict[str, Any]
    evidence_ids: list[str]


def _edit_distance(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    if a == b:
        return 0
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, dp[0] = dp[0], i
        for j, cb in enumerate(b, 1):
            cur = dp[j]
            if ca == cb:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = cur
    return dp[-1]


def _extract_jsonld(html: str) -> list[dict]:
    tree = parse_html(html)
    nodes: list[dict] = []
    for script in tree.css('script[type="application/ld+json"]'):
        raw = script.text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            nodes.extend([x for x in data if isinstance(x, dict)])
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                nodes.extend([x for x in data["@graph"] if isinstance(x, dict)])
            else:
                nodes.append(data)
    return nodes


def _type_list(node: dict) -> list[str]:
    t = node.get("@type")
    if isinstance(t, list):
        return [str(x) for x in t]
    if t:
        return [str(t)]
    return []


def analyze_entities(
    session: Session,
    job_id: str,
    pages: list[Page],
    base_url: str,
    *,
    provenance: str = "derived_metric",
) -> EntityResult:
    elig = eligible_pages(pages)
    home = homepage(pages)
    label = domain_label(base_url)
    candidates: list[str] = []
    if label:
        candidates.append(label)
    for p in elig:
        if p.title:
            # first ProperCase-ish token sequence from title
            m = re.match(r"^([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})", p.title.strip())
            if m:
                candidates.append(m.group(1).split("—")[0].split("-")[0].strip())
            else:
                candidates.append(p.title.split()[0])
        if p.html:
            tree = parse_html(p.html)
            og = tree.css_first('meta[property="og:site_name"]')
            if og and og.attributes.get("content"):
                candidates.append(og.attributes["content"].strip())

    # Normalize brand candidates
    cleaned = []
    for c in candidates:
        c2 = re.sub(r"\s+", " ", c).strip()
        if c2:
            cleaned.append(c2)
    counts = Counter(x.lower() for x in cleaned)
    brand = None
    if counts:
        top = counts.most_common(1)[0][0]
        # Prefer original casing from cleaned
        for c in cleaned:
            if c.lower() == top:
                brand = c
                break
    brand = brand or label or "site"

    titles = [p.title for p in elig if p.title]
    if titles:
        hit = sum(1 for t in titles if brand.lower() in t.lower())
        ratio = hit / len(titles)
        if ratio >= 0.7:
            e1 = 1.0
        elif ratio >= 0.4:
            e1 = 0.5
        else:
            e1 = 0.0
    else:
        ratio = 0.0
        e1 = 0.0

    # E2 Organization signal
    e2 = 0.0
    org_found = False
    footer_org = False
    focus_pages = []
    for p in elig:
        path = urlparse(p.url).path.lower()
        if p.depth == 0 or any(x in path for x in ("about", "company", "team")):
            focus_pages.append(p)
    if not focus_pages and home:
        focus_pages = [home]
    for p in focus_pages:
        if not p.html:
            continue
        for node in _extract_jsonld(p.html):
            types = _type_list(node)
            if any(t in ("Organization", "LocalBusiness") for t in types):
                org_found = True
        tree = parse_html(p.html)
        footer = tree.css_first("footer")
        if footer:
            ft = (footer.text() or "").lower()
            if brand.lower() in ft or "©" in (footer.text() or "") or "&copy;" in p.html.lower():
                footer_org = True
    if org_found:
        e2 = 1.0
    elif footer_org:
        e2 = 0.5
    else:
        e2 = 0.0

    # E3 contact / sameAs
    e3 = 0.0
    for p in focus_pages:
        if not p.html:
            continue
        if "mailto:" in p.html or re.search(r'href=["\'][^"\']*contact', p.html, re.I):
            e3 = 1.0
            break
        for node in _extract_jsonld(p.html):
            if node.get("sameAs"):
                e3 = 1.0
                break
        if e3:
            break

    # E4 ambiguity
    unique_brands = []
    for c in cleaned:
        if not any(_edit_distance(c, u) <= 2 for u in unique_brands):
            unique_brands.append(c)
    # Only consider title-derived divergence among page titles' first tokens
    title_brands = []
    for t in titles:
        tok = t.split("—")[0].split("-")[0].strip().split()[0]
        if not any(_edit_distance(tok, u) <= 2 for u in title_brands):
            title_brands.append(tok)
    divergent = len(title_brands)
    if divergent >= 3:
        e4 = 0.0
    elif divergent == 2:
        e4 = 0.5
    else:
        e4 = 1.0

    weights = {"E1": 0.35, "E2": 0.30, "E3": 0.20, "E4": 0.15}
    checks = {"E1": e1, "E2": e2, "E3": e3, "E4": e4}
    score = max(0.0, min(100.0, 100.0 * sum(weights[k] * checks[k] for k in weights)))

    brand_tokens = []
    for tok in [brand, label, urlparse(base_url).netloc.lower().removeprefix("www.")]:
        if tok and tok.lower() not in {b.lower() for b in brand_tokens}:
            brand_tokens.append(tok)

    atoms = [
        EvidenceAtom(
            analyzer="entities",
            code="ENTITY_BRAND_CONSISTENCY",
            severity="medium" if e1 < 1 else "info",
            message=f"Brand '{brand}' in {ratio:.0%} of titles",
            data={"pass": e1, "brand": brand, "ratio": ratio},
            page_id=home.id if home else None,
            provenance=provenance,
        ),
        EvidenceAtom(
            analyzer="entities",
            code="ENTITY_ORG_SIGNAL",
            severity="high" if e2 == 0 else ("low" if e2 < 1 else "info"),
            message="Organization JSON-LD found" if org_found else (
                "Footer org/copyright hint only" if footer_org else "No Organization signal"
            ),
            data={"pass": e2, "jsonld_org": org_found, "footer_org": footer_org},
            page_id=home.id if home else None,
            provenance=provenance,
        ),
        EvidenceAtom(
            analyzer="entities",
            code="ENTITY_CONTACT_SAMEAS",
            severity="low" if e3 == 0 else "info",
            message="Contact/sameAs present" if e3 else "No contact or sameAs found",
            data={"pass": e3},
            page_id=home.id if home else None,
            provenance=provenance,
        ),
        EvidenceAtom(
            analyzer="entities",
            code="ENTITY_AMBIGUITY",
            severity="medium" if e4 < 1 else "info",
            message=f"Divergent title brand strings={divergent}",
            data={"pass": e4, "divergent": divergent, "title_brands": title_brands},
            provenance=provenance,
        ),
    ]
    rows = persist_evidence(session, job_id, atoms)
    breakdown = {
        "checks": {k: {"pass": checks[k], "weight": weights[k]} for k in weights},
        "brand": brand,
        "brand_tokens": brand_tokens,
    }
    return EntityResult(
        score=score,
        checks=checks,
        brand_tokens=brand_tokens,
        breakdown=breakdown,
        evidence_ids=[r.id for r in rows],
    )
