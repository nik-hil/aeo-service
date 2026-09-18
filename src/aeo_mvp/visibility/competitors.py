"""Competitor domain discovery from retrieval observations (P1-D).

Only meaningful when retrieval_enabled=True. Descriptive counts only — no winner ranking.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from aeo_mvp.domains import registrable_domain
from aeo_mvp.visibility.base import VisibilityObservation


def extract_competitor_domains(
    observations: list[VisibilityObservation],
    *,
    target_domain: str,
) -> dict[str, Any]:
    """Aggregate competitor domains from source_urls / cited_urls.

    Returns descriptive counts only. Omits the target domain.
    """
    target = registrable_domain(target_domain)
    counts: Counter[str] = Counter()
    retrieval_obs = [o for o in observations if o.retrieval_enabled]
    if not retrieval_obs:
        return {
            "applicable": False,
            "reason": "No retrieval_enabled observations; competitor section omitted.",
            "competitors": [],
        }

    for obs in retrieval_obs:
        urls = list(obs.source_urls or []) + list(obs.cited_urls or [])
        for u in urls:
            domain = registrable_domain(u)
            if not domain or domain == target:
                continue
            counts[domain] += 1

    competitors = [
        {"domain": domain, "appearance_count": n}
        for domain, n in counts.most_common()
    ]
    return {
        "applicable": True,
        "target_domain": target,
        "observations_considered": len(retrieval_obs),
        "competitors": competitors,
        "note": (
            "Descriptive co-appearance counts from retrieval sources/citations only. "
            "Not a ranking or share-of-voice winner list."
        ),
    }
