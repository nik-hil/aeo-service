"""Target-site identity and domain-match-v1 matching (AI-search visibility).

``registrable_domain()`` remains true PSL eTLD+1. AI-search appeared/cited use
``target_match()`` against ``TargetSiteIdentity`` so multi-tenant publications
(e.g. ``nik-hil.hashnode.dev``) are not credited via platform apex
``hashnode.dev``.

See ``docs/methodology/DOMAIN_MATCHING.md`` and DECISIONS D023.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from aeo_mvp.domains import (
    registrable_domain,
    registrable_domain_public_only,
)

TargetDomainScope = Literal["registrable_domain", "hostname", "origin"]
MatchScope = TargetDomainScope  # Evaluator alias
IdentityKind = Literal[
    "ordinary",
    "supplemental_multi_tenant",
    "psl_private_multi_tenant",
    "platform_apex",
]

MatchReason = Literal[
    "exact_hostname",
    "www_alias",
    "registrable_equal",
    "subdomain_of_registrable",
    "exact_origin",
    "no_match",
]

MATCH_RULE_VERSION = "domain-match-v1"
SUPPLEMENTAL_ALLOWLIST_VERSION = "multi-tenant-supplemental-v1"

# Platforms NOT on PSL PRIVATE whose eTLD+1 is the platform apex. Tenant sites
# default to hostname match_scope / site_key = full hostname (www-stripped).
SUPPLEMENTAL_MULTI_TENANT_PLATFORMS: frozenset[str] = frozenset(
    {
        "hashnode.dev",
        "wordpress.com",
        "medium.com",
        "substack.com",
        "ghost.io",
        "tumblr.com",
    }
)


@dataclass(frozen=True)
class TargetSiteIdentity:
    """First-class scanned-site identity (Architect + Evaluator binding)."""

    seed_url: str
    scheme: str
    hostname: str
    hostname_apex_normalized: str
    origin: str
    registrable_domain: str
    target_domain_scope: TargetDomainScope
    multi_tenant_host: bool
    match_rule_version: str
    identity_kind: IdentityKind = "ordinary"
    supplemental_allowlist_version: str = SUPPLEMENTAL_ALLOWLIST_VERSION

    @property
    def match_scope(self) -> TargetDomainScope:
        return self.target_domain_scope

    def to_audit_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["match_scope"] = self.match_scope
        d["site_key"] = site_key_from_identity(self)
        return d


@dataclass(frozen=True)
class TargetMatchDetail:
    url: str
    hostname_normalized: str
    registrable_domain: str
    match_reason: MatchReason
    matched: bool

    def to_audit_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_hostname(host: str | None) -> str:
    """Lowercase; strip userinfo/port/brackets; strip trailing dots."""
    raw = (host or "").strip().lower()
    if not raw:
        return ""
    if "@" in raw:
        raw = raw.rsplit("@", 1)[-1]
    if raw.startswith("[") and "]" in raw:
        end = raw.find("]")
        raw = raw[1:end]
    elif ":" in raw:
        raw = raw.rsplit(":", 1)[0]
    return raw.strip(".")


def apex_normalize(hostname: str) -> str:
    """Normalize host for compare: lowercase, trailing-dot strip, ONE leading www."""
    host = normalize_hostname(hostname)
    if host.startswith("www."):
        return host[4:]
    return host


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _normalize_port(scheme: str, port: int | None) -> int | None:
    if port is None:
        return None
    if port == _default_port(scheme):
        return None
    return port


def parse_hostname(url_or_host: str) -> str:
    """Extract hostname; ignore scheme/port/path/query for match compares."""
    raw = (url_or_host or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        return normalize_hostname(urlparse(raw).netloc)
    # host or host/path
    host_part = raw.split("/", 1)[0]
    return normalize_hostname(host_part)


def parse_url_parts(url_or_host: str) -> tuple[str, str, int | None]:
    raw = (url_or_host or "").strip()
    if not raw:
        return "https", "", None
    if "://" not in raw:
        return "https", parse_hostname(raw), None
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    if scheme not in {"http", "https"}:
        scheme = "https"
    host = normalize_hostname(parsed.netloc)
    port = _normalize_port(scheme, parsed.port)
    return scheme, host, port


def build_origin(scheme: str, hostname: str, port: int | None) -> str:
    host = normalize_hostname(hostname)
    if not host:
        return ""
    scheme = (scheme or "https").lower()
    port = _normalize_port(scheme, port)
    if port is None:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _classify(
    hostname: str, reg: str
) -> tuple[TargetDomainScope, bool, IdentityKind]:
    """Return (scope, multi_tenant_host, identity_kind).

    Detection = PSL private-on + supplemental list — NOT bare label-count.
    """
    host = normalize_hostname(hostname)
    apex = apex_normalize(host)
    reg_n = normalize_hostname(reg)
    if not host or not reg_n:
        return "hostname", False, "ordinary"

    pub_reg = registrable_domain_public_only(host)
    on_private_platform = bool(pub_reg and reg_n and pub_reg != reg_n)

    # Bare platform apex (or www.apex) of a supplemental multi-tenant parent
    if reg_n in SUPPLEMENTAL_MULTI_TENANT_PLATFORMS and apex == reg_n:
        return "registrable_domain", True, "platform_apex"

    # Supplemental multi-tenant leaf (e.g. nik-hil.hashnode.dev)
    if reg_n in SUPPLEMENTAL_MULTI_TENANT_PLATFORMS and apex != reg_n:
        # Fail closed: never use platform-apex PSL as match key for a leaf.
        return "hostname", True, "supplemental_multi_tenant"

    # Private-PSL tenant (e.g. alice.github.io): eTLD+1 already includes tenant.
    if on_private_platform:
        if apex == reg_n or apex == f"www.{reg_n}":
            return "registrable_domain", True, "psl_private_multi_tenant"
        # blog.alice.github.io while seed is deeper — still registrable under tenant
        return "registrable_domain", True, "psl_private_multi_tenant"

    # Ordinary domains
    return "registrable_domain", False, "ordinary"


def resolve_target_site_identity(
    seed_url: str,
    *,
    scope: TargetDomainScope | None = None,
) -> TargetSiteIdentity:
    """Freeze target identity at prepare time from the job seed URL."""
    scheme, hostname, port = parse_url_parts(seed_url)
    if scheme not in {"http", "https"}:
        scheme = "https"
    if not hostname:
        return TargetSiteIdentity(
            seed_url=seed_url or "",
            scheme="https",
            hostname="",
            hostname_apex_normalized="",
            origin="",
            registrable_domain="",
            target_domain_scope=scope or "hostname",
            multi_tenant_host=False,
            match_rule_version=MATCH_RULE_VERSION,
            identity_kind="ordinary",
        )

    reg = registrable_domain(hostname) or hostname
    auto_scope, multi, kind = _classify(hostname, reg)
    chosen: TargetDomainScope = scope or auto_scope

    # Fail closed: leaf on supplemental platform must not use registrable scope
    # unless explicitly forced to origin (still not platform apex equality).
    if (
        kind == "supplemental_multi_tenant"
        and chosen == "registrable_domain"
        and scope is None
    ):
        chosen = "hostname"
    if kind == "supplemental_multi_tenant" and scope == "registrable_domain":
        # Explicit opt-in allowed (corporate-style); keep chosen.
        pass

    apex = apex_normalize(hostname)
    return TargetSiteIdentity(
        seed_url=seed_url,
        scheme=scheme,
        hostname=hostname,
        hostname_apex_normalized=apex,
        origin=build_origin(scheme, hostname, port),
        registrable_domain=reg,
        target_domain_scope=chosen,
        multi_tenant_host=multi,
        match_rule_version=MATCH_RULE_VERSION,
        identity_kind=kind,
    )


def site_key_from_identity(identity: TargetSiteIdentity) -> str:
    """Aggregation key for target and competitors (same function both sides)."""
    if identity.target_domain_scope == "hostname":
        return identity.hostname_apex_normalized
    if identity.target_domain_scope == "origin":
        return identity.origin
    return identity.registrable_domain


def site_key(url_or_host: str) -> str:
    return site_key_from_identity(resolve_target_site_identity(url_or_host))


def _match_reason_hostname(cand_raw: str, target_raw: str) -> MatchReason | None:
    c = normalize_hostname(cand_raw)
    t = normalize_hostname(target_raw)
    if not c or not t:
        return None
    c_apex = apex_normalize(c)
    t_apex = apex_normalize(t)
    if c_apex != t_apex:
        return None
    if c != t and (c.startswith("www.") or t.startswith("www.")):
        return "www_alias"
    if c == t:
        return "exact_hostname"
    # both apex-equal after www strip but neither flagged — treat as www_alias
    return "www_alias"


def target_match_detail(
    url_or_host: str, identity: TargetSiteIdentity
) -> TargetMatchDetail:
    """domain-match-v1: classify one candidate URL against frozen identity."""
    host = parse_hostname(url_or_host)
    cand_reg = registrable_domain(host) if host else ""
    empty = TargetMatchDetail(
        url=url_or_host or "",
        hostname_normalized=apex_normalize(host),
        registrable_domain=cand_reg,
        match_reason="no_match",
        matched=False,
    )
    if not (url_or_host or "").strip() or not host:
        return empty

    scope = identity.target_domain_scope

    if scope == "origin":
        scheme, cand_host, cand_port = parse_url_parts(url_or_host)
        cand_origin = build_origin(scheme, cand_host, cand_port)
        if cand_origin and identity.origin and cand_origin == identity.origin:
            return TargetMatchDetail(
                url=url_or_host,
                hostname_normalized=apex_normalize(host),
                registrable_domain=cand_reg,
                match_reason="exact_origin",
                matched=True,
            )
        return empty

    if scope == "hostname":
        # Exact apex_normalize equality ONLY — no parents/siblings/cousins/endswith.
        reason = _match_reason_hostname(host, identity.hostname)
        if reason is None:
            return empty
        return TargetMatchDetail(
            url=url_or_host,
            hostname_normalized=apex_normalize(host),
            registrable_domain=cand_reg,
            match_reason=reason,
            matched=True,
        )

    # registrable_domain scope (opt-in for multi-tenant; default for ordinary)
    target_reg = identity.registrable_domain
    if not cand_reg or not target_reg or cand_reg != target_reg:
        return empty

    host_reason = _match_reason_hostname(host, identity.hostname)
    if host_reason is not None:
        # Same host (or www alias) under registrable scope
        return TargetMatchDetail(
            url=url_or_host,
            hostname_normalized=apex_normalize(host),
            registrable_domain=cand_reg,
            match_reason=host_reason,
            matched=True,
        )

    # Same eTLD+1, different host → subdomain (or apex variant of registrable)
    cand_apex = apex_normalize(host)
    if cand_apex == target_reg or cand_apex == apex_normalize(identity.hostname):
        return TargetMatchDetail(
            url=url_or_host,
            hostname_normalized=cand_apex,
            registrable_domain=cand_reg,
            match_reason="registrable_equal",
            matched=True,
        )
    # blog.example.com when target is example.com
    if cand_apex.endswith("." + target_reg) or (
        identity.hostname_apex_normalized
        and cand_apex.endswith("." + identity.hostname_apex_normalized)
    ):
        return TargetMatchDetail(
            url=url_or_host,
            hostname_normalized=cand_apex,
            registrable_domain=cand_reg,
            match_reason="subdomain_of_registrable",
            matched=True,
        )
    return TargetMatchDetail(
        url=url_or_host,
        hostname_normalized=cand_apex,
        registrable_domain=cand_reg,
        match_reason="registrable_equal",
        matched=True,
    )


def target_match(url_or_host: str, identity: TargetSiteIdentity) -> bool:
    """Companion to ``registrable_domain()`` — scope-aware target site match."""
    return target_match_detail(url_or_host, identity).matched


def collect_target_matches(
    urls: list[str], identity: TargetSiteIdentity
) -> list[TargetMatchDetail]:
    out: list[TargetMatchDetail] = []
    seen: set[str] = set()
    for u in urls:
        if not u or u in seen:
            continue
        detail = target_match_detail(u, identity)
        if detail.matched:
            seen.add(u)
            out.append(detail)
    return out


def build_target_site_match_audit(
    *,
    identity: TargetSiteIdentity,
    source_urls: list[str],
    citation_urls: list[str],
) -> dict[str, Any]:
    """Per-observation audit blob (Architect + Evaluator fields)."""
    appeared = collect_target_matches(source_urls, identity)
    cited = collect_target_matches(citation_urls, identity)
    # Also count citation URLs that appeared only in citations toward appeared? 
    # Spec: appeared iff ≥1 source_urls match; cited iff ≥1 citation match.
    # DO provider ORs cited into appeared historically — keep that at provider layer.
    all_matches = appeared + [m for m in cited if m.url not in {a.url for a in appeared}]
    return {
        "appeared": len(appeared) > 0,
        "cited": len(cited) > 0,
        "scope": identity.target_domain_scope,
        "match_scope": identity.match_scope,
        "hostname": identity.hostname,
        "registrable_domain": identity.registrable_domain,
        "match_rule_version": identity.match_rule_version,
        "target_hostname": identity.hostname,
        "target_registrable_domain": identity.registrable_domain,
        "target_origin": identity.origin,
        "multi_tenant_host": identity.multi_tenant_host,
        "matched_source_urls": [m.url for m in appeared],
        "matched_citation_urls": [m.url for m in cited],
        "matched_urls_appeared": [m.url for m in appeared],
        "matched_urls_cited": [m.url for m in cited],
        "matches": [m.to_audit_dict() for m in all_matches],
    }


def is_supplemental_platform_apex(host_or_reg: str) -> bool:
    apex = apex_normalize(parse_hostname(host_or_reg) or host_or_reg)
    return apex in SUPPLEMENTAL_MULTI_TENANT_PLATFORMS
