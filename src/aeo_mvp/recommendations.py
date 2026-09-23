"""LLM opportunity analysis + full recommended Markdown + change explanations.

Python validates headings, evidence quotes, Markdown safety — no Direct-answer
templates, no heuristic section scoring.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from aeo_mvp.article import Article
from aeo_mvp.llm import LLMClient, LLMError
from aeo_mvp.markdown import extract_title, find_section, parse_sections
from aeo_mvp.queries import Query, QuerySet
from aeo_mvp.visibility import VisibilityReport

Answerability = Literal["strong", "weak", "missing"]

_WS_RE = re.compile(r"\s+")
_DIRECT_ANSWER_RE = re.compile(r"\*\*Direct answer:\*\*", re.I)


class SupportsRespondJSON(Protocol):
    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096) -> Any: ...

    @property
    def model(self) -> str: ...


@dataclass
class Opportunity:
    question: str
    answerability: Answerability
    evidence_quote: str
    target_heading: str
    problem: str
    recommended_change: str
    source: Literal["llm_generated"] = "llm_generated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answerability": self.answerability,
            "evidence_quote": self.evidence_quote,
            "target_heading": self.target_heading,
            "problem": self.problem,
            "recommended_change": self.recommended_change,
            "source": self.source,
        }


@dataclass
class RecommendationBundle:
    opportunities: list[Opportunity] = field(default_factory=list)
    recommended_markdown: str = ""
    change_explanations: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    model: str = ""
    source: str = "llm_generated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunities": [o.to_dict() for o in self.opportunities],
            "change_explanations": list(self.change_explanations),
            "validation_warnings": list(self.validation_warnings),
            "model": self.model,
            "source": self.source,
            "recommended_markdown_chars": len(self.recommended_markdown),
        }


def _ws_canonical(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip().lower())


def evidence_quote_in_article(quote: str, article_text: str) -> bool:
    q = _ws_canonical(quote)
    if len(q) < 12:
        return False
    return q in _ws_canonical(article_text)


def _heading_exists(article: Article, heading: str) -> bool:
    return find_section(article.sections, heading) is not None


def _count_direct_answer_labels(markdown: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sec in parse_sections(markdown):
        n = len(_DIRECT_ANSWER_RE.findall(sec.body or ""))
        if n:
            counts[sec.heading] = n
    return counts


def validate_recommended_markdown(
    original: str,
    recommended: str,
    *,
    article: Article,
    opportunities: list[Opportunity],
) -> list[str]:
    """Deterministic safety checks. Returns warnings; raises LLMError on hard failures."""
    warnings: list[str] = []
    if not (recommended or "").strip():
        raise LLMError("recommended_markdown is empty")

    orig_title = extract_title(original)
    new_title = extract_title(recommended)
    if orig_title and new_title and _ws_canonical(orig_title) != _ws_canonical(new_title):
        raise LLMError(
            f"Title must be preserved (original={orig_title!r}, recommended={new_title!r})"
        )

    orig_heads = {s.heading for s in parse_sections(original) if s.level >= 2}
    new_heads = {s.heading for s in parse_sections(recommended) if s.level >= 2}
    missing = orig_heads - new_heads
    if missing:
        raise LLMError(f"Major sections deleted in recommended Markdown: {sorted(missing)}")

    da = _count_direct_answer_labels(recommended)
    for heading, n in da.items():
        if n > 1:
            raise LLMError(
                f"Malformed/duplicated **Direct answer:** blocks under {heading!r} (count={n})"
            )
    if da:
        warnings.append(
            "recommended_markdown contains **Direct answer:** labels; "
            "prefer natural prose edits without that template"
        )

    article_text = article.plain_text()
    for opp in opportunities:
        if opp.target_heading and not _heading_exists(article, opp.target_heading):
            raise LLMError(f"target_heading does not exist: {opp.target_heading!r}")
        if opp.evidence_quote and not evidence_quote_in_article(
            opp.evidence_quote, article_text
        ):
            raise LLMError(
                f"evidence_quote not found in original article for question {opp.question!r}"
            )

    # Obvious duplicate consecutive paragraphs
    paras = [p.strip() for p in recommended.split("\n\n") if p.strip()]
    for i in range(1, len(paras)):
        if paras[i] == paras[i - 1] and len(paras[i]) > 40:
            raise LLMError("Obvious duplicate paragraph additions in recommended Markdown")

    return warnings


def _parse_opportunities(raw: Any, article: Article) -> list[Opportunity]:
    if isinstance(raw, dict):
        items = raw.get("opportunities") or raw.get("questions") or []
    elif isinstance(raw, list):
        items = raw
    else:
        raise LLMError("Expected opportunities array or object")

    article_text = article.plain_text()
    out: list[Opportunity] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question") or "").strip()
        if not q:
            continue
        ans = str(item.get("answerability") or "missing").strip().lower()
        if ans not in ("strong", "weak", "missing"):
            ans = "missing"
        heading = str(item.get("target_heading") or "").strip()
        if heading and not _heading_exists(article, heading):
            # LLM chose a bad heading — reject this opportunity (Python plumbing)
            continue
        quote = str(item.get("evidence_quote") or "").strip()
        if quote and not evidence_quote_in_article(quote, article_text):
            # Unsupported quote — drop quote rather than invent; mark weaker
            quote = ""
            if ans == "strong":
                ans = "weak"
        out.append(
            Opportunity(
                question=q,
                answerability=ans,  # type: ignore[arg-type]
                evidence_quote=quote,
                target_heading=heading,
                problem=str(item.get("problem") or "").strip(),
                recommended_change=str(
                    item.get("recommended_change") or item.get("proposed_change") or ""
                ).strip(),
                source="llm_generated",
            )
        )
    return out


_RECOMMEND_PROMPT = """You are an Answer Engine Optimization editor for Hashnode Markdown.

