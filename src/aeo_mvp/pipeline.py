"""Hashnode Markdown AEO pipeline — LLM owns semantics; Python owns plumbing."""

from __future__ import annotations

import difflib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aeo_mvp.article import Article, load_hashnode_markdown
from aeo_mvp.config import get_settings
from aeo_mvp.evaluation import QualityEvaluation, evaluate_quality
from aeo_mvp.llm import LLMClient, llm_used, reset_execution_flags, retrieval_used
from aeo_mvp.queries import QuerySet, discover_queries
from aeo_mvp.recommendations import RecommendationBundle, generate_recommendations
from aeo_mvp.summary import build_summary_markdown
from aeo_mvp.visibility import VisibilityReport, measure_visibility


def _pipeline_log(message: str) -> None:
    """Stage progress for CLI / Gradio terminal observers."""
    print(f"[aeo] {message}", file=sys.stdout, flush=True)


@dataclass
class AEOReport:
    article: Article
    queries: QuerySet
    visibility: VisibilityReport
    recommendations: RecommendationBundle
    quality_eval: QualityEvaluation | None
    current_markdown: str
    recommended_markdown: str
    diff: str
    summary_markdown: str = ""
    llm_used: bool = False
    retrieval_used: bool = False
    model: str = ""
    auto_publish: bool = False

    @property
    def opportunities(self):
        return self.recommendations.opportunities

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.article.title,
            "source_path": self.article.source_path,
            "section_headings": self.article.section_headings,
            "model": self.model,
            "questions": [
                {
                    "question": q.text,
                    "importance": q.importance,
                    "reason": q.reason,
                    "article_topics_or_evidence": q.article_topics_or_evidence,
                    "source": "llm_generated",
                }
                for q in self.queries.selected
            ],
            "queries_selected": self.queries.texts,
            "queries_candidate_count": len(self.queries.candidates),
            "query_quality_notes": self.queries.quality_notes,
            "visibility": self.visibility.to_dict(),
            "opportunities": [o.to_dict() for o in self.recommendations.opportunities],
            "recommendations": self.recommendations.to_dict(),
            "quality_eval": self.quality_eval.to_dict() if self.quality_eval else None,
            "llm_used": self.llm_used,
            "retrieval_used": self.retrieval_used,
            "auto_publish": self.auto_publish,
            "diff_preview": self.diff[:4000],
            "summary_preview": (self.summary_markdown or "")[:4000],
        }


def _unified_diff(
    current: str,
    recommended: str,
    fromfile: str = "CURRENT.md",
    tofile: str = "RECOMMENDED.md",
) -> str:
    return "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            recommended.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )


def run_pipeline(
    path: str | Path | None = None,
    *,
    text: str | None = None,
    target_domain: str | None = None,
    brand_tokens: list[str] | None = None,
    dry_run: bool = False,
    skip_quality_eval: bool = False,
    write_artifacts_dir: str | Path | None = None,
    client: LLMClient | None = None,
) -> AEOReport:
    """Load → LLM questions → visibility plumbing → LLM recs → LLM eval → artifacts.

    ``dry_run`` skips paid web_search only. Question discovery / recommendations /
    quality eval still require an LLM client (or injected mock).
    Never auto-publishes.
    """
    reset_execution_flags()
    settings = get_settings()
    llm = client or LLMClient()

    _pipeline_log("pipeline: load article")
    article = load_hashnode_markdown(
        path,
        text=text,
        target_domain=target_domain,
        brand_tokens=brand_tokens,
    )
    _pipeline_log("pipeline: questions (LLM)")
    queries = discover_queries(article, client=llm)
    if dry_run:
        _pipeline_log("pipeline: visibility (dry — skip paid web_search)")
    else:
        _pipeline_log("pipeline: visibility (live web_search)")
    visibility = measure_visibility(article, queries, client=llm, dry_run=dry_run)
    _pipeline_log("pipeline: recommendations (LLM)")
    bundle = generate_recommendations(article, queries, visibility, client=llm)

    quality: QualityEvaluation | None = None
    if not skip_quality_eval:
        _pipeline_log("pipeline: quality eval (LLM)")
        quality = evaluate_quality(article, queries, bundle, client=llm)
    else:
        _pipeline_log("pipeline: quality eval skipped")

    current = article.markdown
    recommended = bundle.recommended_markdown
    result = AEOReport(
        article=article,
        queries=queries,
        visibility=visibility,
        recommendations=bundle,
        quality_eval=quality,
        current_markdown=current,
        recommended_markdown=recommended,
        diff=_unified_diff(current, recommended),
        llm_used=llm_used(),
        retrieval_used=retrieval_used(),
        model=getattr(llm, "model", None) or settings.llm_model,
        auto_publish=False,
    )
    result.summary_markdown = build_summary_markdown(result)

    if write_artifacts_dir is not None:
        out = Path(write_artifacts_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "CURRENT.md").write_text(result.current_markdown, encoding="utf-8")
        (out / "RECOMMENDED.md").write_text(
            result.recommended_markdown, encoding="utf-8"
        )
        (out / "DIFF.patch").write_text(result.diff, encoding="utf-8")
        (out / "SUMMARY.md").write_text(result.summary_markdown, encoding="utf-8")
        (out / "report.json").write_text(
            json.dumps(result.to_dict(), indent=2),
            encoding="utf-8",
        )
        _pipeline_log(f"pipeline: wrote artifacts → {out}")

    _pipeline_log("pipeline: finished")
    return result
