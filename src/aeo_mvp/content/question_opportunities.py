"""AEO question opportunity analysis — structured opportunities per page.

Produces ~10 high-value questions with answerability, validated evidence,
weakness, recommendation, grounding_status, and optional proposed_change via
``grounded_synth``. Hooks into the existing content-optimization pipeline
(no parallel AEO pipeline).

LLM path: optional structured JSON parse + validate. Deterministic analysis
is the default so Gradio always receives a payload without paid draft APIs.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from aeo_mvp.analyzers.base import parse_html, visible_text
from aeo_mvp.content.gaps import _iter_queries, page_coverage_status
from aeo_mvp.content.grounded_synth import (
    evidence_quote_in_article,
    synthesize_proposed_change,
    validate_evidence_list,
    ws_canonical,
)
from aeo_mvp.content.models import ContentGapReport, PageIntelligence

QUESTION_ANALYSIS_VERSION = "question-opportunity-v1"
QUESTION_ANALYSIS_METHODOLOGY = (
    "question-opportunity-v1+deterministic+grounded_synth;"
    "evidence WS-canonical validated against article text;"
    "no invented facts"
)
TARGET_QUESTION_COUNT = 10

Answerability = Literal["strong", "weak", "missing"]
Importance = Literal["high", "medium", "low"]
GroundingStatus = Literal[
    "SAFE_TO_GENERATE",
    "REQUIRES_NEW_INFORMATION",
    "REJECTED_UNGROUNDED",
]

_WS_RE = re.compile(r"\s+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#-]{1,}", re.I)
_STOP = frozenset(
    {
        "the", "and", "for", "with", "from", "this", "that", "your", "our",
        "into", "about", "using", "have", "will", "are", "was", "were",
        "been", "being", "their", "they", "them", "what", "when", "where",
        "which", "while", "how", "who", "why", "a", "an", "of", "to", "in",
        "on", "at", "by", "or", "as", "is", "it", "be", "vs", "versus",
        "can", "do", "does", "did", "an",
    }
)
_Q_HEAD_RE = re.compile(r"^(who|what|when|where|why|how)\b", re.I)


@dataclass
class QuestionOpportunity:
    question: str
    importance: Importance = "medium"
    answerability: Answerability = "missing"
    evidence: list[str] = field(default_factory=list)
    evidence_location: str | None = None
    weakness: str = ""
    recommendation: str = ""
    grounding_status: GroundingStatus = "REQUIRES_NEW_INFORMATION"
    proposed_change: str | None = None
    related_query_ids: list[str] = field(default_factory=list)
    related_search_observations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "importance": self.importance,
            "answerability": self.answerability,
            "evidence": list(self.evidence),
            "evidence_location": self.evidence_location,
            "weakness": self.weakness,
            "recommendation": self.recommendation,
            "grounding_status": self.grounding_status,
            "proposed_change": self.proposed_change,
            "related_query_ids": list(self.related_query_ids),
            "related_search_observations": [
                dict(x) for x in self.related_search_observations
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuestionOpportunity":
        ans = str(data.get("answerability") or "missing")
        if ans not in ("strong", "weak", "missing"):
            ans = "missing"
        imp = str(data.get("importance") or "medium")
        if imp not in ("high", "medium", "low"):
            imp = "medium"
        gs = str(data.get("grounding_status") or "REQUIRES_NEW_INFORMATION")
        if gs not in (
            "SAFE_TO_GENERATE",
            "REQUIRES_NEW_INFORMATION",
            "REJECTED_UNGROUNDED",
        ):
            gs = "REQUIRES_NEW_INFORMATION"
        return cls(
            question=str(data.get("question") or "").strip(),
            importance=imp,  # type: ignore[arg-type]
            answerability=ans,  # type: ignore[arg-type]
            evidence=[str(e) for e in (data.get("evidence") or []) if str(e).strip()],
            evidence_location=(
                str(data["evidence_location"])
                if data.get("evidence_location") is not None
                else None
            ),
            weakness=str(data.get("weakness") or ""),
            recommendation=str(data.get("recommendation") or ""),
            grounding_status=gs,  # type: ignore[arg-type]
            proposed_change=(
                str(data["proposed_change"])
                if data.get("proposed_change") is not None
                else None
            ),
            related_query_ids=[
                str(x) for x in (data.get("related_query_ids") or []) if x
            ],
            related_search_observations=[
                dict(x)
                for x in (data.get("related_search_observations") or [])
                if isinstance(x, dict)
            ],
        )


@dataclass
class QuestionOpportunityAnalysis:
    page_url: str = ""
    page_title: str | None = None
    questions: list[QuestionOpportunity] = field(default_factory=list)
    methodology: str = QUESTION_ANALYSIS_METHODOLOGY
    model: str | None = None
    provider: str | None = None
    generated_at: str = ""
    analysis_version: str = QUESTION_ANALYSIS_VERSION
    warnings: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | unavailable | empty

    def summary_counts(self) -> dict[str, int]:
        strong = sum(1 for q in self.questions if q.answerability == "strong")
        weak = sum(1 for q in self.questions if q.answerability == "weak")
        missing = sum(1 for q in self.questions if q.answerability == "missing")
        return {
            "total": len(self.questions),
            "strong": strong,
            "need_improvement": weak,
            "require_new_info": missing,
        }

    def to_dict(self) -> dict[str, Any]:
        counts = self.summary_counts()
        return {
            "page_url": self.page_url,
            "page_title": self.page_title,
            "questions": [q.to_dict() for q in self.questions],
            "methodology": self.methodology,
            "model": self.model,
            "provider": self.provider,
            "generated_at": self.generated_at,
            "analysis_version": self.analysis_version,
            "warnings": list(self.warnings),
            "status": self.status,
            "summary": counts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "QuestionOpportunityAnalysis":
        if not isinstance(data, dict):
            return cls(status="unavailable")
        qs = [
            QuestionOpportunity.from_dict(q)
            for q in (data.get("questions") or [])
            if isinstance(q, dict) and str(q.get("question") or "").strip()
        ]
        return cls(
            page_url=str(data.get("page_url") or ""),
            page_title=data.get("page_title"),
            questions=qs,
            methodology=str(
                data.get("methodology") or QUESTION_ANALYSIS_METHODOLOGY
            ),
            model=data.get("model"),
            provider=data.get("provider"),
            generated_at=str(data.get("generated_at") or ""),
            analysis_version=str(
                data.get("analysis_version") or QUESTION_ANALYSIS_VERSION
            ),
            warnings=list(data.get("warnings") or []),
            status=str(data.get("status") or "ok"),
        )


def extract_article_text(
    *,
    html: str | None = None,
    source_markdown: str | None = None,
    page: PageIntelligence | None = None,
) -> str:
    """Build article corpus for evidence validation (Markdown preferred)."""
    parts: list[str] = []
    if source_markdown and str(source_markdown).strip():
        parts.append(str(source_markdown))
    if html and str(html).strip():
        try:
            parts.append(visible_text(parse_html(html)))
        except Exception:  # noqa: BLE001 — fail soft; other sources remain
            parts.append(re.sub(r"<[^>]+>", " ", html))
    if page is not None:
        parts.extend(
            [
                page.title or "",
                page.meta_description or "",
                page.h1 or "",
                " ".join(h.text for h in page.headings),
                " ".join(
                    (b.snippet or "") for b in (page.answer_blocks or [])
                ),
                " ".join(
                    (u.passage_preview or u.heading or "")
                    for u in (page.answer_units or [])
                ),
            ]
        )
    return _WS_RE.sub(" ", "\n".join(p for p in parts if p)).strip()


def _tokens(text: str) -> set[str]:
    return {
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if len(t) > 2 and t.lower() not in _STOP
    }


def classify_answerability(
    *,
    coverage: str | None,
    evidence: list[str],
    question: str,
    article_text: str,
) -> Answerability:
    """Map coverage + evidence quality → strong|weak|missing."""
    kept, _ = validate_evidence_list(evidence, article_text)
    if coverage == "full" and kept:
        # Prefer strong when phrase/token overlap is high and evidence is long.
        total_ev = sum(len(e.split()) for e in kept)
        q_toks = _tokens(question)
        hit = sum(1 for t in q_toks if t in ws_canonical(article_text))
        ratio = hit / max(len(q_toks), 1)
        if total_ev >= 18 and ratio >= 0.55:
            return "strong"
        return "weak"
    if coverage in ("partial", "thin") and kept:
        return "weak"
    if kept and coverage in ("full", "partial", "thin", None):
        return "weak" if sum(len(e.split()) for e in kept) >= 12 else "missing"
    return "missing"


def _best_evidence_quotes(
    question: str, article_text: str, *, limit: int = 2
) -> tuple[list[str], str | None]:
    """Pick verbatim sentences from article that best overlap the question."""
    text = (article_text or "").strip()
    if not text:
        return [], None
    q_toks = _tokens(question)
    if not q_toks:
        return [], None

    candidates: list[tuple[float, str, str]] = []
    # Prefer paragraph-ish chunks then sentences.
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    pool: list[tuple[str, str]] = []
    for i, para in enumerate(paras):
        loc = f"paragraph:{i + 1}"
        if len(para.split()) >= 8:
            pool.append((para, loc))
        for sent in _SENT_SPLIT.split(para):
            sent = sent.strip()
            if len(sent.split()) >= 8:
                pool.append((sent, loc))

    seen: set[str] = set()
    for chunk, loc in pool:
        key = ws_canonical(chunk)
        if key in seen or len(key) < 12:
            continue
        seen.add(key)
        c_toks = _tokens(chunk)
        if not c_toks:
            continue
        overlap = len(q_toks & c_toks)
        if overlap == 0:
            continue
        score = overlap / max(len(q_toks), 1) + min(len(chunk.split()), 40) / 80.0
        # Cap quote length for UI.
        quote = chunk if len(chunk) <= 420 else chunk[:417].rsplit(" ", 1)[0] + "…"
        # Truncated quotes must still validate — prefer shorter exact sentence.
        if not evidence_quote_in_article(quote.rstrip("…"), text) and "…" in quote:
            continue
        if evidence_quote_in_article(quote, text) or evidence_quote_in_article(
            quote.rstrip("…"), text
        ):
            candidates.append((score, quote.rstrip("…"), loc))

    candidates.sort(key=lambda x: (-x[0], -len(x[1])))
    out: list[str] = []
    loc_out: str | None = None
    for _score, quote, loc in candidates:
        if quote in out:
            continue
        out.append(quote)
        if loc_out is None:
            loc_out = loc
        if len(out) >= limit:
            break
    return out, loc_out


def _weakness_and_recommendation(
    answerability: Answerability, question: str
) -> tuple[str, str]:
    if answerability == "strong":
        return (
            "Answer is present but may not be packaged as a scannable Q&A unit.",
            "Surface the existing answer as an explicit FAQ or answer-first block "
            f"for: {question}",
        )
    if answerability == "weak":
        return (
            "Partial or thin coverage — answer engines may under-extract this question.",
            "Expand the grounded passage into a direct answer-first paragraph "
            f"addressing: {question}",
        )
    return (
        "No sufficient on-page answer found for this question.",
        "Author must add new on-page facts before a safe proposed change can be generated "
        f"for: {question}",
    )


def _importance_for(coverage: str | None, answerability: Answerability) -> Importance:
    if coverage in ("absent", "mismatched") or answerability == "missing":
        return "high"
    if coverage in ("thin", "partial") or answerability == "weak":
        return "medium"
    return "low"


def _normalize_question(text: str) -> str:
    q = _WS_RE.sub(" ", (text or "").strip())
    if not q:
        return ""
    if not q.endswith("?"):
        q = q.rstrip(".") + "?"
    if q[0].islower():
        q = q[0].upper() + q[1:]
    return q


def _dedupe_key(question: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()


def _derived_topic_questions(page: PageIntelligence) -> list[str]:
    """Derive high-value AEO questions from title / H1 / H2 — not trivial dupes."""
    topic = (
        (page.h1 or page.title or "").strip()
        or (page.primary_topic or {}).get("value")
        or (page.topics[0] if page.topics else "")
    )
    topic = _WS_RE.sub(" ", str(topic)).strip()
    if not topic:
        return []
    # Strip series prefixes like "Agents Zero to Hero #1: …"
    short = re.sub(r"^[^:]+:\s*", "", topic).strip() or topic
    # Prefer a compact series label when present.
    series = re.match(r"^(Agents Zero to Hero\s*#?\d+)", topic, re.I)
    label = series.group(1) if series else short
    out = [
        f"What is {label}?",
        f"How does {label} work?",
        f"Why does {label} matter?",
        f"How do I get started with {label}?",
        f"What are the key steps in {short}?",
        f"What problems does {short} solve?",
        f"Who should use {short}?",
        f"What tools are involved in {short}?",
        f"What are common pitfalls with {short}?",
        f"How is {short} different from frameworks?",
    ]
    for h in page.headings:
        if h.level not in (2, 3):
            continue
        ht = (h.text or "").strip()
        if not ht or ht.endswith("?"):
            continue
        if len(ht.split()) < 2 or len(ht.split()) > 14:
            continue
        if _Q_HEAD_RE.match(ht):
            out.append(_normalize_question(ht))
        else:
            out.append(f"What should I know about {ht}?")
    for outline in page.heading_outline or []:
        ht = str(outline).strip()
        if ht and not ht.endswith("?") and 2 <= len(ht.split()) <= 14:
            out.append(f"What should I know about {ht}?")
    return out


def _candidate_questions(
    page: PageIntelligence,
    queryset: Any,
) -> list[dict[str, Any]]:
    """Collect ranked question candidates from queryset + on-page signals."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(
        question: str,
        *,
        query_id: str | None = None,
        coverage: str | None = None,
        source: str = "derived",
    ) -> None:
        q = _normalize_question(question)
        key = _dedupe_key(q)
        if not q or len(key) < 8 or key in seen:
            return
        # Drop near-dupes (shared prefix of tokens).
        for existing in list(seen):
            a, b = set(existing.split()), set(key.split())
            if a and b and len(a & b) / max(len(a | b), 1) >= 0.85:
                return
        seen.add(key)
        candidates.append(
            {
                "question": q,
                "query_id": query_id,
                "coverage": coverage,
                "source": source,
            }
        )

    # 1) Queryset members (prefer weak coverage).
    coverage_rank = {
        "absent": 0,
        "mismatched": 1,
        "thin": 2,
        "unknown": 3,
        "partial": 4,
        "full": 5,
    }
    qrows: list[tuple[int, dict[str, Any]]] = []
    for q in _iter_queries(queryset):
        text = str(q.get("text") or "").strip()
        if not text:
            continue
        qid = str(q.get("query_id") or q.get("id") or "")
        status, _matched = page_coverage_status(
            text,
            page,
            topic=q.get("topic"),
            entity=q.get("entity"),
            intent=q.get("intent"),
        )
        qrows.append(
            (
                coverage_rank.get(status, 9),
                {
                    "question": text,
                    "query_id": qid or None,
                    "coverage": status,
                    "source": "queryset",
                },
            )
        )
    qrows.sort(key=lambda x: (x[0], x[1]["question"].lower()))
    for _rank, row in qrows:
        _add(
            row["question"],
            query_id=row.get("query_id"),
            coverage=row.get("coverage"),
            source="queryset",
        )

    # 2) On-page FAQ / question headings.
    for qh in page.faq_coverage.get("question_headings") or []:
        _add(str(qh), coverage="partial", source="on_page_faq")
    for h in page.headings:
        if (h.text or "").strip().endswith("?") or _Q_HEAD_RE.match(h.text or ""):
            _add(h.text, coverage="partial", source="heading")

    # 3) Derived topic questions to reach ~10.
    for dq in _derived_topic_questions(page):
        status, _ = page_coverage_status(dq, page)
        _add(dq, coverage=status, source="derived")

    return candidates


