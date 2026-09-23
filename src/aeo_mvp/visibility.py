"""AI-search visibility — thin DigitalOcean web_search plumbing only.

No semantic judgment of question quality. API observation ≠ consumer ChatGPT UI.
``retrieval_used`` comes from tool evidence recorded in ``aeo_mvp.llm``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

from aeo_mvp.article import Article
from aeo_mvp.llm import LLMClient, LLMError, domain_in_urls, mention_in_text
from aeo_mvp.queries import Query, QuerySet


class SupportsRespond(Protocol):
    def available(self) -> bool: ...

    def respond(
        self,
        prompt: str,
        *,
        web_search: bool = False,
        require_web_search: bool = False,
        max_output_tokens: int = 4096,
    ) -> Any: ...

    @property
    def model(self) -> str: ...


def _normalize_page_url(url: str) -> str | None:
    """Deterministic page identity key for exact URL matching.

    - lowercase hostname
    - ignore fragments
    - normalize trailing slash (except bare root)
    - omit default http/https ports
    """
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return None
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    port = parsed.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    path = parsed.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{netloc}{path}{query}"


def target_page_in_urls(target_url: str | None, urls: list[str]) -> bool:
    """True when ``target_url`` matches any URL by exact page identity."""
    needle = _normalize_page_url(target_url) if target_url else None
    if not needle:
        return False
    for u in urls:
        if not isinstance(u, str) or not u.strip():
            continue
        if _normalize_page_url(u) == needle:
            return True
    return False


@dataclass
class VisibilityObservation:
    query: str
    answer: str
    mentioned: bool
    cited: bool
    target_domain_in_sources: bool
    target_page_in_sources: bool | None = None
    target_page_cited: bool | None = None
    source_urls: list[str] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    had_web_search_call: bool = False
    error: str | None = None
    measures_consumer_ui: bool = False
    provenance: str = "api_observation"  # OBSERVED — not LLM-generated judgment


@dataclass
class VisibilityReport:
    observations: list[VisibilityObservation] = field(default_factory=list)
    mention_rate: float = 0.0
    citation_rate: float = 0.0
    target_in_sources_rate: float = 0.0
    target_page_in_sources_rate: float = 0.0
    target_page_citation_rate: float = 0.0
    query_coverage: float = 0.0  # fraction of questions with a successful observation
    provider: str = "digitalocean_web_search"
    model: str = ""
    notes: str = (
        "OBSERVED via DigitalOcean Inference Responses API + web_search. "
        "API observation only — does NOT measure consumer ChatGPT/Gemini/Perplexity UI."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "notes": self.notes,
            "mention_rate": self.mention_rate,
            "citation_rate": self.citation_rate,
            "target_in_sources_rate": self.target_in_sources_rate,
            "target_page_in_sources_rate": self.target_page_in_sources_rate,
            "target_page_citation_rate": self.target_page_citation_rate,
            "query_coverage": self.query_coverage,
            "observations": [
                {
                    "query": o.query,
                    "answer": o.answer[:2000],
                    "mentioned": o.mentioned,
                    "cited": o.cited,
                    "target_domain_in_sources": o.target_domain_in_sources,
                    "target_page_in_sources": o.target_page_in_sources,
                    "target_page_cited": o.target_page_cited,
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


def _rates(obs: list[VisibilityObservation]) -> tuple[float, float, float, float]:
    ok = [o for o in obs if o.error is None]
    n_all = len(obs)
    if not ok:
        return 0.0, 0.0, 0.0, 0.0 if n_all else 0.0
    n = len(ok)
    return (
        sum(1 for o in ok if o.mentioned) / n,
        sum(1 for o in ok if o.cited) / n,
        sum(1 for o in ok if o.target_domain_in_sources) / n,
        n / n_all if n_all else 0.0,
    )


def _page_rates(obs: list[VisibilityObservation]) -> tuple[float, float]:
    """Rates only over observations where a target page URL was configured."""
    scoped = [
        o
        for o in obs
        if o.error is None and o.target_page_in_sources is not None
    ]
    if not scoped:
        return 0.0, 0.0
    n = len(scoped)
    return (
        sum(1 for o in scoped if o.target_page_in_sources) / n,
        sum(1 for o in scoped if o.target_page_cited) / n,
    )


def _page_flags(
    target_url: str | None,
    source_urls: list[str],
    citation_urls: list[str],
) -> tuple[bool | None, bool | None]:
    if not target_url:
        return None, None
    page_cited = target_page_in_urls(target_url, citation_urls)
    page_in_sources = page_cited or target_page_in_urls(target_url, source_urls)
    return page_in_sources, page_cited


def measure_visibility(
    article: Article,
    queries: QuerySet | list[Query] | list[str],
    *,
    client: SupportsRespond | None = None,
    dry_run: bool = False,
) -> VisibilityReport:
    """Run AI-search visibility probes for each selected query (plumbing only)."""
    if isinstance(queries, QuerySet):
        q_list = [q.text for q in queries.selected]
    else:
        q_list = [q if isinstance(q, str) else q.text for q in queries]

    llm: SupportsRespond = client or LLMClient()
    if dry_run or not llm.available():
        return VisibilityReport(
            observations=[],
            model=getattr(llm, "model", "") or "",
            notes=(
                "Skipped live visibility: dry_run=True or AEO_LLM_API_KEY missing. "
                "No fabricated AI-search results. OBSERVED metrics unavailable."
            ),
        )

    brand = list(article.brand_tokens)
    if article.title:
        brand.append(article.title.split(":")[0].strip())
    domain = article.target_domain
    target_url = article.target_url
    observations: list[VisibilityObservation] = []

    for q in q_list:
        prompt = (
            f"{q}\n\n"
            f"Article under evaluation: {article.title}\n"
            + (f"Target site/domain: {domain}\n" if domain else "")
            + "Search the web and cite sources with URLs when available."
        )
        try:
            result = llm.respond(
                prompt,
                web_search=True,
                require_web_search=True,
                max_output_tokens=2048,
            )
        except LLMError as exc:
            page_in, page_cited = _page_flags(target_url, [], [])
            observations.append(
                VisibilityObservation(
                    query=q,
                    answer="",
                    mentioned=False,
                    cited=False,
                    target_domain_in_sources=False,
                    target_page_in_sources=page_in,
                    target_page_cited=page_cited,
                    error=str(exc),
                )
            )
            continue

        citation_urls = [
            c["url"]
            for c in result.citations
            if isinstance(c.get("url"), str)
        ]
        in_sources = domain_in_urls(domain, list(result.source_urls)) or domain_in_urls(
            domain, citation_urls
        )
        cited = domain_in_urls(domain, citation_urls)
        mentioned = mention_in_text(result.text, brand) or in_sources
        page_in, page_cited = _page_flags(
            target_url, list(result.source_urls), citation_urls
        )

        observations.append(
            VisibilityObservation(
                query=q,
                answer=result.text,
                mentioned=mentioned,
                cited=cited,
                target_domain_in_sources=in_sources,
                target_page_in_sources=page_in,
                target_page_cited=page_cited,
                source_urls=list(result.source_urls),
                citations=list(result.citations),
                search_queries=list(result.search_queries),
                had_web_search_call=result.had_web_search_call,
            )
        )

    mention_rate, citation_rate, tis_rate, coverage = _rates(observations)
    page_in_rate, page_cite_rate = _page_rates(observations)
    return VisibilityReport(
        observations=observations,
        mention_rate=mention_rate,
        citation_rate=citation_rate,
        target_in_sources_rate=tis_rate,
        target_page_in_sources_rate=page_in_rate,
        target_page_citation_rate=page_cite_rate,
        query_coverage=coverage,
        model=getattr(llm, "model", "") or "",
    )
