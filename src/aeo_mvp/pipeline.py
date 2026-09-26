"""Hashnode Markdown AEO pipeline — LLM owns semantics; Python owns plumbing."""

from __future__ import annotations

import difflib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aeo_mvp.accuracy import AccuracyReport, evaluate_accuracy
from aeo_mvp.article import Article, load_hashnode_markdown
from aeo_mvp.competitors import Competitor, parse_competitors
from aeo_mvp.config import get_settings
from aeo_mvp.evaluation import QualityEvaluation, evaluate_quality
from aeo_mvp.llm import LLMClient, llm_used, reset_execution_flags, retrieval_used
from aeo_mvp.prompt_set import PromptSet, resolve_prompt_set
from aeo_mvp.queries import QuerySet, discover_queries
from aeo_mvp.recommendations import RecommendationBundle, generate_recommendations
from aeo_mvp.summary import build_summary_markdown
from aeo_mvp.visibility import VisibilityReport, measure_visibility
from aeo_mvp.visibility_md import build_visibility_markdown


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
    visibility_markdown: str = ""
    accuracy: AccuracyReport | None = None
    prompt_set_version: str | None = None
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
            "prompt_set_version": self.prompt_set_version,
            "questions": [
                {
                    "question": q.text,
                    "importance": q.importance,
                    "reason": q.reason,
                    "article_topics_or_evidence": q.article_topics_or_evidence,
                    "source": q.source,
                    "kind": getattr(q, "kind", "general"),
                    "prompt_id": getattr(q, "prompt_id", None),
                }
                for q in self.queries.selected
            ],
            "queries_selected": self.queries.texts,
            "queries_candidate_count": len(self.queries.candidates),
            "query_quality_notes": self.queries.quality_notes,
            "visibility": self.visibility.to_dict(),
            "accuracy": self.accuracy.to_dict() if self.accuracy else None,
            "opportunities": [o.to_dict() for o in self.recommendations.opportunities],
            "recommendations": self.recommendations.to_dict(),
            "quality_eval": self.quality_eval.to_dict() if self.quality_eval else None,
            "llm_used": self.llm_used,
            "retrieval_used": self.retrieval_used,
            "auto_publish": self.auto_publish,
            "diff_preview": self.diff[:4000],
            "summary_preview": (self.summary_markdown or "")[:4000],
            "visibility_preview": (self.visibility_markdown or "")[:4000],
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


def _resolve_competitors(
    competitors: list[Competitor] | list[Any] | str | None,
    competitors_file: str | Path | None,
) -> list[Competitor]:
    if (
        isinstance(competitors, list)
        and competitors
        and all(isinstance(c, Competitor) for c in competitors)
    ):
        return list(competitors)  # type: ignore[arg-type]
    if isinstance(competitors, list):
        return parse_competitors(competitors, competitors_file=competitors_file)
    return parse_competitors(competitors, competitors_file=competitors_file)


def run_pipeline(
    path: str | Path | None = None,
    *,
    text: str | None = None,
    target_domain: str | None = None,
    brand_tokens: list[str] | None = None,
    dry_run: bool = False,
    skip_quality_eval: bool = False,
    skip_accuracy: bool = False,
    write_artifacts_dir: str | Path | None = None,
    client: LLMClient | None = None,
    prompts_file: str | Path | None = None,
    prompts_text: str | None = None,
    competitors: list[Competitor] | list[Any] | str | None = None,
    competitors_file: str | Path | None = None,
) -> AEOReport:
    """Load → questions (LLM or frozen) → visibility → accuracy → recs → eval → artifacts.

    ``dry_run`` skips paid web_search only. Frozen prompts skip LLM rediscovery.
    Never auto-publishes.
    """
    reset_execution_flags()
    settings = get_settings()
    llm = client or LLMClient()

    competitor_list = _resolve_competitors(competitors, competitors_file)

    prompt_set: PromptSet | None = resolve_prompt_set(
        prompts_file=prompts_file,
        prompts_text=prompts_text,
    )

    _pipeline_log("pipeline: load article")
    article = load_hashnode_markdown(
        path,
        text=text,
        target_domain=target_domain,
        brand_tokens=brand_tokens,
    )

    if prompt_set is not None:
        _pipeline_log(
            f"pipeline: frozen prompt set v{prompt_set.version} "
            f"({len(prompt_set.prompts)} prompts; skip LLM rediscovery)"
        )
        queries = prompt_set.to_queryset()
        prompt_set_version = prompt_set.version
    else:
        _pipeline_log("pipeline: questions (LLM)")
        queries = discover_queries(article, client=llm)
        prompt_set_version = None

    if dry_run:
        _pipeline_log("pipeline: visibility (dry — skip paid web_search)")
    else:
        _pipeline_log("pipeline: visibility (live web_search)")
    visibility = measure_visibility(
        article,
        queries,
        client=llm,
        dry_run=dry_run,
        competitors=competitor_list,
    )

    accuracy: AccuracyReport | None
    if skip_accuracy:
        _pipeline_log("pipeline: accuracy skipped")
        accuracy = AccuracyReport(
            notes="Accuracy pass skipped.",
            model=getattr(llm, "model", "") or "",
        )
    else:
        if dry_run or not visibility.observations:
            _pipeline_log("pipeline: accuracy (no OBSERVED answers)")
        else:
            _pipeline_log("pipeline: brand-fact / accuracy (LLM over OBSERVED)")
        accuracy = evaluate_accuracy(article, visibility, queries, client=llm)

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
        accuracy=accuracy,
        prompt_set_version=prompt_set_version,
        llm_used=llm_used(),
        retrieval_used=retrieval_used(),
        model=getattr(llm, "model", None) or settings.llm_model,
        auto_publish=False,
    )
    result.summary_markdown = build_summary_markdown(result)
    result.visibility_markdown = build_visibility_markdown(result)

    if write_artifacts_dir is not None:
        out = Path(write_artifacts_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "CURRENT.md").write_text(result.current_markdown, encoding="utf-8")
        (out / "RECOMMENDED.md").write_text(
            result.recommended_markdown, encoding="utf-8"
        )
        (out / "DIFF.patch").write_text(result.diff, encoding="utf-8")
        (out / "SUMMARY.md").write_text(result.summary_markdown, encoding="utf-8")
        (out / "VISIBILITY.md").write_text(
            result.visibility_markdown, encoding="utf-8"
        )
        (out / "report.json").write_text(
            json.dumps(result.to_dict(), indent=2),
            encoding="utf-8",
        )
        _pipeline_log(f"pipeline: wrote artifacts → {out}")

    _pipeline_log("pipeline: finished")
    return result
