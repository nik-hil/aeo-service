"""Mention/citation rules and aggregate rate formulas (vis-exp-v1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from aeo_mvp.visibility.base import VisibilityObservation

URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+", re.I)
EXTRACTION_METHODOLOGY = "vis-exp-v1:mention-rule-v1+citation-rule-v1"


def extract_urls(text: str) -> list[str]:
    found: list[str] = []
    for m in URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;)")
        if url not in found:
            found.append(url)
    return found


def registrable_domain(url_or_host: str) -> str:
    if "://" in url_or_host:
        host = urlparse(url_or_host).netloc
    else:
        host = url_or_host
    return host.lower().removeprefix("www.")


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


def detect_citation(text: str, site_domain: str, extra_urls: list[str] | None = None) -> tuple[bool, list[str]]:
    urls = extract_urls(text)
    if extra_urls:
        for u in extra_urls:
            if u not in urls:
                urls.append(u)
    site = site_domain.lower().removeprefix("www.")
    cited: list[str] = []
    for u in urls:
        if registrable_domain(u) == site:
            cited.append(u)
    return (len(cited) > 0, cited)


@dataclass
class AggregateRates:
    ai_mention_rate: float
    ai_citation_rate: float
    query_coverage: float
    mention_numerator: int
    citation_numerator: int
    coverage_numerator: int
    denominator_runs: int
    denominator_prompts: int


def aggregate_metrics(observations: list[VisibilityObservation]) -> AggregateRates:
    r = len(observations)
    m = sum(1 for o in observations if o.detected_mention)
    k = sum(1 for o in observations if o.detected_citation)
    prompts = {o.prompt_id for o in observations}
    p = len(prompts)
    qm = len({o.prompt_id for o in observations if o.detected_mention})
    return AggregateRates(
        ai_mention_rate=(m / r) if r else 0.0,
        ai_citation_rate=(k / r) if r else 0.0,
        query_coverage=(qm / p) if p else 0.0,
        mention_numerator=m,
        citation_numerator=k,
        coverage_numerator=qm,
        denominator_runs=r,
        denominator_prompts=p,
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
