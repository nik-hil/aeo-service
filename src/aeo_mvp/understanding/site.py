"""Deterministic site understanding from crawled HTML (P1-B).

LLM enrichment is optional and off by default (requires OPENAI_API_KEY + flag).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from aeo_mvp.analyzers.base import (
    EvidenceAtom,
    domain_label,
    eligible_pages,
    homepage,
    parse_html,
    persist_evidence,
    visible_text,
)
from aeo_mvp.db.models import Page, SiteProfile, new_id, utc_now_iso
from sqlalchemy.orm import Session

COMMERCIAL_PATH_HINTS = (
    "pricing",
    "price",
    "plans",
    "buy",
    "shop",
    "cart",
    "checkout",
    "demo",
    "trial",
    "signup",
    "sign-up",
    "contact",
    "sales",
)
IMPORTANT_PATH_HINTS = (
    "about",
    "company",
    "team",
    "product",
    "products",
    "services",
    "solutions",
    "pricing",
    "faq",
    "docs",
    "documentation",
    "blog",
    "contact",
)
AUDIENCE_PATTERNS = [
    (re.compile(r"\bfor\s+(teams|developers|marketers|founders|enterprises|agencies|startups)\b", re.I), "segment"),
    (re.compile(r"\b(b2b|b2c|smb|enterprise|small business)\b", re.I), "market"),
]
INDUSTRY_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"project management|task board|kanban|roadmap", re.I), "project_management"),
    (re.compile(r"answer engine|aeo|seo|documentation", re.I), "software_documentation"),
    (re.compile(r"ecommerce|online store|shopify", re.I), "ecommerce"),
    (re.compile(r"saas|software as a service|cloud platform", re.I), "saas"),
    (re.compile(r"healthcare|clinic|patient", re.I), "healthcare"),
    (re.compile(r"fintech|banking|payments", re.I), "fintech"),
]


@dataclass
class SiteUnderstanding:
    organization_brand: str | None = None
    products_services: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    audience_hints: list[str] = field(default_factory=list)
    industry_category_guess: str | None = None
    commercial_intents: list[str] = field(default_factory=list)
    important_pages: list[dict[str, Any]] = field(default_factory=list)
    provenance: str = "derived_metric"
    method: str = "deterministic_html_v1"
    evidence_refs: list[str] = field(default_factory=list)
    llm_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _brand_from_pages(pages: list[Page], base_url: str) -> str | None:
    candidates: list[str] = []
    label = domain_label(base_url)
    if label:
        candidates.append(label)
    for p in eligible_pages(pages):
        if p.title:
            m = re.match(
                r"^([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})",
                p.title.strip(),
            )
            if m:
                candidates.append(m.group(1).split("—")[0].split("-")[0].strip())
        if p.html:
            tree = parse_html(p.html)
            og = tree.css_first('meta[property="og:site_name"]')
            if og and og.attributes.get("content"):
                candidates.append(og.attributes["content"].strip())
            for node in _extract_jsonld(p.html):
                types = [t.lower() for t in _type_list(node)]
                if any(t in ("organization", "localbusiness", "corporation") for t in types):
                    name = node.get("name")
                    if isinstance(name, str) and name.strip():
                        candidates.append(name.strip())
    if not candidates:
        return None
    counts = Counter(c.lower() for c in candidates)
    top = counts.most_common(1)[0][0]
    for c in candidates:
        if c.lower() == top:
            return c
    return candidates[0]


def _headings(html: str) -> list[str]:
    tree = parse_html(html)
    out: list[str] = []
    for sel in ("h1", "h2", "h3"):
        for node in tree.css(sel):
            t = (node.text() or "").strip()
            if t:
                out.append(re.sub(r"\s+", " ", t))
    return out


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
    """Infer site profile deterministically. LLM path is stubbed/off by default."""
    elig = eligible_pages(pages)
    brand = _brand_from_pages(pages, base_url)
    products: list[str] = []
    topics: list[str] = []
    audience: list[str] = []
    commercial: list[str] = []
    important: list[dict[str, Any]] = []
    industry_votes: Counter[str] = Counter()

    for p in elig:
        path = urlparse(p.url).path.lower() or "/"
        depth = p.depth
        reason_bits: list[str] = []
        if depth == 0:
            reason_bits.append("homepage")
        for hint in IMPORTANT_PATH_HINTS:
            if hint in path.strip("/").split("/") or f"/{hint}" in path:
                reason_bits.append(f"path:{hint}")
                break
        for hint in COMMERCIAL_PATH_HINTS:
            if hint in path:
                commercial.append(hint)
                reason_bits.append(f"commercial:{hint}")
                break
        if reason_bits:
            important.append(
                {
                    "url": p.url,
                    "title": p.title,
                    "depth": depth,
                    "reasons": sorted(set(reason_bits)),
                }
            )

        if not p.html:
            continue
        heads = _headings(p.html)
        topics.extend(heads[:6])
        text = visible_text(parse_html(p.html))
        for pat, label in AUDIENCE_PATTERNS:
            m = pat.search(text)
            if m:
                audience.append(m.group(0))
        for pat, industry in INDUSTRY_KEYWORDS:
            if pat.search(text) or (p.title and pat.search(p.title)):
                industry_votes[industry] += 1
        for node in _extract_jsonld(p.html):
            types = [t.lower() for t in _type_list(node)]
            if any(t in ("product", "service", "softwareapplication") for t in types):
                name = node.get("name") or node.get("headline")
                if isinstance(name, str) and name.strip():
                    products.append(name.strip())
            if "organization" in types and isinstance(node.get("description"), str):
                topics.append(node["description"][:120])

    # Deduplicate preserving order
    def uniq(items: list[str], limit: int = 12) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in items:
            key = x.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(x.strip())
            if len(out) >= limit:
                break
        return out

    # Product fallback from brand + category-ish titles
    if not products and brand:
        for p in elig:
            if p.title and brand.lower() in p.title.lower():
                # strip brand prefix
                rest = re.sub(re.escape(brand), "", p.title, flags=re.I)
                rest = rest.strip(" —-|:")
                if rest and len(rest) > 3:
                    products.append(rest)
        products = uniq(products, 8)

    industry = industry_votes.most_common(1)[0][0] if industry_votes else None
    if not industry and brand:
        # weak guess from domain label
        industry = "saas" if domain_label(base_url) else None

    understanding = SiteUnderstanding(
        organization_brand=brand,
        products_services=uniq(products),
        topics=uniq(topics, 15),
        audience_hints=uniq(audience, 8),
        industry_category_guess=industry,
        commercial_intents=uniq(commercial, 10),
        important_pages=important[:15],
        provenance=provenance,
        method="deterministic_html_v1",
        llm_used=False,
    )

    # Optional LLM — only if explicitly enabled AND key present. Default off.
    if use_llm and openai_api_key:
        # Intentionally not implemented for MVP honesty: do not invent LLM output.
        understanding.method = "deterministic_html_v1+llm_flag_ignored_unimplemented"
        understanding.llm_used = False

    atoms = [
        EvidenceAtom(
            analyzer="site_understanding",
            code="SITE_PROFILE",
            severity="info",
            message=f"Inferred brand={brand!r} industry={industry!r}",
            data=understanding.to_dict(),
            page_id=homepage(pages).id if homepage(pages) else None,
            provenance=provenance,
        )
    ]
    rows = persist_evidence(session, job_id, atoms)
    understanding.evidence_refs = [r.id for r in rows]

    # Persist structured profile row
    existing = session.query(SiteProfile).filter(SiteProfile.job_id == job_id).one_or_none()
    payload = json.dumps(understanding.to_dict(), sort_keys=True)
    if existing:
        existing.profile_json = payload
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