You will receive:
1) The ORIGINAL article Markdown
2) FINAL user questions (LLM-generated)
3) OBSERVED AI-search visibility results (answers, citations, URLs) — factual API observations

Tasks:
A) For each question, produce a structured opportunity:
   - question
   - answerability: strong | weak | missing
   - evidence_quote: exact substring from the ORIGINAL article (or empty if none)
   - target_heading: an EXISTING heading from the article (choose by meaning; do not invent)
   - problem: specific gap vs what answer engines need
   - recommended_change: what to change in that section (natural prose guidance)

B) Produce a COMPLETE recommended_markdown: the full article Markdown after the
   smallest useful grounded edits. Preserve meaning, tone, and structure.
   - Do NOT invent facts, statistics, citations, examples, or SEO filler.
   - Do NOT use "**Direct answer:**" template blocks.
   - Do NOT delete major sections or change the H1 title.
   - Prefer clarifying lead sentences and tightening existing claims.

C) Provide change_explanations: short bullets of what changed and why.

Respond with JSON ONLY:
{{
  "opportunities": [
    {{
      "question": "...",
      "answerability": "strong|weak|missing",
      "evidence_quote": "...",
      "target_heading": "...",
      "problem": "...",
      "recommended_change": "..."
    }}
  ],
  "recommended_markdown": "... full markdown ...",
  "change_explanations": ["...", "..."]
}}

ORIGINAL ARTICLE:
---
{article}
---

QUESTIONS (LLM-GENERATED):
{questions}

OBSERVED VISIBILITY (API — not consumer ChatGPT UI):
{visibility}
"""


def generate_recommendations(
    article: Article,
    queries: QuerySet | list[Query] | list[str],
    visibility: VisibilityReport | None = None,
    *,
    client: SupportsRespondJSON | None = None,
) -> RecommendationBundle:
    """LLM analyzes opportunities and returns full recommended Markdown."""
    llm: SupportsRespondJSON = client or LLMClient()
    if client is None and isinstance(llm, LLMClient) and not llm.available():
        raise LLMError("AEO_LLM_API_KEY required for recommendations (no template fallback)")

    if isinstance(queries, QuerySet):
        q_payload = [
            {
                "question": q.text,
                "importance": q.importance,
                "reason": q.reason,
                "article_topics_or_evidence": q.article_topics_or_evidence,
            }
            for q in queries.selected
        ]
    else:
        q_payload = [
            {"question": q if isinstance(q, str) else q.text} for q in queries
        ]

    vis_payload: dict[str, Any]
    if visibility is None:
        vis_payload = {"observations": [], "notes": "no visibility run"}
    else:
        vis_payload = visibility.to_dict()

    raw = llm.respond_json(
        _RECOMMEND_PROMPT.format(
            article=article.markdown,
            questions=json.dumps(q_payload, indent=2),
            visibility=json.dumps(vis_payload, indent=2)[:60000],
        ),
        max_output_tokens=8192,
    )
    if not isinstance(raw, dict):
        raise LLMError("Recommendations response must be a JSON object")

    opportunities = _parse_opportunities(raw, article)
    recommended = str(raw.get("recommended_markdown") or "").strip()
    if not recommended:
        raise LLMError("LLM did not return recommended_markdown")

    explanations = [
        str(x).strip()
        for x in (raw.get("change_explanations") or [])
        if str(x).strip()
    ]

    warnings = validate_recommended_markdown(
        article.markdown,
        recommended,
        article=article,
        opportunities=opportunities,
    )

    return RecommendationBundle(
        opportunities=opportunities,
        recommended_markdown=recommended,
        change_explanations=explanations,
        validation_warnings=warnings,
        model=getattr(llm, "model", "") or "",
        source="llm_generated",
    )
