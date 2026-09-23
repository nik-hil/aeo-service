"""LLM quality evaluation of questions + recommended Markdown.

Python only parses structured pass/fail — no SEO scorecard heuristics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from aeo_mvp.article import Article
from aeo_mvp.llm import LLMClient, LLMError
from aeo_mvp.queries import QuerySet
from aeo_mvp.recommendations import RecommendationBundle


class SupportsRespondJSON(Protocol):
    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096) -> Any: ...

    @property
    def model(self) -> str: ...


@dataclass
class QualityEvaluation:
    passed: bool
    summary: str = ""
    question_feedback: list[str] = field(default_factory=list)
    recommendation_feedback: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    unnecessary_changes: list[str] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)
    model: str = ""
    source: str = "llm_generated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "summary": self.summary,
            "question_feedback": list(self.question_feedback),
            "recommendation_feedback": list(self.recommendation_feedback),
            "unsupported_claims": list(self.unsupported_claims),
            "unnecessary_changes": list(self.unnecessary_changes),
            "explanations": list(self.explanations),
            "model": self.model,
            "source": self.source,
        }


_EVAL_PROMPT = """You are reviewing an Answer Engine Optimization draft.

Judge:
1) Questions — realism, relevance, distinctness, specificity (fail awkward heading transforms)
2) Whether recommended Markdown answers the questions better than the original
3) Grounding — no invented facts/stats/citations
4) Unnecessary changes
5) Human readability
6) Unsupported claims

Return JSON ONLY:
{{
  "passed": true,
  "summary": "one paragraph",
  "question_feedback": ["..."],
  "recommendation_feedback": ["..."],
  "unsupported_claims": ["..."],
  "unnecessary_changes": ["..."],
  "explanations": ["pass/fail rationale bullets"]
}}

ORIGINAL ARTICLE:
---
{article}
---

QUESTIONS (LLM-GENERATED):
{questions}

RECOMMENDED MARKDOWN:
---
{recommended}
---

STRUCTURED CHANGES / OPPORTUNITIES:
{changes}
"""


def evaluate_quality(
    article: Article,
    queries: QuerySet,
    bundle: RecommendationBundle,
    *,
    client: SupportsRespondJSON | None = None,
) -> QualityEvaluation:
    llm: SupportsRespondJSON = client or LLMClient()
    if client is None and isinstance(llm, LLMClient) and not llm.available():
        raise LLMError("AEO_LLM_API_KEY required for quality evaluation")

    raw = llm.respond_json(
        _EVAL_PROMPT.format(
            article=article.markdown,
            questions=json.dumps(queries.texts, indent=2),
            recommended=bundle.recommended_markdown[:50000],
            changes=json.dumps(
                {
                    "opportunities": [o.to_dict() for o in bundle.opportunities],
                    "change_explanations": bundle.change_explanations,
                },
                indent=2,
            )[:20000],
        ),
        max_output_tokens=4096,
    )
    if not isinstance(raw, dict):
        raise LLMError("Quality evaluation must return a JSON object")

    passed = bool(raw.get("passed"))
    def _str_list(key: str) -> list[str]:
        vals = raw.get(key) or []
        if not isinstance(vals, list):
            return []
        return [str(x).strip() for x in vals if str(x).strip()]

    return QualityEvaluation(
        passed=passed,
        summary=str(raw.get("summary") or "").strip(),
        question_feedback=_str_list("question_feedback"),
        recommendation_feedback=_str_list("recommendation_feedback"),
        unsupported_claims=_str_list("unsupported_claims"),
        unnecessary_changes=_str_list("unnecessary_changes"),
        explanations=_str_list("explanations"),
        model=getattr(llm, "model", "") or "",
        source="llm_generated",
    )
