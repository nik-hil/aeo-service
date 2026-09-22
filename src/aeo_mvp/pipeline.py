"""Hashnode Markdown AEO pipeline — product flow is intentional and obvious."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aeo_mvp.article import Article, load_hashnode_markdown
from aeo_mvp.llm import llm_used, reset_execution_flags, retrieval_used
from aeo_mvp.queries import QuerySet, discover_queries
from aeo_mvp.recommendations import (
    Opportunity,
    Recommendation,
    analyze_opportunities,
    apply_recommendations,
    generate_recommendations,
)
from aeo_mvp.visibility import VisibilityReport, measure_visibility


@dataclass
class AEOReport:
    article: Article
    queries: QuerySet
    visibility: VisibilityReport
    opportunities: list[Opportunity]
    recommendations: list[Recommendation]
    current_markdown: str
    recommended_markdown: str
    diff: str
    llm_used: bool = False
    retrieval_used: bool = False
    auto_publish: bool = False  # always False — PoC never publishes

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.article.title,
            "source_path": self.article.source_path,
            "section_headings": self.article.section_headings,
            "queries_selected": self.queries.texts,
            "queries_candidate_count": len(self.queries.candidates),
            "visibility": self.visibility.to_dict(),
            "opportunities": [o.to_dict() for o in self.opportunities],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "llm_used": self.llm_used,
            "retrieval_used": self.retrieval_used,
            "auto_publish": self.auto_publish,
            "diff_preview": self.diff[:4000],
        }


def _unified_diff(current: str, recommended: str, fromfile: str = "CURRENT.md", tofile: str = "RECOMMENDED.md") -> str:
    return "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            recommended.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )


def report(
    article: Article,
    queries: QuerySet,
    visibility: VisibilityReport,
    opportunities: list[Opportunity],
    recommendations: list[Recommendation],
    *,
    llm_flag: bool,
    retrieval_flag: bool,
) -> AEOReport:
    current = article.markdown
    recommended = apply_recommendations(current, recommendations)
    return AEOReport(
        article=article,
        queries=queries,
        visibility=visibility,
        opportunities=opportunities,
        recommendations=recommendations,
        current_markdown=current,
        recommended_markdown=recommended,
        diff=_unified_diff(current, recommended),
        llm_used=llm_flag,
        retrieval_used=retrieval_flag,
        auto_publish=False,
    )


def run_pipeline(
    path: str | Path | None = None,
    *,
    text: str | None = None,
    target_domain: str | None = None,
    brand_tokens: list[str] | None = None,
    dry_run: bool = False,
    write_artifacts_dir: str | Path | None = None,
) -> AEOReport:
    """Hashnode Markdown → understanding → queries → visibility → opportunities → recs → report.

    Never auto-publishes to Hashnode/CMS.
    """
    reset_execution_flags()

    article = load_hashnode_markdown(
        path,
        text=text,
        target_domain=target_domain,
        brand_tokens=brand_tokens,
    )
    queries = discover_queries(article)
    visibility = measure_visibility(article, queries, dry_run=dry_run)
    opportunities = analyze_opportunities(article, queries, visibility)
    recommended = generate_recommendations(article, opportunities)
    result = report(
        article,
        queries,
        visibility,
        opportunities,
        recommended,
        llm_flag=llm_used(),
        retrieval_flag=retrieval_used(),
    )

    if write_artifacts_dir is not None:
        out = Path(write_artifacts_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "CURRENT.md").write_text(result.current_markdown, encoding="utf-8")
        (out / "RECOMMENDED.md").write_text(
            result.recommended_markdown, encoding="utf-8"
        )
        (out / "DIFF.patch").write_text(result.diff, encoding="utf-8")

    return result
