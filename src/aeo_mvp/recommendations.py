"""LLM full-document AEO recommendations + deterministic Markdown validation.

Python validates headings, evidence quotes, structure, anti-intro-concentration,
and the applied-change contract (opportunity ↔ RECOMMENDED section edits) —
no Direct-answer templates, no semantic scoring.
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
_FRONT_MATTER_RE = re.compile(r"^---\s*\n[\s\S]*?\n---\s*(?:\n|$)", re.M)


class SupportsRespondJSON(Protocol):
    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096) -> Any: ...

    @property
    def model(self) -> str: ...


@dataclass
class Opportunity:
    question: str
    gap: str
    target_heading: str
    recommended_change: str
    evidence_quote: str
    answerability: Answerability = "missing"
    source: Literal["llm_generated"] = "llm_generated"

    # Back-compat alias used by older Gradio/tests.
    @property
    def problem(self) -> str:
        return self.gap

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "gap": self.gap,
            "target_heading": self.target_heading,
            "recommended_change": self.recommended_change,
            "evidence_quote": self.evidence_quote,
            "answerability": self.answerability,
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
    """True when quote appears in article after whitespace normalization."""
    q = _ws_canonical(quote)
    if len(q) < 12:
        return False
    return q in _ws_canonical(article_text)


def _heading_exists(article: Article, heading: str) -> bool:
    return find_section(article.sections, heading) is not None


def _exact_heading_match(article: Article, heading: str) -> str | None:
    """Return canonical heading text if an exact (case-insensitive) match exists."""
    want = (heading or "").strip().lower()
    if not want:
        return None
    for s in article.sections:
        if s.heading.lower() == want:
            return s.heading
    return None


def _count_direct_answer_labels(markdown: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sec in parse_sections(markdown):
        n = len(_DIRECT_ANSWER_RE.findall(sec.body or ""))
        if n:
            counts[sec.heading] = n
    return counts


def _section_order(markdown: str) -> list[str]:
    return [s.heading for s in parse_sections(markdown)]


def _reject_frontmatter_or_rules(markdown: str) -> None:
    text = markdown or ""
    stripped = text.lstrip()
    if stripped.startswith("---"):
        raise LLMError(
            "recommended_markdown must not start with YAML/frontmatter or --- rules"
        )
    if _FRONT_MATTER_RE.match(stripped):
        raise LLMError("recommended_markdown must not include YAML frontmatter")
    if re.search(r"(?:^|\n)---\s*$", text.rstrip()):
        raise LLMError(
            "recommended_markdown must not end with --- (no trailing rules/frontmatter)"
        )


def _intro_heading(article: Article) -> str | None:
    """First content heading used as 'intro' for concentration checks (H1 if present)."""
    if not article.sections:
        return None
    h1 = next((s for s in article.sections if s.level == 1), None)
    return h1.heading if h1 else article.sections[0].heading


def _body_for_heading(markdown: str, heading: str) -> str | None:
    want = (heading or "").strip().lower()
    for sec in parse_sections(markdown):
        if sec.heading.lower() == want:
            return sec.body
    return None


def _substantive_body_change(before: str | None, after: str | None) -> bool:
    """True when section bodies differ beyond whitespace/Markdown normalization."""
    if before is None or after is None:
        return False
    return _ws_canonical(before) != _ws_canonical(after)


def validate_recommended_markdown(
    original: str,
    recommended: str,
    *,
    article: Article,
    opportunities: list[Opportunity],
) -> list[str]:
    """Deterministic safety checks. Returns warnings; raises LLMError on hard failures.

    Bidirectional applied-change contract:
    - Every opportunity's ``target_heading`` body must change in RECOMMENDED vs CURRENT.
    - Every substantive section body change in RECOMMENDED must have ≥1 opportunity
      targeting that heading. Whitespace-only normalization is not substantive.
    """
    warnings: list[str] = []
    if not (recommended or "").strip():
        raise LLMError("recommended_markdown is empty")

    _reject_frontmatter_or_rules(recommended)

    orig_title = extract_title(original)
    new_title = extract_title(recommended)
    if orig_title and new_title and _ws_canonical(orig_title) != _ws_canonical(new_title):
        raise LLMError(
            f"Title must be preserved (original={orig_title!r}, recommended={new_title!r})"
        )

    orig_secs = parse_sections(original)
    new_secs = parse_sections(recommended)
    orig_heads = [s.heading for s in orig_secs]
    new_heads = [s.heading for s in new_secs]
    orig_set = set(orig_heads)
    new_set = set(new_heads)
    missing = orig_set - new_set
    if missing:
        raise LLMError(f"Major sections deleted in recommended Markdown: {sorted(missing)}")

    # Preserve relative order of headings that existed in CURRENT.
    orig_order = [h for h in orig_heads]
    new_order_filtered = [h for h in new_heads if h in orig_set]
    # Map case-insensitive
    orig_lower = [h.lower() for h in orig_order]
    new_lower = [h.lower() for h in new_order_filtered]
    # Every original heading should appear in new in the same order (subsequence).
    it = iter(new_lower)
    for h in orig_lower:
        for n in it:
            if n == h:
                break
        else:
            raise LLMError(
                f"Section order not preserved for existing heading {h!r} "
                "(headings must keep CURRENT relative order)"
            )

    extra = new_set - orig_set
    if extra:
        # Disallow arbitrary new major sections (level <= 2 heuristics: any new ATX heading).
        raise LLMError(
            f"New major headings not allowed in recommended Markdown: {sorted(extra)}"
        )

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
        if not opp.target_heading or not _exact_heading_match(article, opp.target_heading):
            raise LLMError(f"target_heading does not exist: {opp.target_heading!r}")
        if not opp.evidence_quote or not evidence_quote_in_article(
            opp.evidence_quote, article_text
        ):
            raise LLMError(
                f"evidence_quote must be a verbatim substring of CURRENT for question "
                f"{opp.question!r}"
            )
        if not (opp.gap or "").strip():
            raise LLMError(f"gap required for opportunity {opp.question!r}")
        if not (opp.recommended_change or "").strip():
            raise LLMError(f"recommended_change required for opportunity {opp.question!r}")

    # Applied-change invariant (forward): every opportunity must land as a real
    # section body edit in RECOMMENDED. Whitespace-only diffs are not applied edits.
    intro = _intro_heading(article)
    claimed: list[str] = []
    unchanged_targets: list[str] = []
    for opp in opportunities:
        canon = _exact_heading_match(article, opp.target_heading)
        if not canon:
            continue
        claimed.append(canon)
        before = _body_for_heading(original, canon)
        after = _body_for_heading(recommended, canon)
        if not _substantive_body_change(before, after):
            unchanged_targets.append(canon)
    if unchanged_targets:
        unique_unchanged = list(dict.fromkeys(unchanged_targets))
        raise LLMError(
            "Opportunities must correspond to applied RECOMMENDED edits; "
            f"target section body unchanged for: {unique_unchanged}. "
            "Omit opportunities that were considered but not applied."
        )

    # Applied-change invariant (reverse): every substantive section body change
    # must be attributable to ≥1 opportunity targeting that heading.
    claimed_lower = {h.lower() for h in claimed}
    unattributed: list[str] = []
    for sec in orig_secs:
        before = sec.body
        after = _body_for_heading(recommended, sec.heading)
        if not _substantive_body_change(before, after):
            continue
        if sec.heading.lower() not in claimed_lower:
            unattributed.append(sec.heading)
    if unattributed:
        raise LLMError(
            "RECOMMENDED has substantive section edits without matching opportunities "
            f"for: {unattributed}. Emit an opportunity for each applied section change, "
            "or leave that section unchanged."
        )

    # If ≥3 opportunities exist and ALL target only the intro/H1 while article has
    # multiple H2+ sections, reject artificial intro concentration.
    h2_plus = [s.heading for s in article.sections if s.level >= 2]
    if len(opportunities) >= 3 and h2_plus and intro:
        only_intro = all(
            ( _exact_heading_match(article, o.target_heading) or "" ).lower()
            == intro.lower()
            for o in opportunities
        )
        if only_intro:
            raise LLMError(
                "Opportunities are concentrated on the introduction/H1 only; "
                "question→section principle requires distributing edits to relevant "
                "existing sections when the article has multiple sections."
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
        heading_raw = str(item.get("target_heading") or "").strip()
        heading = _exact_heading_match(article, heading_raw)
        if not heading:
            # Must be an existing CURRENT heading — drop invalid rows.
            continue
        quote = str(item.get("evidence_quote") or "").strip()
        if not quote or not evidence_quote_in_article(quote, article_text):
            # Meaningful opportunities require a grounded verbatim quote.
            continue
        gap = str(item.get("gap") or item.get("problem") or "").strip()
        change = str(
            item.get("recommended_change") or item.get("proposed_change") or ""
        ).strip()
        if not gap or not change:
            continue
        out.append(
            Opportunity(
                question=q,
                gap=gap,
                target_heading=heading,
                recommended_change=change,
                evidence_quote=quote,
                answerability=ans,  # type: ignore[arg-type]
                source="llm_generated",
            )
        )
    return out


_RECOMMEND_PROMPT = """You are the AEO recommendation engine for a Hashnode Markdown article.

