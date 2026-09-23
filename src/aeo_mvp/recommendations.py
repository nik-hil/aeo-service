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

You are an EDITOR of the existing article — not a researcher writing new content.
Python will only validate structure, grounding, and the applied-change contract —
you own all semantic decisions. The heading inventory in the questions payload is
navigation ONLY; section meaning and gap judgment stay with you.

CORE RULE (mandatory — diagnosis vs content):
Search evidence tells you WHAT may be weak. CURRENT.md tells you WHAT you are
allowed to say.
- OBSERVED VISIBILITY diagnoses retrieval/extractability/clarity problems.
- CURRENT ARTICLE is the only content source of truth for new prose.
Do NOT import search facts, citations, snippets, external pages, or model/general
knowledge into RECOMMENDED merely because they seem relevant.

GOAL — SUFFICIENT ANSWERABILITY WITH THE SMALLEST USEFUL CHANGE:
Optimize for making each selected question sufficiently answerable from the
article, using the smallest useful CURRENT-grounded edit, then STOP. Do NOT
optimize for max/min edits, article length, opportunity count, diff size, or
keyword count. Correct output may have 0, 2, 5, or more meaningful changes.

Reject restatements, paraphrases, visible-code narration, polish, and any content
that is not authorized by CURRENT. Still emit opportunities for genuine CLARITY /
INFORMATION gaps when the fix is grounded in CURRENT (relationships, distinctions,
constraints, consequences, limitations, dependencies, ambiguity, missing element
elsewhere in CURRENT). Do NOT become too conservative: partial answers can still
need real improvement — but only with CURRENT-authorized content.

SOURCE PRIORITY (do not confuse these roles):
1) CURRENT ARTICLE = content source of truth. New prose must be grounded in
   information already in CURRENT (including connecting facts that appear in
   different sections, making implicit relationships explicit, clarifying
   ambiguity, improving extractability/precision/placement).
2) SELECTED QUESTIONS = optimization targets (what readers ask; whether CURRENT
   answers sufficiently).
3) OBSERVED VISIBILITY = diagnostic evidence only (weak retrieval, hard-to-extract
   concepts, wording/relationship clarity). Do NOT treat retrieved answers as
   source material. Do NOT import search facts into RECOMMENDED merely because
   they are relevant.

MAY CHANGE (when grounded in CURRENT):
Make existing relationships/distinctions/limitations/constraints explicit; connect
facts already in CURRENT; resolve ambiguity; improve extractability/precision/
placement; rewrite existing prose when needed for answerability; combine info from
different parts of CURRENT into a clearer local explanation.

MUST NOT (forbidden content sources):
Add information that exists only in DigitalOcean/search answers, external pages,
citations, snippets, model/general knowledge, assumptions, or inferred repo
behavior not stated in CURRENT. No external provider/implementation details,
stats, new facts/examples/citations/URLs/technologies/claims, or researched
explanations the author did not provide — unless already in CURRENT.

INPUTS:
1) CURRENT ARTICLE — the complete Hashnode Markdown (read and reason about ALL of it)
2) SELECTED QUESTIONS — realistic user questions this article should answer
3) OBSERVED VISIBILITY — DigitalOcean Responses + web_search API observations
   (answers, citations, source URLs). Diagnostic only — NOT consumer ChatGPT /
   Gemini / Perplexity UI rankings, and NOT a content source.

CRITICAL PRODUCT RULES:
1. FULL-DOCUMENT OPTIMIZATION — Inspect the entire article before deciding changes.
   Do NOT optimize only the introduction. The introduction is NOT the default place
   for improvements. Do NOT dump improvements into the intro.
2. QUESTION → SECTION PRINCIPLE — Place every accepted change in the EXISTING section
   (H1–H6 already in CURRENT) that owns the concept. Prefer that section over the intro.
   Different questions SHOULD touch different sections when evidence supports it.
   Do NOT artificially concentrate changes near the beginning.
3. GROUNDING RULE (content authorization): For every proposed addition ask:
   Can I point to supporting info inside CURRENT.md?
   - YES → allowed (as clarification / connection / local rewrite of CURRENT).
   - NO → do not add. Search finding it does NOT authorize it.
   Visibility may identify that a gap exists; it never authorizes external content.
