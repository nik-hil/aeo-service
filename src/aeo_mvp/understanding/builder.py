"""Evidence-first SiteProfile builder (Phase 3).

Priority: titles/H1 → tags/series (topics only) → About/bio → JSON-LD → og:* → body.
Chrome (nav/footer/platform chrome) votes are capped. industry_category defaults to omit.
site_genre is gated before any SaaS industry guess.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from aeo_mvp.analyzers.base import (
    eligible_pages,
    homepage,
    parse_html,
    visible_text,
)
from aeo_mvp.db.models import Page
from aeo_mvp.target_site import resolve_target_site_identity
from aeo_mvp.understanding.profile import (
    HEURISTIC_CONFIDENCE_CAP,
    PROFILE_METHOD,
    EntityMention,
    EvidenceRef,
    SiteProfileField,
    StructuredSiteProfile,
)

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

# Chrome / platform UI headings that must not drive industry votes
CHROME_HEADING_RE = re.compile(
    r"^(command palette|latest articles|trending|popular|newsletter|"
    r"follow me|share this|table of contents|toc|related posts|"
    r"write a response|comments?|subscribe|sign in|log in|"
    r"powered by hashnode|hashnode)$",
    re.I,
)
HASHNODE_CHROME_PATH_RE = re.compile(r"/(tag|series|newsletter)/?", re.I)
TAG_TOKEN_RE = re.compile(r"^#[\w-]+$", re.I)

# Industry patterns — strong compounds only for PM; bare roadmap/kanban are weak
INDUSTRY_STRONG: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bproject[\s-]?management\b", re.I), "project_management"),
    (re.compile(r"\btask[\s-]?board\b", re.I), "project_management"),
    (re.compile(r"\banswer[\s-]?engine\b|\baeo\b|\bseo\b", re.I), "software_documentation"),
    (re.compile(r"\becommerce\b|\bonline store\b|\bshopify\b", re.I), "ecommerce"),
    (re.compile(r"\bsaas\b|\bsoftware as a service\b|\bcloud platform\b", re.I), "saas"),
    (re.compile(r"\bhealthcare\b|\bclinic\b|\bpatient\b", re.I), "healthcare"),
    (re.compile(r"\bfintech\b|\bbanking\b|\bpayments?\b", re.I), "fintech"),
    (
        re.compile(
            r"\bai[\s-]?agent\b|\btool[\s-]?calling\b|\blarge language model\b|"
            r"\bmachine learning\b|\bartificial intelligence\b|\bllm\b|"
            r"\bgenerative ai\b",
            re.I,
        ),
        "ai_ml",
    ),
]
# Weak tokens: may support an industry ONLY alongside a strong match; never alone.
INDUSTRY_WEAK: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\broadmap\b", re.I), "project_management"),
    (re.compile(r"\bkanban\b", re.I), "project_management"),
    (re.compile(r"\bpython\b", re.I), "ai_ml"),
    (re.compile(r"\bsoftware engineering\b", re.I), "ai_ml"),
]

TOPIC_AI_HINTS = re.compile(
    r"\b(ai|agent|llm|tool[\s-]?call|python|harness|filesystem|"
    r"coding agent|provider[\s-]?agnostic|artificial intelligence)\b",
    re.I,
)

AUDIENCE_PATTERNS = [
    (re.compile(r"\bfor\s+(teams|developers|marketers|founders|enterprises|agencies|startups)\b", re.I), "segment"),
    (re.compile(r"\b(b2b|b2c|smb|enterprise|small business)\b", re.I), "market"),
]

# Evidence class weights (chrome capped via separate path)
CLASS_WEIGHT: dict[str, float] = {
    "title_h1": 1.0,
    "tags_series": 0.85,
    "about_bio": 0.9,
    "jsonld": 0.95,
    "og_meta": 0.7,
    "article_body": 0.55,
    "url_path": 0.4,
    "metadata": 0.5,
    "chrome": 0.15,
}
CHROME_VOTE_CAP = 1  # max industry votes attributable to chrome across the site

INDUSTRY_MIN_VOTES = 3
INDUSTRY_LEAD_MARGIN = 2


@dataclass
class _Signal:
    text: str
    evidence_class: str
    url: str | None
    page_id: str | None
    locator: str
    weight: float = 1.0


@dataclass
class _BuildCtx:
    signals: list[_Signal] = field(default_factory=list)
    tags: list[_Signal] = field(default_factory=list)
    products: list[_Signal] = field(default_factory=list)
    authors: list[_Signal] = field(default_factory=list)
    audience: list[_Signal] = field(default_factory=list)
    content_types: set[str] = field(default_factory=set)
    commercial: list[str] = field(default_factory=list)
    important: list[dict[str, Any]] = field(default_factory=list)
    jsonld_types: set[str] = field(default_factory=set)
    has_person: bool = False
    has_blog: bool = False
    has_product_schema: bool = False
    description: str | None = None
    description_ev: list[EvidenceRef] = field(default_factory=list)
    brand_candidates: list[tuple[str, EvidenceRef]] = field(default_factory=list)


def _eid() -> str:
    return str(uuid4())


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


def _headings(html: str) -> list[tuple[str, str]]:
    tree = parse_html(html)
    out: list[tuple[str, str]] = []
    for sel in ("h1", "h2", "h3"):
        for node in tree.css(sel):
            t = re.sub(r"\s+", " ", (node.text() or "").strip())
            if t:
                out.append((sel, t))
    return out


def _is_chrome_heading(text: str) -> bool:
    return bool(CHROME_HEADING_RE.match(text.strip()))


def _is_tag_token(text: str) -> bool:
    t = text.strip()
    return bool(TAG_TOKEN_RE.match(t)) or (
        t.startswith("#") and len(t) > 1 and " " not in t
    )


def _path_is_chrome(path: str) -> bool:
    return bool(HASHNODE_CHROME_PATH_RE.search(path))


def _ref(
    *,
    url: str | None,
    snippet: str,
    locator: str,
    page_id: str | None,
    evidence_class: str,
    weight: float | None = None,
) -> EvidenceRef:
    w = weight if weight is not None else CLASS_WEIGHT.get(evidence_class, 0.5)
    return EvidenceRef(
        evidence_id=_eid(),
        url=url,
        snippet=snippet[:200] if snippet else None,
        locator=locator,
        page_id=page_id,
        evidence_class=evidence_class,  # type: ignore[arg-type]
        weight=w,
    )


def _collect_page_signals(page: Page, ctx: _BuildCtx) -> None:
    path = urlparse(page.url).path.lower() or "/"
    depth = page.depth
    reason_bits: list[str] = []
    if depth == 0:
        reason_bits.append("homepage")
    for hint in IMPORTANT_PATH_HINTS:
        if hint in path.strip("/").split("/") or f"/{hint}" in path:
            reason_bits.append(f"path:{hint}")
            break
    for hint in COMMERCIAL_PATH_HINTS:
        if hint in path:
            ctx.commercial.append(hint)
            reason_bits.append(f"commercial:{hint}")
            break
    if reason_bits:
        ctx.important.append(
            {
                "url": page.url,
                "title": page.title,
                "depth": depth,
                "reasons": sorted(set(reason_bits)),
            }
        )

    chrome_path = _path_is_chrome(path)
    if not page.html:
        if page.title:
            cls = "chrome" if chrome_path else "title_h1"
            ctx.signals.append(
                _Signal(
                    text=page.title,
                    evidence_class=cls,
                    url=page.url,
                    page_id=page.id,
                    locator="title",
                    weight=CLASS_WEIGHT[cls],
                )
            )
        return

    tree = parse_html(page.html)

    # Titles / H1 (highest priority)
    if page.title and not chrome_path:
        ctx.signals.append(
            _Signal(
                text=page.title,
                evidence_class="title_h1",
                url=page.url,
                page_id=page.id,
                locator="title",
                weight=CLASS_WEIGHT["title_h1"],
            )
        )
        if _is_tag_token(page.title.strip()):
            ctx.tags.append(
                _Signal(
                    text=page.title.strip(),
                    evidence_class="tags_series",
                    url=page.url,
                    page_id=page.id,
                    locator="title_tag",
                    weight=CLASS_WEIGHT["tags_series"],
                )
            )

    for sel, text in _headings(page.html):
        if _is_chrome_heading(text) or chrome_path:
            ctx.signals.append(
                _Signal(
                    text=text,
                    evidence_class="chrome",
                    url=page.url,
                    page_id=page.id,
                    locator=sel,
                    weight=CLASS_WEIGHT["chrome"],
                )
            )
            continue
        if _is_tag_token(text) or path.startswith("/tag/"):
            ctx.tags.append(
                _Signal(
                    text=text,
                    evidence_class="tags_series",
                    url=page.url,
                    page_id=page.id,
                    locator=sel,
                    weight=CLASS_WEIGHT["tags_series"],
                )
            )
            ctx.signals.append(
                _Signal(
                    text=text,
                    evidence_class="tags_series",
                    url=page.url,
                    page_id=page.id,
                    locator=sel,
                    weight=CLASS_WEIGHT["tags_series"],
                )
            )
            continue
        cls = "title_h1" if sel == "h1" else "article_body"
        ctx.signals.append(
            _Signal(
                text=text,
                evidence_class=cls,
                url=page.url,
                page_id=page.id,
                locator=sel,
                weight=CLASS_WEIGHT[cls],
            )
        )

    # og / meta
    og_site = tree.css_first('meta[property="og:site_name"]')
    if og_site and og_site.attributes.get("content"):
        name = og_site.attributes["content"].strip()
        ctx.brand_candidates.append(
            (
                name,
                _ref(
                    url=page.url,
                    snippet=name,
                    locator="meta[property=og:site_name]",
                    page_id=page.id,
                    evidence_class="og_meta",
                ),
            )
        )
    og_desc = tree.css_first('meta[property="og:description"]') or tree.css_first(
        'meta[name="description"]'
    )
    if og_desc and og_desc.attributes.get("content") and not ctx.description:
        ctx.description = og_desc.attributes["content"].strip()
        ctx.description_ev = [
            _ref(
                url=page.url,
                snippet=ctx.description,
                locator="meta[description]",
                page_id=page.id,
                evidence_class="og_meta",
            )
        ]

    # About / bio path boost
    if "about" in path or "bio" in path or "author" in path:
        text = visible_text(parse_html(page.html))[:500]
        if text:
            ctx.signals.append(
                _Signal(
                    text=text,
                    evidence_class="about_bio",
                    url=page.url,
                    page_id=page.id,
                    locator="about_body",
                    weight=CLASS_WEIGHT["about_bio"],
                )
            )

    # JSON-LD
    for node in _extract_jsonld(page.html):
        types = [t.lower() for t in _type_list(node)]
        for t in types:
            ctx.jsonld_types.add(t)
        if any(t in ("person",) for t in types):
            ctx.has_person = True
            name = node.get("name")
            if isinstance(name, str) and name.strip():
                ctx.authors.append(
                    _Signal(
                        text=name.strip(),
                        evidence_class="jsonld",
                        url=page.url,
                        page_id=page.id,
                        locator="jsonld:Person",
                        weight=CLASS_WEIGHT["jsonld"],
                    )
                )
                ctx.brand_candidates.append(
                    (
                        name.strip(),
                        _ref(
                            url=page.url,
                            snippet=name.strip(),
                            locator="jsonld:Person.name",
                            page_id=page.id,
                            evidence_class="jsonld",
                        ),
                    )
                )
        if any(t in ("blog", "blogposting", "article", "techarticle") for t in types):
            ctx.has_blog = True
            ctx.content_types.add("blog_post" if "blogposting" in types or "article" in types else "blog")
            headline = node.get("headline") or node.get("name")
            if isinstance(headline, str) and headline.strip():
                ctx.signals.append(
                    _Signal(
                        text=headline.strip(),
                        evidence_class="jsonld",
                        url=page.url,
                        page_id=page.id,
                        locator="jsonld:BlogPosting",
                        weight=CLASS_WEIGHT["jsonld"],
                    )
                )
            author = node.get("author")
            if isinstance(author, dict) and isinstance(author.get("name"), str):
                ctx.authors.append(
                    _Signal(
                        text=author["name"].strip(),
                        evidence_class="jsonld",
                        url=page.url,
                        page_id=page.id,
                        locator="jsonld:author",
                        weight=CLASS_WEIGHT["jsonld"],
                    )
                )
            elif isinstance(author, str) and author.strip():
                ctx.authors.append(
                    _Signal(
                        text=author.strip(),
                        evidence_class="jsonld",
                        url=page.url,
                        page_id=page.id,
                        locator="jsonld:author",
                        weight=CLASS_WEIGHT["jsonld"],
                    )
                )
        if any(t in ("product", "service", "softwareapplication") for t in types):
            ctx.has_product_schema = True
            name = node.get("name") or node.get("headline")
            if isinstance(name, str) and name.strip() and not _is_tag_token(name):
                ctx.products.append(
                    _Signal(
                        text=name.strip(),
                        evidence_class="jsonld",
                        url=page.url,
                        page_id=page.id,
                        locator="jsonld:Product",
                        weight=CLASS_WEIGHT["jsonld"],
                    )
                )
        if any(t in ("organization", "localbusiness", "corporation") for t in types):
            name = node.get("name")
            if isinstance(name, str) and name.strip():
                ctx.brand_candidates.append(
                    (
                        name.strip(),
                        _ref(
                            url=page.url,
                            snippet=name.strip(),
                            locator="jsonld:Organization.name",
                            page_id=page.id,
                            evidence_class="jsonld",
                        ),
                    )
                )
            desc = node.get("description")
            if isinstance(desc, str) and desc.strip() and not ctx.description:
                ctx.description = desc.strip()[:300]
                ctx.description_ev = [
                    _ref(
                        url=page.url,
                        snippet=ctx.description,
                        locator="jsonld:Organization.description",
                        page_id=page.id,
                        evidence_class="jsonld",
                    )
                ]

    # Audience from body (non-chrome)
    if not chrome_path:
        text = visible_text(parse_html(page.html))
        for pat, _label in AUDIENCE_PATTERNS:
            m = pat.search(text)
            if m:
                ctx.audience.append(
                    _Signal(
                        text=m.group(0),
                        evidence_class="article_body",
                        url=page.url,
                        page_id=page.id,
                        locator="body:audience",
                        weight=CLASS_WEIGHT["article_body"],
                    )
                )
        # Sample body for topic signals (capped length)
        body_sample = text[:800]
        if body_sample and depth <= 1:
            ctx.signals.append(
                _Signal(
                    text=body_sample,
                    evidence_class="article_body",
                    url=page.url,
                    page_id=page.id,
                    locator="body_sample",
                    weight=CLASS_WEIGHT["article_body"] * 0.5,
                )
            )


def _uniq_str(items: list[str], limit: int = 12) -> list[str]:
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


def _infer_genre(ctx: _BuildCtx, commercial: list[str]) -> tuple[str | None, float, list[EvidenceRef], list[str]]:
    """Genre gate before industry. Blog+Person, no Product/pricing → personal_tech_blog."""
    warnings: list[str] = []
    evidence: list[EvidenceRef] = []
    has_pricing = any(c in ("pricing", "price", "plans", "buy", "shop", "cart", "checkout") for c in commercial)
    bloggy = ctx.has_blog or "blog_post" in ctx.content_types or any(
        s.evidence_class in ("title_h1", "tags_series") and TOPIC_AI_HINTS.search(s.text)
        for s in ctx.signals
    )
    taggy = len(ctx.tags) >= 2
    no_product = not ctx.has_product_schema and not ctx.products

    if (ctx.has_person or ctx.has_blog or taggy) and bloggy and no_product and not has_pricing:
        # personal tech blog / publication
        for s in ctx.authors[:2]:
            evidence.append(
                _ref(
                    url=s.url,
                    snippet=s.text,
                    locator=s.locator,
                    page_id=s.page_id,
                    evidence_class=s.evidence_class,
                )
            )
        for s in ctx.tags[:3]:
            evidence.append(
                _ref(
                    url=s.url,
                    snippet=s.text,
                    locator=s.locator,
                    page_id=s.page_id,
                    evidence_class="tags_series",
                )
            )
        genre = "personal_tech_blog"
        conf = min(0.38, HEURISTIC_CONFIDENCE_CAP)
        if ctx.has_person and ctx.has_blog:
            conf = min(0.40, HEURISTIC_CONFIDENCE_CAP)
        return genre, conf, evidence, warnings

    if ctx.has_product_schema or has_pricing:
        return "saas_product", 0.35, evidence, warnings

    if bloggy:
        return "content_site", 0.30, evidence, warnings

    return None, 0.0, evidence, warnings


def _industry_votes(ctx: _BuildCtx) -> tuple[str | None, float, list[EvidenceRef], list[str]]:
    """Assert industry only if thresholds met. Bare roadmap/kanban alone never wins PM."""
    warnings: list[str] = []
    strong_votes: Counter[str] = Counter()
    weak_votes: Counter[str] = Counter()
    evidence_by: dict[str, list[EvidenceRef]] = defaultdict(list)
    chrome_votes_used = 0

    for sig in ctx.signals:
        is_chrome = sig.evidence_class == "chrome"
        if is_chrome and chrome_votes_used >= CHROME_VOTE_CAP:
            continue
        # Strong patterns
        matched_strong = False
        for pat, industry in INDUSTRY_STRONG:
            if pat.search(sig.text):
                # Weight: title/h1/jsonld count more; chrome at most 1 total vote
                vote = 1.0 if not is_chrome else 0.25
                if sig.evidence_class == "title_h1":
                    vote = 1.5
                elif sig.evidence_class == "jsonld":
                    vote = 1.25
                elif sig.evidence_class == "article_body":
                    vote = 0.5
                strong_votes[industry] += vote
                evidence_by[industry].append(
                    _ref(
                        url=sig.url,
                        snippet=sig.text[:160],
                        locator=sig.locator,
                        page_id=sig.page_id,
                        evidence_class=sig.evidence_class,
                        weight=sig.weight,
                    )
                )
                matched_strong = True
                if is_chrome:
                    chrome_votes_used += 1
                break
        if matched_strong:
            continue
        for pat, industry in INDUSTRY_WEAK:
            if pat.search(sig.text):
                weak_votes[industry] += 0.25 if not is_chrome else 0.05
                if is_chrome:
                    chrome_votes_used += 1
                break

    if not strong_votes:
        # Weak-only votes never assert (fixes bare roadmap → project_management)
        if weak_votes:
            top_w, _ = weak_votes.most_common(1)[0]
            warnings.append(
                f"weak_industry_tokens_only:{top_w}:omitted"
            )
        return None, 0.0, [], warnings

    # Combine: weak only as tie-break support, not primary
    combined: Counter[str] = Counter()
    for ind, v in strong_votes.items():
        combined[ind] = v + min(weak_votes.get(ind, 0), 0.5)

    ranked = combined.most_common()
    top, top_n = ranked[0]
    second_n = ranked[1][1] if len(ranked) > 1 else 0.0

    # Thresholds: ≥3 strong-equivalent votes, lead ≥2
    if top_n < INDUSTRY_MIN_VOTES or (top_n - second_n) < INDUSTRY_LEAD_MARGIN:
        warnings.append(
            f"industry_threshold_not_met:top={top}:{top_n:.2f}:second={second_n:.2f}"
        )
        return None, 0.0, evidence_by.get(top, [])[:5], warnings

    # Distinct evidence classes required (≥2) for assertion
    classes = {e.evidence_class for e in evidence_by.get(top, []) if e.evidence_class != "chrome"}
    if len(classes) < 2:
        warnings.append(f"industry_insufficient_evidence_classes:{top}:{sorted(classes)}")
        return None, 0.0, evidence_by.get(top, [])[:5], warnings

    conf = min(0.40, 0.25 + 0.03 * top_n)
    return top, conf, evidence_by.get(top, [])[:8], warnings


def _pick_brand(ctx: _BuildCtx, base_url: str) -> tuple[str | None, list[EvidenceRef]]:
    identity = resolve_target_site_identity(base_url)
    # Never use multi-tenant platform apex as brand
    label = ""
    if identity.multi_tenant_host and identity.identity_kind != "platform_apex":
        host = identity.hostname_apex_normalized or identity.hostname
        label = host.split(".")[0] if host else ""
    else:
        host = identity.registrable_domain or ""
        label = host.split(".")[0] if host else ""

    counts: Counter[str] = Counter()
    ev_map: dict[str, EvidenceRef] = {}
    for name, ev in ctx.brand_candidates:
        # Reject platform apex names
        low = name.lower()
        if low in ("hashnode", "wordpress", "medium", "substack", "ghost", "tumblr"):
            continue
        counts[low] += 1
        ev_map.setdefault(low, ev)
    for a in ctx.authors:
        counts[a.text.lower()] += 2
        ev_map.setdefault(
            a.text.lower(),
            _ref(
                url=a.url,
                snippet=a.text,
                locator=a.locator,
                page_id=a.page_id,
                evidence_class=a.evidence_class,
            ),
        )

    if counts:
        top = counts.most_common(1)[0][0]
        # Prefer original casing from candidates
        for name, ev in ctx.brand_candidates:
            if name.lower() == top:
                return name, [ev]
        for a in ctx.authors:
            if a.text.lower() == top:
                return a.text, [ev_map[top]]
        return top, [ev_map[top]]

    if label:
        return label, [
            _ref(
                url=base_url,
                snippet=label,
                locator="hostname_label",
                page_id=None,
                evidence_class="url_path",
            )
        ]
    return None, []


def _topics_from_signals(ctx: _BuildCtx) -> tuple[list[str], list[str], list[EvidenceRef]]:
    primary: list[str] = []
    secondary: list[str] = []
    evidence: list[EvidenceRef] = []
    seen: set[str] = set()

    def add(text: str, bucket: list[str], sig: _Signal) -> None:
        key = text.lower().strip()
        if not key or key in seen or _is_chrome_heading(text):
            return
        if len(text) < 3:
            return
        seen.add(key)
        bucket.append(text.strip())
        evidence.append(
            _ref(
                url=sig.url,
                snippet=text[:160],
                locator=sig.locator,
                page_id=sig.page_id,
                evidence_class=sig.evidence_class,
            )
        )

    # Titles / H1 first
    for sig in ctx.signals:
        if sig.evidence_class == "title_h1":
            add(sig.text, primary, sig)
    # Tags / series → topics only (never products)
    for sig in ctx.tags:
        add(sig.text, primary if TOPIC_AI_HINTS.search(sig.text) else secondary, sig)
    # JSON-LD headlines
    for sig in ctx.signals:
        if sig.evidence_class == "jsonld":
            add(sig.text, primary, sig)
    # Other headings as secondary
    for sig in ctx.signals:
        if sig.evidence_class == "article_body" and sig.locator in ("h2", "h3"):
            add(sig.text, secondary, sig)

    return _uniq_str(primary, 12), _uniq_str(secondary, 12), evidence[:20]


def _evidence_hash(ctx: _BuildCtx, profile_bits: dict[str, Any]) -> str:
    payload = {
        "signals": sorted({(s.evidence_class, s.text[:80].lower()) for s in ctx.signals}),
        "tags": sorted({s.text.lower() for s in ctx.tags}),
        "bits": profile_bits,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_structured_profile(
    pages: list[Page],
    base_url: str,
    *,
    provenance: str = "derived_metric",
) -> StructuredSiteProfile:
    """Build evidence-first StructuredSiteProfile from crawled pages."""
    elig = eligible_pages(pages)
    ctx = _BuildCtx()
    for p in elig:
        _collect_page_signals(p, ctx)

    warnings: list[str] = []
    identity = resolve_target_site_identity(base_url)
    hostname = identity.hostname_apex_normalized or identity.hostname

    brand, brand_ev = _pick_brand(ctx, base_url)
    primary, secondary, topic_ev = _topics_from_signals(ctx)

    # Tags must never appear in products
    products = _uniq_str(
        [s.text for s in ctx.products if not _is_tag_token(s.text)], 8
    )
    product_ev = [
        _ref(
            url=s.url,
            snippet=s.text,
            locator=s.locator,
            page_id=s.page_id,
            evidence_class=s.evidence_class,
        )
        for s in ctx.products
        if not _is_tag_token(s.text)
    ][:8]

    authors = _uniq_str([s.text for s in ctx.authors], 6)
    author_ev = [
        _ref(
            url=s.url,
            snippet=s.text,
            locator=s.locator,
            page_id=s.page_id,
            evidence_class=s.evidence_class,
        )
        for s in ctx.authors
    ][:6]

    audience = _uniq_str([s.text for s in ctx.audience], 8)
    content_types = sorted(ctx.content_types) or (
        ["blog_post"] if ctx.has_blog else []
    )

    genre, genre_conf, genre_ev, genre_warn = _infer_genre(ctx, ctx.commercial)
    warnings.extend(genre_warn)

    industry, ind_conf, ind_ev, ind_warn = _industry_votes(ctx)
    warnings.extend(ind_warn)

    # Genre gate: personal_tech_blog must not get SaaS industry without strong product evidence
    if genre == "personal_tech_blog" and industry in ("project_management", "saas", "ecommerce"):
        # Only keep if strong product schema + pricing; else omit and prefer ai_ml if present
        if not ctx.has_product_schema:
            if any(s.evidence_class != "chrome" for s in ctx.signals if TOPIC_AI_HINTS.search(s.text)):
                # Prefer ai_ml when AI language dominates
                ai_votes = sum(
                    1
                    for s in ctx.signals
                    if s.evidence_class in ("title_h1", "tags_series", "jsonld")
                    and TOPIC_AI_HINTS.search(s.text)
                )
                if ai_votes >= 2:
                    industry, ind_conf = "ai_ml", min(0.38, HEURISTIC_CONFIDENCE_CAP)
                    ind_ev = [
                        _ref(
                            url=s.url,
                            snippet=s.text[:160],
                            locator=s.locator,
                            page_id=s.page_id,
                            evidence_class=s.evidence_class,
                        )
                        for s in ctx.signals
                        if TOPIC_AI_HINTS.search(s.text)
                        and s.evidence_class != "chrome"
                    ][:6]
                    warnings.append("genre_gate:overrode_saas_industry_with_ai_ml")
                else:
                    warnings.append(f"genre_gate:omitted_industry:{industry}")
                    industry, ind_conf, ind_ev = None, 0.0, []
            else:
                warnings.append(f"genre_gate:omitted_industry:{industry}")
                industry, ind_conf, ind_ev = None, 0.0, []

    # Entities from topics + authors
    entities: list[EntityMention] = []
    for a in authors:
        entities.append(EntityMention(name=a, type="person", confidence=0.35))
    for t in primary[:8]:
        etype = "technology" if TOPIC_AI_HINTS.search(t) else "concept"
        entities.append(EntityMention(name=t[:80], type=etype, confidence=0.30))

    field_prov: Any = "heuristic" if provenance == "derived_metric" else provenance

    org_field = (
        SiteProfileField.from_heuristic(brand, confidence=0.36, evidence=brand_ev, provenance=field_prov)
        if brand
        else SiteProfileField.omitted_field(reason="no_brand_evidence")
    )
    host_field = SiteProfileField.from_heuristic(
        hostname,
        confidence=0.40,
        evidence=[
            _ref(
                url=base_url,
                snippet=hostname,
                locator="target_site.hostname",
                page_id=homepage(pages).id if homepage(pages) else None,
                evidence_class="url_path",
            )
        ],
        provenance="observed",
    )
    desc_field = (
        SiteProfileField.from_heuristic(
            ctx.description, confidence=0.34, evidence=ctx.description_ev, provenance=field_prov
        )
        if ctx.description
        else SiteProfileField.omitted_field(reason="no_description")
    )
    primary_field = (
        SiteProfileField.from_heuristic(primary, confidence=0.38, evidence=topic_ev[:10], provenance=field_prov)
        if primary
        else SiteProfileField.omitted_field(reason="no_primary_topics")
    )
    secondary_field = (
        SiteProfileField.from_heuristic(secondary, confidence=0.30, evidence=topic_ev[10:], provenance=field_prov)
        if secondary
        else SiteProfileField.omitted_field(reason="no_secondary_topics")
    )
    entities_field = (
        SiteProfileField.from_heuristic(
            [e.to_dict() for e in entities],
            confidence=0.32,
            evidence=author_ev + topic_ev[:4],
            provenance=field_prov,
        )
        if entities
        else SiteProfileField.omitted_field(reason="no_entities")
    )
    products_field = (
        SiteProfileField.from_heuristic(products, confidence=0.36, evidence=product_ev, provenance=field_prov)
        if products
        else SiteProfileField.omitted_field(reason="no_product_schema")
    )
    authors_field = (
        SiteProfileField.from_heuristic(authors, confidence=0.36, evidence=author_ev, provenance=field_prov)
        if authors
        else SiteProfileField.omitted_field(reason="no_authors")
    )
    audience_field = (
        SiteProfileField.from_heuristic(audience, confidence=0.28, evidence=[], provenance=field_prov)
        if audience
        else SiteProfileField.omitted_field(reason="no_audience_hints")
    )
    content_field = (
        SiteProfileField.from_heuristic(content_types, confidence=0.34, evidence=[], provenance=field_prov)
        if content_types
        else SiteProfileField.omitted_field(reason="no_content_types")
    )
    genre_field = (
        SiteProfileField.from_heuristic(genre, confidence=genre_conf, evidence=genre_ev, provenance=field_prov)
        if genre
        else SiteProfileField.omitted_field(reason="genre_undetermined")
    )
    industry_field = (
        SiteProfileField.from_heuristic(industry, confidence=ind_conf, evidence=ind_ev, provenance=field_prov)
        if industry
        else SiteProfileField.omitted_field(
            reason="industry_defaults_to_omit"
            if not ind_warn
            else ";".join(ind_warn)[:200]
        )
    )
    commercial_field = (
        SiteProfileField.from_heuristic(
            _uniq_str(ctx.commercial, 10), confidence=0.35, evidence=[], provenance=field_prov
        )
        if ctx.commercial
        else SiteProfileField.omitted_field(reason="no_commercial_paths")
    )

    ehash = _evidence_hash(
        ctx,
        {
            "brand": brand,
            "genre": genre,
            "industry": industry,
            "primary": primary[:5],
        },
    )

    return StructuredSiteProfile(
        org_name=org_field,
        hostname=host_field,
        description=desc_field,
        primary_topics=primary_field,
        secondary_topics=secondary_field,
        entities=entities_field,
        products=products_field,
        authors=authors_field,
        audience=audience_field,
        content_types=content_field,
        industry_category=industry_field,
        site_genre=genre_field,
        commercial_signals=commercial_field,
        important_pages=ctx.important[:15],
        method=PROFILE_METHOD,
        llm_used=False,
        warnings=warnings,
        evidence_hash=ehash,
    )
