"""Content Readiness + Answerability inputs (METRICS §4 and parts of §7)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from aeo_mvp.analyzers.base import (
    EvidenceAtom,
    eligible_pages,
    homepage,
    parse_html,
    persist_evidence,
    visible_text,
    word_count,
)
from aeo_mvp.db.models import Page
from sqlalchemy.orm import Session

_DEF_RE = re.compile(r"\b(is|are|means|refers to)\b", re.I)
_Q_HEAD_RE = re.compile(r"^(who|what|when|where|why|how)\b", re.I)


@dataclass
class PageContentScore:
    url: str
    page_id: str
    score: float
    checks: dict[str, float]
    faq_shaped: bool
    has_definition: bool
    question_headings: int
    has_howto_steps: bool


@dataclass
class ContentResult:
    content_score: float
    answerability_score: float
    page_scores: list[PageContentScore]
    content_breakdown: dict[str, Any]
    answerability_breakdown: dict[str, Any]
    evidence_ids: list[str]
    checks_a: dict[str, float] = field(default_factory=dict)


def _heading_levels(tree) -> list[int]:
    levels: list[int] = []
    for i in range(1, 7):
        for _ in tree.css(f"h{i}"):
            levels.append(i)
    # Preserve document order
    ordered: list[int] = []
    for node in tree.css("h1, h2, h3, h4, h5, h6"):
        tag = node.tag
        if tag and tag.startswith("h") and tag[1:].isdigit():
            ordered.append(int(tag[1]))
    return ordered


def _has_heading_skips(levels: list[int]) -> bool:
    if not levels:
        return False
    prev = levels[0]
    for lvl in levels[1:]:
        if lvl > prev + 1:
            return True
        prev = lvl
    return False


def _answer_first(tree) -> bool:
    main = tree.css_first("main") or tree.body or tree
    # Collect early text from p/li
    chunks: list[str] = []
    total = 0
    for node in main.css("p, li"):
        t = (node.text() or "").strip()
        if len(t) < 20:
            continue
        chunks.append(t)
        total += len(t)
        if total >= 500:
            break
    blob = " ".join(chunks)[:500]
    # Declarative sentence >= 40 chars ending with . ! or long enough clause
    for part in re.split(r"[.!?]\s+", blob):
        if len(part.strip()) >= 40:
            return True
    return len(blob) >= 40 and (" is " in blob.lower() or " are " in blob.lower() or "," in blob)


def _has_faq_shape(tree, html: str) -> bool:
    # JSON-LD FAQPage
    if '"@type"' in html and "FAQPage" in html:
        return True
    headings = tree.css("h1, h2, h3, h4, strong, b")
    for node in headings:
        text = (node.text() or "").strip()
        if not text:
            continue
        is_q = text.endswith("?") or bool(_Q_HEAD_RE.match(text))
        if not is_q:
            continue
        # following paragraph sibling-ish: look at next elements in parent
        parent = node.parent
        if not parent:
            continue
        found_self = False
        for child in parent.iter():
            if child == node:
                found_self = True
                continue
            if not found_self:
                continue
            if child.tag in ("p", "div") and len((child.text() or "").strip()) >= 40:
                return True
            if child.tag in ("h1", "h2", "h3", "h4"):
                break
    return False


def _paragraph_pass(tree) -> float:
    usable = 0
    for p in tree.css("p"):
        wc = word_count((p.text() or "").strip())
        if 40 <= wc <= 300:
            usable += 1
    if 2 <= usable <= 30:
        return 1.0
    if usable == 1 or usable > 30:
        return 0.5
    return 0.0


def _wordcount_pass(text: str) -> float:
    wc = word_count(text)
    if 300 <= wc <= 5000:
        return 1.0
    if 100 <= wc <= 299 or 5001 <= wc <= 8000:
        return 0.5
    return 0.0


def _howto(tree, html: str) -> bool:
    if "HowTo" in html and "application/ld+json" in html:
        return True
    for ol in tree.css("ol"):
        steps = ol.css("li")
        if len(steps) >= 3:
            return True
    return False


def _question_heading_count(tree) -> int:
    count = 0
    for node in tree.css("h1, h2, h3, h4, h5, h6"):
        text = (node.text() or "").strip()
        if text.endswith("?") or _Q_HEAD_RE.match(text):
            count += 1
    return count


def _score_page(page: Page) -> PageContentScore:
    assert page.html
    tree = parse_html(page.html)
    weights = {"C1": 0.25, "C2": 0.25, "C3": 0.20, "C4": 0.15, "C5": 0.15}
    levels = _heading_levels(tree)
    h1_count = sum(1 for l in levels if l == 1)
    skips = _has_heading_skips(levels)
    if h1_count == 1 and not skips:
        c1 = 1.0
    elif h1_count == 1 and skips:
        c1 = 0.5
    else:
        c1 = 0.0
    c2 = 1.0 if _answer_first(tree) else 0.0
    faq = _has_faq_shape(tree, page.html)
    c3 = 1.0 if faq else 0.0
    c4 = _paragraph_pass(tree)
    text = visible_text(tree)
    c5 = _wordcount_pass(text)
    checks = {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5}
    score = 100.0 * sum(weights[k] * checks[k] for k in weights)
    first_ps = tree.css("p")[:2]
    first_text = " ".join((p.text() or "") for p in first_ps)
    has_def = bool(_DEF_RE.search(first_text))
    return PageContentScore(
        url=page.url,
        page_id=page.id,
        score=score,
        checks=checks,
        faq_shaped=faq,
        has_definition=has_def,
        question_headings=_question_heading_count(tree),
        has_howto_steps=_howto(tree, page.html),
    )


def analyze_content(
    session: Session,
    job_id: str,
    pages: list[Page],
    *,
    provenance: str = "derived_metric",
) -> ContentResult:
    elig = eligible_pages(pages)
    atoms: list[EvidenceAtom] = []
    page_scores = [_score_page(p) for p in elig]

    if page_scores:
        content_score = sum(ps.score for ps in page_scores) / len(page_scores)
    else:
        content_score = 0.0
    content_score = max(0.0, min(100.0, content_score))

    for ps in page_scores:
        atoms.append(
            EvidenceAtom(
                analyzer="content",
                code="CONTENT_HEADINGS",
                severity="medium" if ps.checks["C1"] < 1 else "info",
                message=f"Heading hierarchy pass={ps.checks['C1']} on {ps.url}",
                data={"pass": ps.checks["C1"], "url": ps.url},
                page_id=ps.page_id,
                provenance=provenance,
            )
        )
        atoms.append(
            EvidenceAtom(
                analyzer="content",
                code="CONTENT_ANSWER_FIRST",
                severity="medium" if ps.checks["C2"] == 0 else "info",
                message=f"Answer-first pass={ps.checks['C2']}",
                data={"pass": ps.checks["C2"], "url": ps.url},
                page_id=ps.page_id,
                provenance=provenance,
            )
        )
        atoms.append(
            EvidenceAtom(
                analyzer="content",
                code="CONTENT_FAQ_SHAPE",
                severity="low" if ps.checks["C3"] == 0 else "info",
                message=f"FAQ shape pass={ps.checks['C3']}",
                data={"pass": ps.checks["C3"], "url": ps.url},
                page_id=ps.page_id,
                provenance=provenance,
            )
        )
        atoms.append(
            EvidenceAtom(
                analyzer="content",
                code="CONTENT_PARAGRAPHS",
                severity="low" if ps.checks["C4"] < 1 else "info",
                message=f"Usable paragraphs pass={ps.checks['C4']}",
                data={"pass": ps.checks["C4"], "url": ps.url},
                page_id=ps.page_id,
                provenance=provenance,
            )
        )
        atoms.append(
            EvidenceAtom(
                analyzer="content",
                code="CONTENT_WORDCOUNT",
                severity="medium" if ps.checks["C5"] < 0.5 else "info",
                message=f"Wordcount pass={ps.checks['C5']}",
                data={"pass": ps.checks["C5"], "url": ps.url},
                page_id=ps.page_id,
                provenance=provenance,
            )
        )

    # Answerability site-level
    n = len(page_scores) or 1
    def_share = sum(1 for ps in page_scores if ps.has_definition) / n if page_scores else 0.0
    if def_share >= 0.3:
        a1 = 1.0
    elif def_share >= 0.1:
        a1 = 0.5
    else:
        a1 = 0.0
    a2 = 1.0 if any(ps.has_howto_steps for ps in page_scores) else 0.0
    q_total = sum(ps.question_headings for ps in page_scores)
    if q_total >= 2:
        a3 = 1.0
    elif q_total == 1:
        a3 = 0.5
    else:
        a3 = 0.0
    faq_density = (
        sum(1 for ps in page_scores if ps.faq_shaped) / len(page_scores) if page_scores else 0.0
    )
    if faq_density >= 0.15:
        a4 = 1.0
    elif faq_density >= 0.05:
        a4 = 0.5
    else:
        a4 = 0.0
    a_weights = {"A1": 0.25, "A2": 0.25, "A3": 0.25, "A4": 0.25}
    checks_a = {"A1": a1, "A2": a2, "A3": a3, "A4": a4}
    answerability = 100.0 * sum(a_weights[k] * checks_a[k] for k in a_weights)
    answerability = max(0.0, min(100.0, answerability))

    atoms.extend(
        [
            EvidenceAtom(
                analyzer="content",
                code="ANS_DEFINITION",
                severity="low" if a1 < 1 else "info",
                message=f"Definition pattern share={def_share:.2f}",
                data={"pass": a1, "share": def_share},
                provenance=provenance,
            ),
            EvidenceAtom(
                analyzer="content",
                code="ANS_HOWTO",
                severity="medium" if a2 == 0 else "info",
                message="HowTo/steps present" if a2 else "No HowTo/steps found",
                data={"pass": a2},
                provenance=provenance,
            ),
            EvidenceAtom(
                analyzer="content",
                code="ANS_QUESTION_HEADINGS",
                severity="medium" if a3 == 0 else "info",
                message=f"Question headings count={q_total}",
                data={"pass": a3, "count": q_total},
                provenance=provenance,
            ),
            EvidenceAtom(
                analyzer="content",
                code="ANS_FAQ_DENSITY",
                severity="low" if a4 < 1 else "info",
                message=f"FAQ density={faq_density:.2f}",
                data={"pass": a4, "density": faq_density},
                provenance=provenance,
            ),
        ]
    )

    # Homepage-specific answer-first evidence already included; keep home pointer for recs
    home = homepage(pages)
    if home and home.id not in {ps.page_id for ps in page_scores}:
        pass

    rows = persist_evidence(session, job_id, atoms)
    content_breakdown = {
        "page_scores": [
            {"url": ps.url, "score": ps.score, "checks": ps.checks} for ps in page_scores
        ],
        "mean": content_score,
    }
    answerability_breakdown = {
        "checks": {k: {"pass": checks_a[k], "weight": a_weights[k]} for k in a_weights},
        "definition_share": def_share,
        "faq_density": faq_density,
        "question_headings": q_total,
    }
    return ContentResult(
        content_score=content_score,
        answerability_score=answerability,
        page_scores=page_scores,
        content_breakdown=content_breakdown,
        answerability_breakdown=answerability_breakdown,
        evidence_ids=[r.id for r in rows],
        checks_a=checks_a,
    )
