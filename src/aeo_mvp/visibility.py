"""AI-search visibility via DigitalOcean Responses + server-side web_search only.

API observations ≠ consumer ChatGPT UI. ``retrieval_used`` comes from tool
evidence recorded in ``aeo_mvp.llm``, never from config alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aeo_mvp.article import Article
from aeo_mvp.llm import LLMClient, LLMError, domain_in_urls, mention_in_text
from aeo_mvp.queries import Query, QuerySet


@dataclass
class VisibilityObservation:
    query: str
    answer: str
    mentioned: bool
    cited: bool
    target_domain_in_sources: bool
    source_urls: list[str] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    had_web_search_call: bool = False
    error: str | None = None
    measures_consumer_ui: bool = False
    provenance: str = "api_observation"


@dataclass
class VisibilityReport:
    observations: list[VisibilityObservation] = field(default_factory=list)
    mention_rate: float = 0.0
    citation_rate: float = 0.0
    target_in_sources_rate: float = 0.0
    provider: str = "digitalocean_web_search"
    notes: str = (
        "DigitalOcean Inference Responses API + web_search. "
        "API observation only — does NOT measure consumer ChatGPT/Gemini/Perplexity UI."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "notes": self.notes,
            "mention_rate": self.mention_rate,
            "citation_rate": self.citation_rate,
            "target_in_sources_rate": self.target_in_sources_rate,
            "observations": [
                {
                    "query": o.query,
                    "answer": o.answer[:2000],
                    "mentioned": o.mentioned,
                    "cited": o.cited,
                    "target_domain_in_sources": o.target_domain_in_sources,
                    "source_urls": o.source_urls,
                    "citations": o.citations,
                    "search_queries": o.search_queries,
                    "had_web_search_call": o.had_web_search_call,
                    "error": o.error,
                    "measures_consumer_ui": o.measures_consumer_ui,
                    "provenance": o.provenance,
                }
                for o in self.observations
            ],
        }


def _rates(obs: list[VisibilityObservation]) -> tuple[float, float, float]:
    ok = [o for o in obs if o.error is None]
    if not ok:
        return 0.0, 0.0, 0.0
    n = len(ok)
    return (
        sum(1 for o in ok if o.mentioned) / n,
        sum(1 for o in ok if o.cited) / n,
        sum(1 for o in ok if o.target_domain_in_sources) / n,
    )


def measure_visibility(
    article: Article,
    queries: QuerySet | list[Query] | list[str],
    *,
    client: LLMClient | None = None,
    dry_run: bool = False,
) -> VisibilityReport:
    """Run AI-search visibility probes for each selected query.

    When ``dry_run`` or no API key, returns empty observations (no fabricated
    success). Callers may inject a mock ``client`` in tests.
    """
    if isinstance(queries, QuerySet):
        q_list = [q.text for q in queries.selected]
    else:
        q_list = [q if isinstance(q, str) else q.text for q in queries]

    llm = client or LLMClient()
    observations: list[VisibilityObservation] = []

    if dry_run or not llm.available():
        return VisibilityReport(
            observations=[],
            notes=(
                "Skipped live visibility: AEO_LLM_API_KEY missing or dry_run=True. "
                "No fabricated AI-search results."
            ),
        )

    brand = list(article.brand_tokens)
    if article.title:
        brand.append(article.title.split(":")[0].strip())
    domain = article.target_domain

    for q in q_list:
        prompt = (
            f"{q}\n\n"
            f"Article under evaluation: {article.title}\n"
            + (f"Target site/domain: {domain}\n" if domain else "")
            + "Search the web and cite sources with URLs when available."
        )
        try:
            result = llm.respond(prompt, web_search=True, require_web_search=True)
        except LLMError as exc:
            observations.append(
                VisibilityObservation(
                    query=q,
                    answer="",
                    mentioned=False,
                    cited=False,
                    target_domain_in_sources=False,
                    error=str(exc),
                )
            )
            continue

        citation_urls = [
            c["url"]
            for c in result.citations
            if isinstance(c.get("url"), str)
        ]
        in_sources = domain_in_urls(domain, result.source_urls) or domain_in_urls(
            domain, citation_urls
        )
        cited = domain_in_urls(domain, citation_urls)
        mentioned = mention_in_text(result.text, brand) or in_sources

        observations.append(
            VisibilityObservation(
                query=q,
                answer=result.text,
                mentioned=mentioned,
                cited=cited,
                target_domain_in_sources=in_sources,
                source_urls=list(result.source_urls),
                citations=list(result.citations),
                search_queries=list(result.search_queries),
                had_web_search_call=result.had_web_search_call,
            )
        )

    mention_rate, citation_rate, tis_rate = _rates(observations)
    return VisibilityReport(
        observations=observations,
        mention_rate=mention_rate,
        citation_rate=citation_rate,
        target_in_sources_rate=tis_rate,
    )
