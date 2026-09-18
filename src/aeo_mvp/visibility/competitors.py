"""Competitor domain discovery from retrieval observations (P1-D).

Only meaningful when retrieval_enabled=True. Descriptive counts only — no winner ranking.

Competitors use the same ``site_key()`` as the target. Hosted multi-tenant
tenants never aggregate to the platform apex. Target hits are omitted via
``target_match``, not bare PSL equality. Sibling tenants / platform apex on
supplemental multi-tenant platforms are dropped unless ``include_platform_siblings``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from aeo_mvp.domains import registrable_domain
from aeo_mvp.target_site import (
    TargetSiteIdentity,
    is_supplemental_platform_apex,
    parse_hostname,
    resolve_target_site_identity,
    site_key,
    site_key_from_identity,
    target_match,
)
from aeo_mvp.visibility.base import VisibilityObservation


def extract_competitor_domains(
    observations: list[VisibilityObservation],
    *,
    target_domain: str | None = None,
    target_identity: TargetSiteIdentity | None = None,
    include_platform_siblings: bool = False,
) -> dict[str, Any]:
    """Aggregate competitor site_keys from source_urls / cited_urls.

    Returns descriptive counts only. Omits the target site via ``target_match``.
    """
    identity = target_identity or resolve_target_site_identity(
        target_domain or ""
    )
    target_key = site_key_from_identity(identity)
    counts: Counter[str] = Counter()
    examples: dict[str, dict[str, Any]] = {}
    retrieval_obs = [o for o in observations if o.retrieval_enabled]
    if not retrieval_obs:
        return {
            "applicable": False,
            "reason": "No retrieval_enabled observations; competitor section omitted.",
            "competitors": [],
            "target_site": identity.to_audit_dict(),
        }

    for obs in retrieval_obs:
        urls = list(obs.source_urls or []) + list(obs.cited_urls or [])
        for u in urls:
            if not u:
                continue
            if target_match(u, identity):
                continue
            host = parse_hostname(u)
            if not host:
                continue
            key = site_key(u)
            if not key:
                continue
            # Drop bare supplemental platform apex / sibling tenants unless opt-in.
            if identity.multi_tenant_host and not include_platform_siblings:
                cand_id = resolve_target_site_identity(u)
                if cand_id.registrable_domain == identity.registrable_domain:
                    continue
                if is_supplemental_platform_apex(key):
                    continue
            counts[key] += 1
            if key not in examples:
                examples[key] = {
                    "site_key": key,
                    "raw_host": host,
                    "registrable_domain": registrable_domain(host),
                    "identity_kind": resolve_target_site_identity(u).identity_kind,
                    "example_url": u,
                }

    competitors = []
    for domain, n in counts.most_common():
        meta = examples.get(domain, {})
        competitors.append(
            {
                "domain": domain,
                "site_key": domain,
                "appearance_count": n,
                "raw_host": meta.get("raw_host"),
                "registrable_domain": meta.get("registrable_domain"),
                "identity_kind": meta.get("identity_kind"),
                "example_url": meta.get("example_url"),
            }
        )
    return {
        "applicable": True,
        "target_domain": identity.registrable_domain,
        "target_site_key": target_key,
        "target_site": identity.to_audit_dict(),
        "observations_considered": len(retrieval_obs),
        "include_platform_siblings": include_platform_siblings,
        "competitors": competitors,
        "note": (
            "Descriptive co-appearance counts from retrieval sources/citations only. "
            "Buckets use site_key() (hostname for supplemental multi-tenant tenants; "
            "PSL eTLD+1 otherwise). Target omitted via target_match. "
            "Not a ranking or share-of-voice winner list."
        ),
    }