def _obs_for_query(
    query_id: str | None,
    visibility_observations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not query_id or not visibility_observations:
        return []
    out: list[dict[str, Any]] = []
    for obs in visibility_observations:
        oid = str(obs.get("prompt_id") or obs.get("query_id") or "")
        if oid != query_id:
            continue
        slim: dict[str, Any] = {
            "query_id": oid,
            "detected_mention": bool(obs.get("detected_mention")),
            "detected_citation": bool(obs.get("detected_citation")),
            "provenance": obs.get("provenance"),
        }
        # Attach retrieval-issued search queries when present (measurement only).
        if obs.get("search_queries") is not None:
            slim["search_queries"] = obs.get("search_queries")
        if obs.get("query"):
            slim["query"] = obs.get("query")
        out.append(slim)
    return out


def parse_llm_question_json(raw: str | dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    """Parse LLM structured JSON into raw question dicts.

    Raises ``ValueError`` on malformed / non-object payload.
    """
    if isinstance(raw, (dict, list)):
        data: Any = raw
    else:
        text = (raw or "").strip()
        if not text:
            raise ValueError("empty_llm_json")
        # Strip optional markdown fences.
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed_llm_json:{exc}") from exc

    if isinstance(data, dict):
        items = data.get("questions")
        if items is None and "question" in data:
            items = [data]
        if not isinstance(items, list):
            raise ValueError("llm_json_missing_questions_array")
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("llm_json_not_object_or_array")

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("llm_question_not_object")
        q = str(item.get("question") or "").strip()
        if not q:
            raise ValueError("llm_question_empty")
        out.append(item)
    if not out:
        raise ValueError("llm_questions_empty")
    return out


def validate_and_ground_llm_items(
    items: list[dict[str, Any]],
    *,
    article_text: str,
) -> tuple[list[QuestionOpportunity], list[str]]:
    """Validate LLM items: evidence must be in article; reject invented proposed_change."""
    warnings: list[str] = []
    results: list[QuestionOpportunity] = []
    for item in items:
        q = _normalize_question(str(item.get("question") or ""))
        raw_ev = item.get("evidence") or []
        if isinstance(raw_ev, str):
            raw_ev = [raw_ev]
        evidence = [str(e).strip() for e in raw_ev if str(e).strip()]
        kept, rejected = validate_evidence_list(evidence, article_text)
        if rejected:
            warnings.append(f"llm_evidence_rejected:{q[:40]}")
        coverage = item.get("page_coverage") or item.get("coverage")
        ans_raw = str(item.get("answerability") or "").lower()
        if ans_raw in ("strong", "weak", "missing"):
            # Still downgrade if evidence fails validation.
            if ans_raw != "missing" and not kept:
                ans: Answerability = "missing"
            else:
                ans = ans_raw  # type: ignore[assignment]
        else:
            ans = classify_answerability(
                coverage=str(coverage) if coverage else None,
                evidence=kept,
                question=q,
                article_text=article_text,
            )
        weakness = str(item.get("weakness") or "")
        recommendation = str(item.get("recommendation") or "")
        if not weakness or not recommendation:
            w2, r2 = _weakness_and_recommendation(ans, q)
            weakness = weakness or w2
            recommendation = recommendation or r2

        proposed_in = item.get("proposed_change")
        proposed: str | None = None
        grounding: GroundingStatus
        if ans == "missing":
            grounding = "REQUIRES_NEW_INFORMATION"
            proposed = None
        else:
            synth, grounding, synth_warn = synthesize_proposed_change(
                question=q,
                evidence=kept,
                article_text=article_text,
                answerability=ans,
            )
            warnings.extend(synth_warn)
            # Never accept LLM proposed_change that invents content — only grounded_synth.
            if proposed_in and synth is None:
                warnings.append(f"llm_proposed_change_rejected:{q[:40]}")
            proposed = synth

        loc = item.get("evidence_location")
        results.append(
            QuestionOpportunity(
                question=q,
                importance=_importance_for(
                    str(coverage) if coverage else None, ans
                ),
                answerability=ans,
                evidence=kept,
                evidence_location=str(loc) if loc else None,
                weakness=weakness,
                recommendation=recommendation,
                grounding_status=grounding,
                proposed_change=proposed,
                related_query_ids=[
                    str(x) for x in (item.get("related_query_ids") or []) if x
                ],
            )
        )
    return results, warnings


def build_question_opportunity_analysis(
    page: PageIntelligence,
    gap_report: ContentGapReport | None = None,
    *,
    article_text: str = "",
    queryset: Any = None,
    visibility_observations: list[dict[str, Any]] | None = None,
    llm_json: str | dict[str, Any] | list[Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    target_count: int = TARGET_QUESTION_COUNT,
) -> QuestionOpportunityAnalysis:
    """Build ~10 question opportunities for a page (deterministic + optional LLM)."""
    _ = gap_report  # reserved for future gap-id linking; coverage comes from page/queryset
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    warnings: list[str] = []
    text = (article_text or "").strip()
    if not text:
        text = extract_article_text(page=page)
    if not text:
        warnings.append("empty_article_text")

    questions: list[QuestionOpportunity] = []

    if llm_json is not None:
        try:
            items = parse_llm_question_json(llm_json)
            grounded, w = validate_and_ground_llm_items(items, article_text=text)
            warnings.extend(w)
            questions.extend(grounded)
            provider = provider or "openai_compatible"
        except ValueError as exc:
            warnings.append(str(exc))

    if len(questions) < target_count:
        for cand in _candidate_questions(page, queryset):
            if len(questions) >= target_count:
                break
            q = cand["question"]
            if any(_dedupe_key(q) == _dedupe_key(x.question) for x in questions):
                continue
            coverage = cand.get("coverage")
            evidence, loc = _best_evidence_quotes(q, text)
            ans = classify_answerability(
                coverage=coverage,
                evidence=evidence,
                question=q,
                article_text=text,
            )
            weakness, recommendation = _weakness_and_recommendation(ans, q)
            proposed, grounding, synth_warn = synthesize_proposed_change(
                question=q,
                evidence=evidence,
                article_text=text,
                answerability=ans,
            )
            warnings.extend(synth_warn)
            qid = cand.get("query_id")
            questions.append(
                QuestionOpportunity(
                    question=q,
                    importance=_importance_for(coverage, ans),
                    answerability=ans,
                    evidence=evidence,
                    evidence_location=loc,
                    weakness=weakness,
                    recommendation=recommendation,
                    grounding_status=grounding,
                    proposed_change=proposed,
                    related_query_ids=[qid] if qid else [],
                    related_search_observations=_obs_for_query(
                        qid, visibility_observations
                    ),
                )
            )

    status = "ok" if questions else "empty"
    return QuestionOpportunityAnalysis(
        page_url=page.url or "",
        page_title=page.title,
        questions=questions[:target_count],
        methodology=QUESTION_ANALYSIS_METHODOLOGY,
        model=model,
        provider=provider or "deterministic",
        generated_at=now,
        analysis_version=QUESTION_ANALYSIS_VERSION,
        warnings=warnings,
        status=status,
    )


# --- Copy-text builders (plain useful text for clipboard) ---


def copy_text_questions(analysis: QuestionOpportunityAnalysis | dict[str, Any]) -> str:
    a = (
        analysis
        if isinstance(analysis, QuestionOpportunityAnalysis)
        else QuestionOpportunityAnalysis.from_dict(analysis)
    )
    lines = [q.question for q in a.questions if q.question]
    return "\n".join(lines)


def copy_text_opportunities(
    analysis: QuestionOpportunityAnalysis | dict[str, Any],
) -> str:
    a = (
        analysis
        if isinstance(analysis, QuestionOpportunityAnalysis)
        else QuestionOpportunityAnalysis.from_dict(analysis)
    )
    blocks: list[str] = []
    for q in a.questions:
        if q.answerability == "strong":
            continue
        blocks.append(
            "\n".join(
                [
                    f"Question: {q.question}",
                    f"Answerability: {q.answerability}",
                    f"Weakness: {q.weakness}",
                    f"Recommendation: {q.recommendation}",
                    f"Grounding: {q.grounding_status}",
                ]
            )
        )
    return "\n\n".join(blocks)


def copy_text_recommended_changes(
    analysis: QuestionOpportunityAnalysis | dict[str, Any],
) -> str:
    a = (
        analysis
        if isinstance(analysis, QuestionOpportunityAnalysis)
        else QuestionOpportunityAnalysis.from_dict(analysis)
    )
    blocks: list[str] = []
    for q in a.questions:
        if q.grounding_status != "SAFE_TO_GENERATE" or not q.proposed_change:
            continue
        blocks.append(f"Question: {q.question}\n{q.proposed_change.strip()}")
    return "\n\n".join(blocks)


def copy_text_one_question(q: QuestionOpportunity | dict[str, Any]) -> str:
    item = q if isinstance(q, QuestionOpportunity) else QuestionOpportunity.from_dict(q)
    parts = [
        f"Question: {item.question}",
        f"Answerability: {item.answerability}",
        f"Importance: {item.importance}",
        f"Evidence: {'; '.join(item.evidence) if item.evidence else '(none)'}",
        f"Evidence location: {item.evidence_location or '(none)'}",
        f"Weakness: {item.weakness}",
        f"Recommendation: {item.recommendation}",
        f"Grounding: {item.grounding_status}",
        f"Proposed change:\n{item.proposed_change or '(none — requires new information)'}",
    ]
    if item.related_query_ids:
        parts.append(f"Related query ids: {', '.join(item.related_query_ids)}")
    if item.related_search_observations:
        parts.append(
            "Related search signals: "
            + json.dumps(item.related_search_observations, ensure_ascii=True)
        )
    return "\n".join(parts)


def analysis_to_markdown(analysis: QuestionOpportunityAnalysis | dict[str, Any]) -> str:
    """Full in-page Markdown for Gradio (all fields visible; no 'View details')."""
    a = (
        analysis
        if isinstance(analysis, QuestionOpportunityAnalysis)
        else QuestionOpportunityAnalysis.from_dict(analysis)
    )
    if a.status == "unavailable":
        return (
            "### AEO QUESTIONS & OPPORTUNITIES\n\n"
            "**AEO question analysis unavailable.** "
            "The rest of this page report remains valid.\n"
        )
    if not a.questions:
        return (
            "### AEO QUESTIONS & OPPORTUNITIES\n\n"
            "_No question opportunities generated for this page._\n"
        )
    counts = a.summary_counts()
    lines = [
        "### AEO QUESTIONS & OPPORTUNITIES",
        "",
        (
            f"**{counts['total']} analyzed;** "
            f"{counts['strong']} strong; "
            f"{counts['need_improvement']} need improvement; "
            f"{counts['require_new_info']} require new info."
        ),
        "",
        (
            f"_Provider: {a.provider or 'deterministic'} · "
            f"Model: {a.model or 'n/a'} · "
            f"Version: {a.analysis_version} · "
            f"Generated: {a.generated_at or 'n/a'}_"
        ),
        "",
    ]
    for i, q in enumerate(a.questions, start=1):
        lines.append(f"#### {i}. {q.question}")
        lines.append("")
        lines.append(f"- **Answerability:** `{q.answerability}`")
        lines.append(f"- **Importance:** `{q.importance}`")
        lines.append(f"- **Grounding:** `{q.grounding_status}`")
        if q.evidence:
            lines.append("- **Evidence:**")
            for ev in q.evidence:
                lines.append(f"  > {ev}")
        else:
            lines.append("- **Evidence:** _(none validated against article text)_")
        lines.append(
            f"- **Evidence location:** {q.evidence_location or '_(not located)_'}"
        )
        lines.append(f"- **Weakness:** {q.weakness}")
        lines.append(f"- **Recommendation:** {q.recommendation}")
        if q.proposed_change:
            lines.append("- **Proposed change:**")
            lines.append("")
            lines.append("```markdown")
            lines.append(q.proposed_change.rstrip())
            lines.append("```")
        else:
            lines.append(
                "- **Proposed change:** _(none — "
                f"{q.grounding_status.lower().replace('_', ' ')})_"
            )
        if q.related_query_ids:
            lines.append(
                f"- **Related query ids:** {', '.join(q.related_query_ids)}"
            )
        if q.related_search_observations:
            lines.append("- **Related search signal (visibility measurement):**")
            for obs in q.related_search_observations:
                mention = obs.get("detected_mention")
                cite = obs.get("detected_citation")
                lines.append(
                    f"  - query_id=`{obs.get('query_id')}` · "
                    f"mention={mention} · citation={cite}"
                )
        lines.append("")
    return "\n".join(lines)
