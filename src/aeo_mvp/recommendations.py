"""Opportunity analysis and grounded recommendations.

Flow per opportunity (from #46 lessons, reimplemented simply):
  question → answerability → evidence → gap → recommended change

Constraints (from #45 lessons, reimplemented simply):
  - evidence quotes must appear in the article
  - no H1 mega-section targeting for body edits
  - do not pile all ops onto one section
  - no cite_miss / covered_gap_ids hidden coupling
  - distinguish observed (visibility) vs generated (recommendations)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from aeo_mvp.article import Article
from aeo_mvp.markdown import append_under_heading, find_section, parse_sections
from aeo_mvp.queries import Query, QuerySet
from aeo_mvp.visibility import VisibilityObservation, VisibilityReport

Answerability = Literal["strong", "weak", "missing"]

_WS_RE = re.compile(r"\s+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]{2,}", re.I)
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "your",
        "our",
        "into",
        "about",
        "using",
        "have",
        "will",
        "are",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "how",
        "who",
        "why",
        "can",
        "does",
        "did",
        "not",
        "but",
        "you",
        "all",
        "any",
        "more",
        "than",
        "also",
        "just",
        "like",
        "such",
        "only",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "or",
        "as",
        "is",
        "it",
        "be",
    }
)


def _ws_canonical(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip().lower())


def evidence_quote_in_article(quote: str, article_text: str) -> bool:
    """True when quote is a real substring (whitespace-canonical)."""
    q = _ws_canonical(quote)
    if len(q) < 12:
        return False
    return q in _ws_canonical(article_text)


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for m in _TOKEN_RE.finditer(text or ""):
        t = m.group(0).lower().strip(".-")
        if len(t) >= 3 and t not in _STOP:
            out.add(t)
    return out


def _sentences(text: str) -> list[str]:
    parts = _SENT_SPLIT.split((text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def _best_evidence(article: Article, question: str) -> tuple[str | None, str | None]:
    """Return (evidence_quote, target_heading) grounded in article text."""
    q_tokens = _tokens(question)
    if not q_tokens:
        return None, None

    # Prefer non-H1 sections so we never default everything to the mega H1 body.
    candidates = [s for s in article.sections if s.level >= 2] or list(article.sections)
    best: tuple[float, str, str] | None = None  # score, quote, heading

    for sec in candidates:
        for sent in _sentences(sec.body):
            overlap = len(q_tokens & _tokens(sent))
            if overlap <= 0:
                continue
            score = overlap / max(1, len(q_tokens))
            # Prefer shorter grounded quotes.
            score -= min(0.2, len(sent) / 2000.0)
            if best is None or score > best[0]:
                best = (score, sent, sec.heading)

    if best is None:
        # Fall back to intro sentences but still attach a non-H1 heading if possible.
        for sent in _sentences(article.intro):
            overlap = len(q_tokens & _tokens(sent))
            if overlap <= 0:
                continue
            heading = candidates[0].heading if candidates else (
                article.sections[0].heading if article.sections else article.title
            )
            # Avoid using H1 as target when H2+ exist.
            h1 = next((s for s in article.sections if s.level == 1), None)
            if h1 and heading == h1.heading and len(article.sections) > 1:
                heading = next(
                    (s.heading for s in article.sections if s.level >= 2),
                    heading,
                )
            return sent, heading
        return None, None

    return best[1], best[2]


def _answerability(evidence: str | None, question: str) -> Answerability:
    if not evidence:
        return "missing"
    overlap = len(_tokens(question) & _tokens(evidence))
    if overlap >= 3:
        return "strong"
    if overlap >= 1:
        return "weak"
    return "missing"


@dataclass
class Opportunity:
    question: str
    answerability: Answerability
    target_heading: str
    evidence_quote: str
    problem: str
    observed_mention: bool | None = None
    observed_cited: bool | None = None
    source: Literal["observed", "generated"] = "generated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answerability": self.answerability,
            "target_heading": self.target_heading,
            "evidence_quote": self.evidence_quote,
            "problem": self.problem,
            "observed_mention": self.observed_mention,
            "observed_cited": self.observed_cited,
            "source": self.source,
        }


@dataclass
class Recommendation:
    question: str
    answerability: Answerability
    target_heading: str
    evidence_quote: str
    problem: str
    proposed_change: str
    source: Literal["observed", "generated"] = "generated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answerability": self.answerability,
            "target_heading": self.target_heading,
            "evidence_quote": self.evidence_quote,
            "problem": self.problem,
            "proposed_change": self.proposed_change,
            "source": self.source,
        }


def analyze_opportunities(
    article: Article,
    queries: QuerySet | list[Query] | list[str],
    visibility: VisibilityReport | None = None,
) -> list[Opportunity]:
    """Build opportunities from article questions + optional visibility observations."""
    if isinstance(queries, QuerySet):
        q_texts = [q.text for q in queries.selected]
        section_hint = {
            q.text: q.source_section for q in queries.selected if q.source_section
        }
    else:
        q_texts = [q if isinstance(q, str) else q.text for q in queries]
        section_hint = {}

    vis_by_q: dict[str, VisibilityObservation] = {}
    if visibility:
        for o in visibility.observations:
            vis_by_q[o.query] = o

    article_text = article.plain_text()
    opportunities: list[Opportunity] = []
    heading_counts: dict[str, int] = {}

    for q in q_texts:
        evidence, heading = _best_evidence(article, q)
        if heading is None:
            heading = section_hint.get(q) or (
                next(
                    (s.heading for s in article.sections if s.level >= 2),
                    article.sections[0].heading if article.sections else article.title,
                )
            )
        # Enforce no all-ops-on-one-section: rotate if a heading is overloaded.
        if heading_counts.get(heading, 0) >= 2:
            for s in article.sections:
                if s.level >= 2 and heading_counts.get(s.heading, 0) < 2:
                    heading = s.heading
                    break
        heading_counts[heading] = heading_counts.get(heading, 0) + 1

        # Never target H1 for body edits when H2+ sections exist (mega-section guard).
        h1 = next((s for s in article.sections if s.level == 1), None)
        if (
            h1
            and heading == h1.heading
            and any(s.level >= 2 for s in article.sections)
        ):
            alt = next(s.heading for s in article.sections if s.level >= 2)
            heading = alt
            heading_counts[heading] = heading_counts.get(heading, 0) + 1

        ans = _answerability(evidence, q)
        quote = evidence or ""
        if quote and not evidence_quote_in_article(quote, article_text):
            quote = ""
            ans = "missing"

        obs = vis_by_q.get(q)
        if ans == "strong" and (obs is None or (obs.mentioned and not obs.error)):
            problem = "Answer is present; tighten the lead sentence for extractability."
        elif ans == "weak":
            problem = (
                "Partial answer exists but lacks a direct, quotable response "
                f"to “{q.rstrip('?')}?”."
            )
        else:
            problem = (
                f"Article does not directly answer “{q.rstrip('?')}?” "
                f"under “{heading}”."
            )

        if obs and obs.error is None:
            if not obs.mentioned and not obs.target_domain_in_sources:
                problem += " AI-search observation: no mention or target domain in sources."
            elif not obs.cited:
                problem += " AI-search observation: appeared in sources but not cited."
            source: Literal["observed", "generated"] = "observed"
            observed_mention = obs.mentioned
            observed_cited = obs.cited
        else:
            source = "generated"
            observed_mention = None
            observed_cited = None

        # Skip fully strong + already cited unless we still want light polish —
        # keep weak/missing and uncited observed gaps.
        if ans == "strong" and source == "observed" and observed_cited:
            continue
        if ans == "strong" and source == "generated" and not problem.startswith("Answer"):
            continue

        opportunities.append(
            Opportunity(
                question=q,
                answerability=ans,
                target_heading=heading,
                evidence_quote=quote,
                problem=problem,
                observed_mention=observed_mention,
                observed_cited=observed_cited,
                source=source,
            )
        )

    # Prefer weak/missing first; keep a focused set.
    opportunities.sort(
        key=lambda o: (
            0 if o.answerability == "missing" else 1 if o.answerability == "weak" else 2,
            0 if o.source == "observed" else 1,
            o.question,
        )
    )
    return opportunities[:12]


def _propose_change(opp: Opportunity, article: Article) -> str:
    """Grounded, specific proposed Markdown addition — no generic SEO fluff."""
    sec = find_section(article.sections, opp.target_heading)
    topic = opp.question.rstrip("?").strip()
    if opp.evidence_quote:
        return (
            f"**Direct answer:** {opp.evidence_quote.strip()}\n\n"
            f"Expanded for the question “{topic}?”: keep the quote above as the "
            f"lead sentence under “{opp.target_heading}”, then add one concrete "
            f"example from the surrounding section"
            + (
                f" (currently ~{len(sec.body.split())} words)."
                if sec and sec.body
                else "."
            )
        )
    return (
        f"**Add a direct answer** under “{opp.target_heading}” that opens with "
        f"one sentence answering “{topic}?”, using only facts already in this "
        f"article. Do not invent statistics or citations."
    )


def _pick_heading(article: Article, preferred: str, used: dict[str, int], *, cap: int = 2) -> str | None:
    """Choose a non-H1 heading under the per-section cap, or None if exhausted."""
    h1 = next((s for s in article.sections if s.level == 1), None)
    body = [s for s in article.sections if s.level >= 2] or list(article.sections)

    def ok(h: str) -> bool:
        if h1 and h == h1.heading and any(s.level >= 2 for s in article.sections):
            return False
        return used.get(h, 0) < cap

    if preferred and ok(preferred):
        return preferred
    for s in body:
        if ok(s.heading):
            return s.heading
    return None


def generate_recommendations(
    article: Article,
    opportunities: list[Opportunity],
) -> list[Recommendation]:
    """Turn opportunities into specific grounded recommendations."""
    recs: list[Recommendation] = []
    used_headings: dict[str, int] = {}
    for opp in opportunities:
        heading = _pick_heading(article, opp.target_heading, used_headings, cap=2)
        if heading is None:
            continue
        used_headings[heading] = used_headings.get(heading, 0) + 1

        adj = Opportunity(
            question=opp.question,
            answerability=opp.answerability,
            target_heading=heading,
            evidence_quote=opp.evidence_quote,
            problem=opp.problem,
            observed_mention=opp.observed_mention,
            observed_cited=opp.observed_cited,
            source=opp.source,
        )
        recs.append(
            Recommendation(
                question=adj.question,
                answerability=adj.answerability,
                target_heading=adj.target_heading,
                evidence_quote=adj.evidence_quote,
                problem=adj.problem,
                proposed_change=_propose_change(adj, article),
                source=adj.source,
            )
        )
    return recs


def apply_recommendations(markdown: str, recommendations: list[Recommendation]) -> str:
    """Produce RECOMMENDED.md by appending grounded snippets under target headings.

    Does not auto-publish. Skips recommendations that would target H1 when H2+
    exist. Caps edits per heading to avoid dumping everything on one section.
    """
    sections = parse_sections(markdown)
    h1 = next((s for s in sections if s.level == 1), None)
    has_h2 = any(s.level >= 2 for s in sections)
    out = markdown
    per_heading: dict[str, int] = {}

    for rec in recommendations:
        heading = rec.target_heading
        if h1 and has_h2 and heading == h1.heading:
            continue
        if per_heading.get(heading, 0) >= 2:
            continue
        if find_section(parse_sections(out), heading) is None:
            continue
        snippet = rec.proposed_change.strip()
        if not snippet:
            continue
        # Apply a short lead addition derived from the proposal, not the whole essay.
        lead = snippet.split("\n\n")[0].strip()
        out = append_under_heading(out, heading, lead)
        per_heading[heading] = per_heading.get(heading, 0) + 1
    return out