You optimize the FULL document for answer-engine visibility. Python will only
validate structure and grounding — you own all semantic decisions.

INPUTS:
1) CURRENT ARTICLE — the complete Hashnode Markdown (read and reason about ALL of it)
2) SELECTED QUESTIONS — realistic user questions this article should answer
3) OBSERVED VISIBILITY — DigitalOcean Responses + web_search API observations
   (answers, citations, source URLs). These are API observations, NOT consumer
   ChatGPT / Gemini / Perplexity UI rankings.

CRITICAL PRODUCT RULES:
1. FULL-DOCUMENT OPTIMIZATION — Inspect the entire article before deciding changes.
   Do NOT optimize only the introduction. The introduction is NOT the default place
   for improvements.
2. QUESTION → SECTION PRINCIPLE — For EACH selected question:
   - Does the article answer it well?
   - If not, what is the gap (missing/weak/unclear)?
   - Find the EXISTING section (H1–H6 heading already in CURRENT) where the answer
     logically belongs.
   - Apply the smallest useful grounded edit IN THAT SECTION.
   Prefer improving that section over moving information into the intro.
   Different questions SHOULD touch different sections when evidence supports it.
   Do NOT artificially concentrate changes near the beginning.
3. GROUNDING — Use only the CURRENT article text plus the supplied visibility
   observations. Do NOT invent facts, statistics, citations, sources, examples,
   implementation details, or fake search claims.