4. MINIMALITY — Prefer improve sentence → expand paragraph → one short paragraph →
   larger rewrite only if needed. Maximize answerability per meaningful change,
   not Markdown churn. No keyword stuffing or artificial SEO.
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
   - No external citations / URLs / SEO filler imported from search
7. NOT EVERY QUESTION NEEDS A CHANGE — NO GAP questions get NO opportunity and NO filler.
   Do not force every selected question into an opportunity.
   Do not edit merely because search has more information than the article.

REQUIRED DECISION METHOD — follow these steps for EACH selected question before
producing final JSON. Do not skip steps. Do not start writing RECOMMENDED until
steps 1–6 are done for all questions.

STEP 1 — FIND THE CURRENT ANSWER:
Read the COMPLETE CURRENT article. Locate where the question is answered (possibly
across multiple sections). Do NOT assume the introduction contains the answer.
The Python heading inventory is navigation only.

STEP 2 — WRITE AN INTERNAL ANSWER SUMMARY (CURRENT only):
Before deciding whether to edit, mentally answer the question using CURRENT only.
Ask: What would an AI have to say to answer this question correctly using only
facts supportable by CURRENT?
Compare that required answer with what CURRENT actually supports.
This prevents edits driven only by wording similarity or by search results.

STEP 3 — IDENTIFY THE SMALLEST REAL GAP — classify as exactly one of:
- NO GAP / sufficiently: article already answers sufficiently → no opportunity, no edit.
- CLARITY GAP / partially: info exists in CURRENT but an important relationship,
  distinction, constraint, consequence, dependency, limitation, or ambiguity
  prevents a strong answer → local clarification allowed. Map answerability to "weak".
- INFORMATION GAP (elsewhere in CURRENT): important answer element is present
  somewhere else in CURRENT but not where the question needs it → local addition/
  relocation of CURRENT-authorized info allowed. Map answerability to "missing".
- INFORMATION GAP (missing entirely from CURRENT): important element is not in
  CURRENT at all → do not invent; do not create the opportunity — even if search/
  visibility mentions it.
Search may identify that a gap exists; it does not authorize external content.
Do not force every question into an opportunity.

STEP 4 — THE BEFORE / AFTER TEST (for every proposed edit):
What specific part of the answer is better after this edit? Must be concrete.
GOOD: explains why X↔Y; distinguishes X from Y; makes a limitation explicit; makes a
causal relationship clear; adds a necessary CURRENT-grounded detail; removes
ambiguity that could cause an incorrect answer.
BAD alone (reject): clearer / more descriptive / sounds better / more SEO / more
context / summarizes the code / adds search-only details.

STEP 5 — COUNTERFACTUAL TEST (primary stopping / keep-or-reject criterion):
Ask exactly: If I remove this edit, would an AI's answer become materially less
accurate, less complete, or more ambiguous?
- YES → KEEP (only if also CURRENT-authorized)
- NO → REJECT (repetition, paraphrase, narrating visible code, polish, generic
  explanation, unnecessary expansion, search-imported filler)

CALIBRATED EXAMPLES (teach these judgment standards):
1. BAD search-only import → REJECT: visibility says the repo uses OpenRouter /
   OPENROUTER_API_KEY but CURRENT does not mention OpenRouter → do not add OpenRouter
   endpoint / API-key setup prose; no opportunity. Search evidence ≠ content license.
2. GOOD missing relationship → KEEP: CURRENT has tool_call_id and appends the tool
   result but never says why the ID matters → make the association with the specific
   tool request explicit (matters with multiple calls).
3. GOOD connecting existing facts → KEEP: CURRENT separately has tool error +
   preserved history → make the causal connection explicit (failed result in
   conversation lets the model revise and retry).
4. BAD general-knowledge expansion → REJECT: expanding arbitrary Python execution
   into file/network risks (or similar) when CURRENT does not support that claim.
5. BAD visible-code narration → REJECT: code already shows append tool result and
   prose says the harness sends the result back; proposing "harness appends tool
   result so model can see it" adds no meaningful answer value.
6. BAD paraphrase → REJECT: "model decides / harness controls how" rewritten as
   "LLM makes decisions / harness controls execution" — same meaning, no opportunity.
