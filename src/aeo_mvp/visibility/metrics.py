"""Mention/citation rules and aggregate rate formulas (llm-mention-v1 / ai-search-vis-v1)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from aeo_mvp.domains import registrable_domain
from aeo_mvp.target_site import TargetSiteIdentity, resolve_target_site_identity, target_match
from aeo_mvp.visibility.base import VisibilityObservation

URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+", re.I)
EXTRACTION_METHODOLOGY = (
    "llm-mention-v1:mention-rule-v1+url-mention-rule-v1+domain-match-v1"
)
AI_SEARCH_EXTRACTION_METHODOLOGY = (
    "ai-search-vis-v1:do-web-search+url-citation-v1+mention-rule-v1+domain-match-v1"
)


def extract_urls(text: str) -> list[str]:
    found: list[str] = []
    for m in URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;)")
        if url not in found:
            found.append(url)
    return found

def detect_mention(text: str, brand_tokens: list[str], *, exclude_suffix: str | None = None) -> bool:
    corpus = text or ""
    if exclude_suffix and exclude_suffix in corpus:
        corpus = corpus.replace(exclude_suffix, " ")
    for token in brand_tokens:
        if not token:
            continue
        if len(token) < 3 and brand_tokens:
            # keep short only if it's the only usable token — handled by caller
            pass
        if "." in token:
            if token.lower() in corpus.lower():
                return True
        else:
            pattern = re.compile(rf"\b{re.escape(token)}\b", re.I)
            if pattern.search(corpus):
                return True
    return False


def detect_citation(
    text: str,
    site_domain: str | TargetSiteIdentity,
    extra_urls: list[str] | None = None,
    *,
    identity: TargetSiteIdentity | None = None,
) -> tuple[bool, list[str]]:
    """URL-mention heuristic: target site URL appears in text (not retrieval citation).

    Matching uses ``target_match`` / ``TargetSiteIdentity`` (``domain-match-v1``) —
    the same rules as AI-search DO appearance/citation. Bare PSL equality alone
    must not credit sibling tenants on multi-tenant platforms (e.g.
    ``other.hashnode.dev`` for a ``nik-hil.hashnode.dev`` job).

    Prefer passing a frozen ``TargetSiteIdentity`` (or ``identity=``). A bare
    domain/URL string is resolved via ``resolve_target_site_identity``; for
    Hashnode-class leaves pass the seed hostname/URL, not the platform apex.
    """
    urls = extract_urls(text)
    if extra_urls:
        for u in extra_urls:
            if u not in urls:
                urls.append(u)
    if identity is None:
        if isinstance(site_domain, TargetSiteIdentity):
            identity = site_domain
        else:
            identity = resolve_target_site_identity(site_domain)
    cited: list[str] = []
    for u in urls:
        if target_match(u, identity):
            cited.append(u)
    return (len(cited) > 0, cited)


def domain_matches_target(url_or_host: str, target_domain: str) -> bool:
    """True iff url_or_host's registrable domain equals the target's (PSL-based).

    Legacy PSL equality helper (lookalike / domain-level checks).
    AI-search appeared/cited MUST use ``aeo_mvp.target_site.target_match`` instead.
    """
    left = registrable_domain(url_or_host)
    right = registrable_domain(target_domain)
    return bool(left) and left == right


@dataclass
class AggregateRates:
    """Legacy aggregate container; prefer LlmAggregateRates / AiSearchAggregateRates."""

    ai_mention_rate: float
    ai_citation_rate: float
    query_coverage: float
    mention_numerator: int
    citation_numerator: int
    coverage_numerator: int
    denominator_runs: int
    denominator_prompts: int


@dataclass
class LlmAggregateRates:
    llm_mention_rate: float
    llm_url_mention_rate: float
    query_coverage: float
    mention_numerator: int
    url_mention_numerator: int
    coverage_numerator: int
    denominator_runs: int
    denominator_prompts: int


@dataclass
class AiSearchAggregateRates:
    ai_search_mention_rate: float
    ai_search_citation_rate: float
    target_domain_appearance_rate: float
    query_coverage: float
    mention_numerator: int
    citation_numerator: int
    appearance_numerator: int
    coverage_numerator: int
    denominator_runs: int
    denominator_prompts: int


def aggregate_llm_metrics(observations: list[VisibilityObservation]) -> LlmAggregateRates:
    """Aggregate rates for non-retrieval LLM mention experiments."""
    r = len(observations)
    m = sum(1 for o in observations if o.detected_mention)
    k = sum(1 for o in observations if o.detected_citation)
    prompts = {o.prompt_id for o in observations}
    p = len(prompts)
    qm = len({o.prompt_id for o in observations if o.detected_mention})
    return LlmAggregateRates(
        llm_mention_rate=(m / r) if r else 0.0,
        llm_url_mention_rate=(k / r) if r else 0.0,
        query_coverage=(qm / p) if p else 0.0,
        mention_numerator=m,
        url_mention_numerator=k,
        coverage_numerator=qm,
        denominator_runs=r,
        denominator_prompts=p,
    )


def aggregate_ai_search_metrics(observations: list[VisibilityObservation]) -> AiSearchAggregateRates:
    """Aggregate rates for retrieval-enabled AI search visibility experiments.

    domain-match-v1: ``target_domain_appeared`` / ``target_domain_cited`` are the
    sole inputs for appearance/citation rates. Do **not** fall back to
    ``detected_mention`` / ``detected_citation`` when those flags are null —
    brand-token text mention must not set appearance/citation.
    """
    r = len(observations)
    m = sum(1 for o in observations if o.detected_mention)
    k = sum(1 for o in observations if o.target_domain_cited is True)
    appeared = sum(1 for o in observations if o.target_domain_appeared is True)
    prompts = {o.prompt_id for o in observations}
    p = len(prompts)

    def _covered(o: VisibilityObservation) -> bool:
        if o.detected_mention:
            return True
        if o.target_domain_appeared is True:
            return True
        if o.target_domain_cited is True:
            return True
        return False

    qm = len({o.prompt_id for o in observations if _covered(o)})
    return AiSearchAggregateRates(
        ai_search_mention_rate=(m / r) if r else 0.0,
        ai_search_citation_rate=(k / r) if r else 0.0,
        target_domain_appearance_rate=(appeared / r) if r else 0.0,
        query_coverage=(qm / p) if p else 0.0,
        mention_numerator=m,
        citation_numerator=k,
        appearance_numerator=appeared,
        coverage_numerator=qm,
        denominator_runs=r,
        denominator_prompts=p,
    )


def aggregate_metrics(observations: list[VisibilityObservation]) -> AggregateRates:
    """Back-compat wrapper; maps LLM rates onto legacy field names (do not emit in reports)."""
    llm = aggregate_llm_metrics(observations)
    return AggregateRates(
        ai_mention_rate=llm.llm_mention_rate,
        ai_citation_rate=llm.llm_url_mention_rate,
        query_coverage=llm.query_coverage,
        mention_numerator=llm.mention_numerator,
        citation_numerator=llm.url_mention_numerator,
        coverage_numerator=llm.coverage_numerator,
        denominator_runs=llm.denominator_runs,
        denominator_prompts=llm.denominator_prompts,
    )


def filter_brand_tokens(tokens: list[str]) -> list[str]:
    cleaned = []
    for t in tokens:
        t = (t or "").strip()
        if not t:
            continue
        if len(t) < 3:
            continue
        if t.lower() not in {c.lower() for c in cleaned}:
            cleaned.append(t)
    if not cleaned and tokens:
        # keep domain label even if short
        for t in tokens:
            if t and t.lower() not in {c.lower() for c in cleaned}:
                cleaned.append(t)
                break
    return cleaned