4. MINIMALITY — Prefer improving existing sentences/paragraphs or short clarifications.
   Rewrite only when needed for a real question-level gap. No keyword stuffing or
   artificial SEO.
5. AEO AIM — Help an AI system identify concepts, answer the selected questions from
   the article, connect answers to the correct section, and distinguish related concepts.
6. RECOMMENDED_MARKDOWN must be the COMPLETE improved article Markdown ONLY:
   - Preserve title, H1–H6 structure and relative order, narrative, voice, important examples
   - Preserve code blocks unless a grounded correction is required
   - No YAML/frontmatter, no leading/trailing `---`, no meta commentary about the
     optimization inside the article
   - No arbitrary new major sections; no deleting major sections; no moving content
     between unrelated sections
   - Do NOT use "**Direct answer:**" template blocks

APPLIED-CHANGE CONTRACT (critical — Python enforces this):
Opportunities are records of changes you ACTUALLY applied in recommended_markdown,
NOT ideas you considered. Bidirectional consistency is required:
- If you emit an opportunity → you MUST edit that target_heading's section body in
  recommended_markdown (the applied recommended_change must land there).
- If you edit a section body in recommended_markdown → you MUST emit a matching
  opportunity with that exact existing target_heading.
- If you consider a gap but do NOT edit that section → do NOT emit that opportunity.
- If there are no substantive edits → return opportunities: [] (do not invent rows).
- Minor whitespace / Markdown normalization alone is NOT a substantive edit and
  must not produce opportunity records.

FOR EACH QUESTION whose gap you actually fix in recommended_markdown, emit:
- question
- gap (what is missing/weak for answer engines)
- target_heading (MUST be an existing H1–H6 heading from CURRENT, exact text)
- recommended_change (description of the edit you applied in that section)
- evidence_quote (MUST be copied verbatim from CURRENT and support the change)
- answerability: strong | weak | missing

Then produce recommended_markdown (full article) and change_explanations (short bullets).

SELF-CHECK BEFORE RETURNING (must all be true):
- I inspected the whole article, not just the intro
- I considered the logically relevant EXISTING section for each question
- Improvements are located where the information belongs
- Changes are NOT intro-concentrated
- Multiple sections are touched when questions span topics
- Every opportunity maps to an applied section edit in recommended_markdown
- Every substantive recommended_markdown section edit has a matching opportunity
- Every evidence_quote is verbatim from CURRENT
- Structure, order, and voice are preserved
- No unnecessary rewriting; no invented facts
- No opportunity rows for gaps I did not actually edit

Respond with JSON ONLY:
{{
  "opportunities": [
    {{
      "question": "...",
      "gap": "...",
      "target_heading": "...",
      "recommended_change": "...",
      "evidence_quote": "...",
      "answerability": "strong|weak|missing"
    }}
  ],
  "recommended_markdown": "... complete markdown article only ...",
  "change_explanations": ["...", "..."]
}}

CURRENT ARTICLE:
<<<ARTICLE
{article}
ARTICLE>>>

SELECTED QUESTIONS (LLM-GENERATED):
{questions}

OBSERVED VISIBILITY (API — not consumer ChatGPT/Gemini UI):
{visibility}
"""


def generate_recommendations(
    article: Article,
    queries: QuerySet | list[Query] | list[str],
    visibility: VisibilityReport | None = None,
    *,
    client: SupportsRespondJSON | None = None,
) -> RecommendationBundle:
    """LLM full-document opportunities + complete recommended Markdown."""
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

    # Help the model with an explicit heading inventory (plumbing, not semantics).
    heading_inventory = [
        {"level": s.level, "heading": s.heading} for s in article.sections
    ]

    vis_payload: dict[str, Any]
    if visibility is None:
        vis_payload = {"observations": [], "notes": "no visibility run"}
    else:
        vis_payload = visibility.to_dict()

    prompt = _RECOMMEND_PROMPT.format(
        article=article.markdown,
        questions=json.dumps(
            {"questions": q_payload, "existing_headings": heading_inventory},
            indent=2,
        ),
        visibility=json.dumps(vis_payload, indent=2)[:60000],
    )
    raw = llm.respond_json(prompt, max_output_tokens=8192)
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