7. GOOD important boundary → KEEP: schemas + TOOLS registry in CURRENT leave the
   model→harness→function boundary implicit; making that boundary explicit improves
   answerability.
8. BAD polish after sufficiency → STOP / REJECT second: one useful CURRENT-grounded
   clarification makes the question answerable; a second paragraph restating the
   same point is redundant — no additional opportunity for that question.

DO NOT BECOME TOO CONSERVATIVE:
Do NOT interpret this method as "only edit when absolutely no information exists."
Partial answers can require real improvement when CURRENT already contains the
needed facts. Example that still qualifies: history contains tool calls/results
but does not explain that an assistant tool-call message must remain associated
with the subsequent tool result — legitimate clarification when the selected
question depends on that AND CURRENT supports the association pattern.

STEP 6 — STOPPING RULE PER QUESTION:
1. Determine the current answer (from STEPs 1–2) using CURRENT only
2. Identify the smallest real answerability gap (STEP 3)
3. Make the smallest useful edit that passes STEPs 4–5 AND the GROUNDING RULE
4. Reconsider the question with the proposed edit in mind
5. If now sufficiently complete and unambiguous → STOP for that question
6. Do not make another edit unless a second, independent answerability gap remains
Do not keep editing because words could still be improved.
Do not edit merely because search has more information than the article.

STEP 7 — SECTION PLACEMENT:
Place every accepted change in the existing section that owns the concept
(adapt to CURRENT headings; do not invent headings):
- tool schemas → Tool schemas (or equivalent)
- execution → Implementing execute_code (or equivalent)
- tool results → Feeding the result back… (or equivalent)
- conversation state → Why the message history matters (or equivalent)
- completion → The finish tool (or equivalent)
- security → There is already a security problem (or equivalent)
Only modify the intro when missing info genuinely belongs there. Do not move content
into the intro merely for AI visibility.

STEP 8 — COMPLETE DOCUMENT CONSTRUCTION:
RECOMMENDED.md = CURRENT.md + accepted meaningful CURRENT-grounded changes only.
Do not independently rewrite the rest. Do not make extra edits while constructing
final Markdown. Do not import retrieval discoveries. Opportunities define the
allowed changes.

STEP 9 — CONSISTENCY CHECK (before final JSON):
For every substantive edit verify: selected question, exact gap, why it materially
improves the answer (BEFORE/AFTER + COUNTERFACTUAL), correct section, CURRENT-
grounded (GROUNDING RULE), not search-imported, not redundant, no additional edit
needed for that question.
Whole-article checks: contradictions with code; duplicate explanations; conflicting
descriptions of the same mechanism; unnecessary repetition; intro-heavy changes;
invented / search-only information. Do not leave two competing explanations (e.g.
completion when no tool calls vs finish tool — clarify the relationship rather than
add another paragraph). Also verify bidirectional opportunity ↔ applied-edit
consistency below.

