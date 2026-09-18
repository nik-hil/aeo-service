"""page-intel-v1 — extract observed page facts + answer units."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from aeo_mvp.analyzers.base import parse_html, visible_text, word_count
from aeo_mvp.content.models import (
    PAGE_INTEL_VERSION,
    AnswerUnit,
    HeadingNode,
    ObservedSignal,
    PageIntelligence,
)
from aeo_mvp.queries.evidence import normalize_provenance

_Q_HEAD_RE = re.compile(r"^(who|what|when|where|why|how)\b", re.I)
_DEF_RE = re.compile(r"\b(is|are|means|refers to)\b", re.I)
_STOP = frozenset(
    {
        "the", "and", "for", "with", "from", "this", "that", "your", "our",
        "into", "about", "using", "have", "will", "are", "was", "were",
        "been", "being", "their", "they", "them", "what", "when", "where",
        "which", "while", "a", "an", "of", "to", "in", "on", "at", "by",
        "or", "as", "is", "it", "be",
    }
)


def _content_prov(raw: Any) -> str:
    """Map through 4.1.1 normalize_provenance; never invent observed."""
    return normalize_provenance(raw)


def _meta_content(tree, *, name: str | None = None, prop: str | None = None) -> str | None:
    if name:
        node = tree.css_first(f'meta[name="{name}"]')
        if node:
            c = node.attributes.get("content")
            return c.strip() if c else None
    if prop:
        node = tree.css_first(f'meta[property="{prop}"]')
        if node:
            c = node.attributes.get("content")
            return c.strip() if c else None
    return None


def _parse_jsonld(html: str) -> tuple[list[dict[str, Any]], list[str]]:
    tree = parse_html(html)
    nodes: list[dict[str, Any]] = []
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


def _types(node: dict[str, Any]) -> list[str]:
    t = node.get("@type")
    if isinstance(t, list):
        return [str(x) for x in t]
    if t:
        return [str(t)]
    return []


def _signal(
    key: str,
    value: Any,
    *,
    provenance: Any = "observed",
    evidence_class: str | None = None,
    locator: str | None = None,
    snippet: str | None = None,
) -> ObservedSignal:
    return ObservedSignal(
        key=key,
        value=value,
        provenance=_content_prov(provenance),  # type: ignore[arg-type]
        evidence_class=evidence_class,
        locator=locator,
        snippet=(snippet[:240] if snippet else None),
    )


def _topic_tokens(*texts: str | None, limit: int = 12) -> list[str]:
    bag: dict[str, int] = {}
    for text in texts:
        if not text:
            continue
        for raw in re.findall(r"[A-Za-z][A-Za-z0-9+#-]{2,}", text):
            tok = raw.lower()
            if tok in _STOP or len(tok) < 3:
                continue
            bag[tok] = bag.get(tok, 0) + 1
    ranked = sorted(bag.items(), key=lambda kv: (-kv[1], kv[0]))
    return [t for t, _ in ranked[:limit]]


def _entity_candidates(tree, jsonld_nodes: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for node in jsonld_nodes:
        for key in ("name", "headline"):
            v = node.get(key)
            if isinstance(v, str) and v.strip():
                names.append(v.strip())
        author = node.get("author")
        if isinstance(author, dict) and isinstance(author.get("name"), str):
            names.append(author["name"].strip())
        elif isinstance(author, str):
            names.append(author.strip())
    for a in tree.css("a[href*='/tag/'], a[rel='tag']"):
        t = (a.text() or "").strip().lstrip("#")
        if t:
            names.append(f"#{t}" if "/tag/" in (a.attributes.get("href") or "") else t)
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        key = n.lower()
        if key in seen or len(n) < 2:
            continue
        seen.add(key)
        out.append(n)
    return out[:20]


def _faq(tree, jsonld_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    faq_schema = any("FAQPage" in _types(n) for n in jsonld_nodes)
    questions: list[str] = []
    for node in tree.css("h1, h2, h3, h4, strong, b, summary"):
        text = (node.text() or "").strip()
        if text and (text.endswith("?") or _Q_HEAD_RE.match(text)):
            questions.append(text)
    questions = sorted(set(questions), key=lambda s: s.lower())
    return {
        "has_faq_schema": faq_schema,
        "question_headings": questions,
        "question_count": len(questions),
        "provenance": _content_prov("observed" if questions or faq_schema else None),
    }


def _answerability(text: str, headings: list[HeadingNode]) -> dict[str, Any]:
    has_def = bool(_DEF_RE.search(text[:800])) if text else False
    q_heads = sum(1 for h in headings if h.text.endswith("?") or _Q_HEAD_RE.match(h.text))
    steps = bool(re.search(r"\b(step\s*\d|first,|then,|finally,)\b", text, re.I)) if text else False
    early = text[:500] if text else ""
    answer_first = len(early) >= 40 and (
        "." in early or " is " in early.lower() or " are " in early.lower()
    )
    return {
        "has_definition_pattern": has_def,
        "question_heading_count": q_heads,
        "has_howto_steps": steps,
        "answer_first_heuristic": answer_first,
        "provenance": _content_prov("derived"),
    }


def _answer_units(headings: list[HeadingNode], text: str, faq: dict[str, Any]) -> list[AnswerUnit]:
    units: list[AnswerUnit] = []
    for h in headings:
        kind = "section"
        if h.text.endswith("?") or _Q_HEAD_RE.match(h.text):
            kind = "faq"
        elif re.search(r"\b(how to|steps?|guide)\b", h.text, re.I):
            kind = "howto"
        elif re.search(r"\b(vs|versus|compare)\b", h.text, re.I):
            kind = "comparison"
        elif _DEF_RE.search(h.text):
            kind = "definition"
        uid = hashlib.sha256(f"{kind}|{h.level}|{h.text}".encode()).hexdigest()[:10]
        units.append(
            AnswerUnit(
                unit_id=f"au_{uid}",
                kind=kind,
                heading=h.text,
                passage_preview=(text[:160] if text else None),
                provenance="observed",
            )
        )
    for q in faq.get("question_headings") or []:
        if any(u.heading == q for u in units):
            continue
        uid = hashlib.sha256(f"faq|{q}".encode()).hexdigest()[:10]
        units.append(
            AnswerUnit(
                unit_id=f"au_{uid}",
                kind="faq",
                heading=q,
                provenance="observed",
            )
        )
    units.sort(key=lambda u: (u.kind, u.heading or "", u.unit_id))
    return units


def _internal_links(tree, base_url: str) -> list[dict[str, str]]:
    host = urlparse(base_url).netloc.lower()
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc.lower() != host:
            continue
        text = (a.text() or "").strip() or href
        key = abs_url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        links.append({"url": key, "anchor": text[:120]})
    links.sort(key=lambda x: (x["url"], x["anchor"]))
    return links[:40]


def extract_page_intelligence(
    html: str | None,
    *,
    url: str = "",
    title_hint: str | None = None,
) -> PageIntelligence:
    """Extract page-intel-v1. Observed crawl signals only; missing→compatibility."""
    hostname = urlparse(url).hostname if url else None
    warnings: list[str] = []
    if not html or not str(html).strip():
        return PageIntelligence(
            page_intel_version=PAGE_INTEL_VERSION,
            schema_version=PAGE_INTEL_VERSION,
            url=url,
            hostname=hostname,
            title=title_hint,
            method="deterministic_page_intel_v1+page-intel-v1",
            limits=["thin_copy", "no_answer_first"],
            content_hash=hashlib.sha256(b"").hexdigest()[:16],
            warnings=["empty_page_html"],
            body_signals={"empty": True},
            faq_coverage={"has_faq_schema": False, "question_headings": [], "question_count": 0},
            structured_data={"types": [], "node_count": 0},
            answerability_signals={
                "has_definition_pattern": False,
                "question_heading_count": 0,
                "has_howto_steps": False,
                "answer_first_heuristic": False,
                "provenance": "compatibility",
            },
            signals=[_signal("empty_html", True, provenance=None, evidence_class="metadata")],
            target_match_scope="hostname",
        )

    tree = parse_html(html)
    title_node = tree.css_first("title")
    title = (title_node.text() or "").strip() if title_node else None
    if not title:
        title = title_hint
    meta_desc = _meta_content(tree, name="description") or _meta_content(
        tree, prop="og:description"
    )
    h1_node = tree.css_first("h1")
    h1 = (h1_node.text() or "").strip() if h1_node else None

    headings: list[HeadingNode] = []
    for node in tree.css("h1, h2, h3, h4, h5, h6"):
        tag = node.tag or ""
        if not tag.startswith("h") or not tag[1:].isdigit():
            continue
        text_h = (node.text() or "").strip()
        if not text_h:
            continue
        headings.append(HeadingNode(level=int(tag[1]), text=text_h, provenance="observed"))

    text = visible_text(tree)
    wc = word_count(text)
    jsonld_nodes, jsonld_errors = _parse_jsonld(html)
    if jsonld_errors:
        warnings.append(f"jsonld_parse_errors:{len(jsonld_errors)}")

    types: list[str] = []
    for n in jsonld_nodes:
        for t in _types(n):
            if t not in types:
                types.append(t)
    types.sort()

    topics = _topic_tokens(title, h1, meta_desc, " ".join(h.text for h in headings[:12]))
    for a in tree.css("a[href*='/tag/']"):
        t = (a.text() or "").strip()
        if t and t.lower() not in {x.lower() for x in topics}:
            topics.append(t)
    topics = topics[:16]

    entities = _entity_candidates(tree, jsonld_nodes)
    faq = _faq(tree, jsonld_nodes)
    answerability = _answerability(text, headings)
    units = _answer_units(headings, text, faq)
    links = _internal_links(tree, url or "https://example.invalid/")

    body_signals = {
        "paragraph_count": len(tree.css("main p, article p, p")),
        "has_main": tree.css_first("main") is not None,
        "has_article": tree.css_first("article") is not None,
        "heading_count": len(headings),
        "h1_count": sum(1 for h in headings if h.level == 1),
        "image_count": len(tree.css("img")),
        "figure_count": len(tree.css("figure")),
    }

    signals: list[ObservedSignal] = []
    if title:
        signals.append(
            _signal("title", title, provenance="observed", evidence_class="title_h1", locator="title")
        )
    else:
        signals.append(_signal("title", None, provenance=None, evidence_class="title_h1"))
    if meta_desc:
        signals.append(
            _signal(
                "meta_description",
                meta_desc,
                provenance="observed",
                evidence_class="og_meta",
                locator="meta[name=description]",
                snippet=meta_desc,
            )
        )
    else:
        signals.append(_signal("meta_description", None, provenance=None, evidence_class="og_meta"))
    if h1:
        signals.append(
            _signal("h1", h1, provenance="observed", evidence_class="title_h1", locator="h1")
        )
    if jsonld_nodes:
        signals.append(
            _signal(
                "jsonld_types",
                types,
                provenance="observed",
                evidence_class="jsonld",
                locator='script[type="application/ld+json"]',
            )
        )
    signals.append(
        _signal("word_count", wc, provenance="derived", evidence_class="article_body")
    )
    signals.sort(key=lambda s: (s.key, str(s.provenance)))

    content_hash = hashlib.sha256(
        (html or "").encode("utf-8", errors="replace")
    ).hexdigest()[:16]
    answer_blocks = [u.to_answer_block() for u in units]
    heading_outline = [h.text for h in headings]
    limits: list[str] = []
    if wc < 80:
        limits.append("thin_copy")
    if not answerability.get("answer_first_heuristic"):
        limits.append("no_answer_first")
    if body_signals.get("paragraph_count", 0) == 0 and body_signals.get("has_main") is False:
        limits.append("js_heavy_heuristic")
    # heading skip: large level jumps
    levels = [h.level for h in headings]
    if any(abs(a - b) > 1 for a, b in zip(levels, levels[1:])):
        limits.append("heading_skip")

    content_type = "other"
    type_set = {t.lower() for t in types}
    if "faqpage" in type_set or faq.get("question_count", 0) >= 2:
        content_type = "faq"
    elif "techarticle" in type_set or "documentation" in " ".join(topics).lower():
        content_type = "docs"
    elif "article" in type_set or "blogposting" in type_set:
        content_type = "article"
    elif h1 and wc < 200 and links:
        content_type = "landing"
    elif "about" in (url or "").lower():
        content_type = "about"

    primary_topic = {
        "value": topics[0] if topics else (h1 or title),
        "confidence": 0.35 if topics else 0.2,
        "provenance": "derived" if topics else "compatibility",
        "evidence": [],
    }

    return PageIntelligence(
        page_intel_version=PAGE_INTEL_VERSION,
        schema_version=PAGE_INTEL_VERSION,
        page_id="",
        url=url,
        hostname=hostname,
        title=title,
        primary_topic=primary_topic,
        entities=entities,
        content_type=content_type,  # type: ignore[arg-type]
        answer_blocks=answer_blocks,
        heading_outline=heading_outline,
        word_count=wc,
        schema_types=list(types),
        query_affinities=[],
        limits=limits,
        content_hash=content_hash,
        method="deterministic_page_intel_v1+page-intel-v1",
        meta_description=meta_desc,
        h1=h1,
        headings=headings,
        body_signals=body_signals,
        topics=topics,
        faq_coverage=faq,
        structured_data={
            "types": types,
            "node_count": len(jsonld_nodes),
            "nodes_preview": [
                {"@type": _types(n), "name": n.get("name") or n.get("headline")}
                for n in jsonld_nodes[:5]
            ],
            "provenance": _content_prov("observed" if jsonld_nodes else None),
        },
        answerability_signals=answerability,
        answer_units=units,
        internal_links=links,
        signals=signals,
        target_match_scope="hostname",
        warnings=warnings,
    )