APPLIED-CHANGE CONTRACT / OPPORTUNITY CONTRACT (critical — Python enforces this;
PR #48 unchanged):
An opportunity = a meaningful change that was actually applied.
- No idea-only opportunities; no opportunities for NO GAP / strong questions.
- No opportunities whose recommended_change requires info absent from CURRENT.
- If you emit an opportunity → you MUST edit that target_heading's section body in
  recommended_markdown (the applied recommended_change must land there).
- If you edit a section body in recommended_markdown → you MUST emit a matching
  opportunity with that exact existing target_heading.
- If you consider a gap but do NOT edit that section → do NOT emit that opportunity.
- If there are no substantive edits → return opportunities: [] (do not invent rows).
- Minor whitespace / Markdown normalization alone is NOT a substantive edit and
  must not produce opportunity records.
- evidence_quote MUST be a verbatim substring of CURRENT.

FOR EACH QUESTION whose gap you actually fix in recommended_markdown, emit:
- question
- gap (the real answerability problem — CLARITY or INFORMATION in CURRENT terms,
  not a restatement and not a search-import excuse)
- target_heading (MUST be an existing H1–H6 heading from CURRENT, exact text)
- recommended_change (description of the CURRENT-grounded edit you applied)
- evidence_quote (MUST be copied verbatim from CURRENT and support the change)
- answerability: strong | weak | missing
  (prefer weak for CLARITY GAP; missing for INFORMATION GAP grounded in CURRENT;
   NO GAP questions usually have no opportunity row)

Then produce recommended_markdown (full article) and change_explanations (short bullets
describing only material CURRENT-grounded applied edits).

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

OBSERVED VISIBILITY (API — diagnostic only; not a content source):
{visibility}
"""


MAX_RECOMMENDATION_ATTEMPTS = 3

_TRANSIENT_LLM_ERROR_MARKERS = (
    "LLM request failed",
    "LLM HTTP ",
)


def _is_transient_llm_error(exc: BaseException) -> bool:
    """True for transport/API failures with no model output to repair against."""
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    msg = str(exc)
    return any(marker in msg for marker in _TRANSIENT_LLM_ERROR_MARKERS)


def _with_repair_feedback(
    base_prompt: str,
    error: str,
    *,
    second_repair: bool,
) -> str:
    """Append targeted repair instructions; keep original CURRENT in base_prompt."""
    note = (
        "This is a second repair attempt. Fix only the latest failure below.\n\n"
        if second_repair
        else ""
    )
    # Do not use str.format on ``error`` — it may contain braces.
    return (
        f"{base_prompt.rstrip()}\n\n"
        "REPAIR FEEDBACK:\n"
        "The previous recommendation failed deterministic validation.\n\n"
        "Validator error:\n"
        f"{error}\n\n"
        f"{note}"
        "Repair this exact failure.\n"
        "Do not make unrelated changes.\n"
        "Re-evaluate the opportunity and recommended_markdown together.\n"
        "If the opportunity is not justified, remove the opportunity instead of "
        "forcing an edit.\n"
        "If the opportunity is justified, apply the corresponding meaningful edit "
        "in the correct existing section.\n"
        "Return JSON ONLY using the required schema.\n"
    )


def _bundle_from_llm_raw(
    raw: Any,
    *,
    article: Article,
    model: str,
) -> RecommendationBundle:
    """Parse + validate one recommendation JSON response against ORIGINAL CURRENT."""
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
        model=model,
        source="llm_generated",
    )


def generate_recommendations(
    article: Article,
    queries: QuerySet | list[Query] | list[str],
    visibility: VisibilityReport | None = None,
    *,
    client: SupportsRespondJSON | None = None,
) -> RecommendationBundle:
    """LLM full-document opportunities + complete recommended Markdown.

    One LLM call per attempt. On deterministic validation / JSON-schema failure,
    retry up to twice with the same base prompt plus targeted repair feedback
    containing the exact error (max 3 attempts). Transient transport/API errors
    retry the original prompt without repair feedback. Failed RECOMMENDED is never
    used as CURRENT — every attempt reasons from the original article.
    """
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

    # Base prompt always uses ORIGINAL CURRENT — never a failed RECOMMENDED.
    base_prompt = _RECOMMEND_PROMPT.format(
        article=article.markdown,
        questions=json.dumps(
            {"questions": q_payload, "existing_headings": heading_inventory},
            indent=2,
        ),
        visibility=json.dumps(vis_payload, indent=2)[:60000],
    )

    next_repair_error: str | None = None
    repairs_sent = 0
    last_error: LLMError | None = None
    model = getattr(llm, "model", "") or ""

    for attempt in range(1, MAX_RECOMMENDATION_ATTEMPTS + 1):
        if next_repair_error is None:
            prompt = base_prompt
        else:
            prompt = _with_repair_feedback(
                base_prompt,
                next_repair_error,
                second_repair=repairs_sent >= 1,
            )
            repairs_sent += 1

        try:
            raw = llm.respond_json(prompt, max_output_tokens=8192)
            return _bundle_from_llm_raw(raw, article=article, model=model)
        except LLMError as exc:
            last_error = exc
            if attempt >= MAX_RECOMMENDATION_ATTEMPTS:
                break
            if _is_transient_llm_error(exc):
                # Transport/API redraw — same original prompt, no repair block.
                next_repair_error = None
            else:
                # JSON/schema or deterministic Markdown validation — targeted repair.
                next_repair_error = str(exc)

    assert last_error is not None
    raise last_error
