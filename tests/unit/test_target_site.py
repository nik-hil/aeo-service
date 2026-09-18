"""domain-match-v1 / TargetSiteIdentity unit tests (offline fixtures)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aeo_mvp.domains import registrable_domain, registrable_domain_public_only
from aeo_mvp.target_site import (
    MATCH_RULE_VERSION,
    SUPPLEMENTAL_MULTI_TENANT_PLATFORMS,
    apex_normalize,
    resolve_target_site_identity,
    site_key,
    target_match,
    target_match_detail,
)
from aeo_mvp.visibility.base import VisibilityObservation
from aeo_mvp.visibility.competitors import extract_competitor_domains
from aeo_mvp.visibility.metrics import aggregate_ai_search_metrics


# --- PSL facts ---


def test_psl_hashnode_is_platform_apex_not_naive_bug():
    """Researcher: hashnode.dev is NOT PSL-private; eTLD+1 is hashnode.dev."""
    assert registrable_domain("nik-hil.hashnode.dev") == "hashnode.dev"
    assert registrable_domain("https://nik-hil.hashnode.dev/x") == "hashnode.dev"
    # Same with public-only extractor — not a private-suffix artifact.
    assert registrable_domain_public_only("nik-hil.hashnode.dev") == "hashnode.dev"
    assert "hashnode.dev" in SUPPLEMENTAL_MULTI_TENANT_PLATFORMS


def test_psl_private_domains_github_io():
    assert registrable_domain("alice.github.io") == "alice.github.io"
    assert registrable_domain("https://blog.alice.github.io/a") == "alice.github.io"
    # Without private domains this would collapse to github.io.
    assert registrable_domain_public_only("alice.github.io") == "github.io"


def test_psl_ordinary_and_lookalike_unchanged():
    assert registrable_domain("example.com") == "example.com"
    assert registrable_domain("https://www.example.com/path") == "example.com"
    assert registrable_domain("blog.example.com") == "example.com"
    assert registrable_domain("malicious-example.com") == "malicious-example.com"
    assert registrable_domain("malicious-example.com") != registrable_domain(
        "example.com"
    )


# --- Identity / scope defaults ---


def test_identity_hashnode_defaults_to_hostname_scope():
    ident = resolve_target_site_identity(
        "https://nik-hil.hashnode.dev/agents-zero-to-hero"
    )
    assert ident.hostname == "nik-hil.hashnode.dev"
    assert ident.hostname_apex_normalized == "nik-hil.hashnode.dev"
    assert ident.registrable_domain == "hashnode.dev"
    assert ident.target_domain_scope == "hostname"
    assert ident.match_scope == "hostname"
    assert ident.multi_tenant_host is True
    assert ident.identity_kind == "supplemental_multi_tenant"
    assert ident.match_rule_version == MATCH_RULE_VERSION
    assert ident.origin == "https://nik-hil.hashnode.dev"
    assert site_key(ident.seed_url) == "nik-hil.hashnode.dev"


def test_identity_ordinary_defaults_to_registrable():
    ident = resolve_target_site_identity("https://www.example.com/a")
    assert ident.hostname == "www.example.com"
    assert ident.hostname_apex_normalized == "example.com"
    assert ident.registrable_domain == "example.com"
    assert ident.target_domain_scope == "registrable_domain"
    assert ident.multi_tenant_host is False
    assert site_key("https://www.example.com/a") == "example.com"


def test_identity_github_io_private_psl():
    ident = resolve_target_site_identity("https://alice.github.io/proj")
    assert ident.registrable_domain == "alice.github.io"
    assert ident.multi_tenant_host is True
    assert ident.identity_kind == "psl_private_multi_tenant"
    assert ident.target_domain_scope == "registrable_domain"
    assert site_key("https://alice.github.io/proj") == "alice.github.io"


# --- Hostname-scope matching (Hashnode) ---


@pytest.mark.parametrize(
    "candidate,expect,reason",
    [
        ("https://nik-hil.hashnode.dev/article", True, "exact_hostname"),
        ("https://nik-hil.hashnode.dev/", True, "exact_hostname"),
        ("https://www.nik-hil.hashnode.dev/x", True, "www_alias"),
        ("NIK-HIL.hashnode.dev.", True, "exact_hostname"),
        ("https://nik-hil.hashnode.dev:443/a", True, "exact_hostname"),
        ("https://nik-hil.hashnode.dev/a?q=1", True, "exact_hostname"),
        ("https://other-user.hashnode.dev/x", False, "no_match"),
        ("https://hashnode.dev/", False, "no_match"),
        ("https://www.hashnode.dev/", False, "no_match"),
        ("https://blog.hashnode.dev/", False, "no_match"),
        ("https://maliciousnik-hil.hashnode.dev/", False, "no_match"),
        ("https://evil-nik-hil.hashnode.dev/", False, "no_match"),
        ("https://nik-hil.hashnode.dev.evil.com/", False, "no_match"),
        ("https://blog.nik-hil.hashnode.dev/", False, "no_match"),
        ("https://example.com/nik-hil.hashnode.dev", False, "no_match"),
    ],
)
def test_hashnode_hostname_scope_matrix(candidate, expect, reason):
    ident = resolve_target_site_identity("https://nik-hil.hashnode.dev/")
    assert ident.target_domain_scope == "hostname"
    detail = target_match_detail(candidate, ident)
    assert detail.matched is expect
    assert detail.match_reason == reason
    assert target_match(candidate, ident) is expect


def test_hashnode_no_endswith_lookalike():
    ident = resolve_target_site_identity("https://nik-hil.hashnode.dev/")
    evil = "maliciousnik-hil.hashnode.dev"
    # Naive endswith would wrongly match; apex equality must not.
    assert evil.endswith("nik-hil.hashnode.dev")
    assert not target_match(f"https://{evil}/", ident)


# --- Registrable-scope (ordinary + opt-in) ---


@pytest.mark.parametrize(
    "candidate,expect,reason",
    [
        ("https://example.com/a", True, "exact_hostname"),
        ("https://www.example.com/a", True, "www_alias"),
        ("https://blog.example.com/a", True, "subdomain_of_registrable"),
        ("https://malicious-example.com/a", False, "no_match"),
        ("https://example.com.evil.org/a", False, "no_match"),
    ],
)
def test_example_registrable_scope_matrix(candidate, expect, reason):
    ident = resolve_target_site_identity("https://example.com/")
    assert ident.target_domain_scope == "registrable_domain"
    detail = target_match_detail(candidate, ident)
    assert detail.matched is expect
    assert detail.match_reason == reason


def test_blog_under_hostname_false_registrable_opt_in_true():
    seed = "https://nik-hil.hashnode.dev/"
    host_scope = resolve_target_site_identity(seed)
    assert not target_match("https://blog.nik-hil.hashnode.dev/x", host_scope)

    reg_scope = resolve_target_site_identity(seed, scope="registrable_domain")
    assert reg_scope.target_domain_scope == "registrable_domain"
    # Opt-in registrable on Hashnode equates eTLD+1 — footgun, but explicit.
    assert target_match("https://blog.nik-hil.hashnode.dev/x", reg_scope)
    assert target_match("https://other-user.hashnode.dev/x", reg_scope)


def test_apex_normalize_strips_one_www_only():
    assert apex_normalize("www.example.com") == "example.com"
    assert apex_normalize("www.www.example.com") == "www.example.com"


# --- Aggregates: no mention→appearance fallback ---


def test_ai_search_aggregate_ignores_mention_when_flags_null():
    obs = [
        VisibilityObservation(
            provider_name="digitalocean_web_search",
            engine_label="digitalocean_web_search:m",
            query="q",
            prompt_id="p1",
            run_index=0,
            observed_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
            raw_response="{}",
            detected_mention=True,
            detected_citation=True,
            cited_urls=[],
            extraction_methodology="ai-search-vis-v1",
            provenance="api_observation",
            retrieval_enabled=True,
            experiment_kind="ai_search_visibility",
            target_domain_appeared=None,
            target_domain_cited=None,
            source_urls=[],
            search_queries=["q"],
        )
    ]
    rates = aggregate_ai_search_metrics(obs)
    assert rates.ai_search_mention_rate == 1.0
    assert rates.ai_search_citation_rate == 0.0
    assert rates.target_domain_appearance_rate == 0.0
    # query_coverage may still count brand mention
    assert rates.query_coverage == 1.0


# --- Competitors ---


def test_competitors_omit_target_via_match_not_psl_collapse():
    ident = resolve_target_site_identity("https://nik-hil.hashnode.dev/")
    obs = [
        VisibilityObservation(
            provider_name="digitalocean_web_search",
            engine_label="x",
            query="q",
            prompt_id="p1",
            run_index=0,
            observed_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
            raw_response="{}",
            detected_mention=False,
            detected_citation=False,
            cited_urls=["https://nik-hil.hashnode.dev/a"],
            extraction_methodology="ai-search-vis-v1",
            provenance="api_observation",
            retrieval_enabled=True,
            experiment_kind="ai_search_visibility",
            source_urls=[
                "https://nik-hil.hashnode.dev/a",
                "https://other-user.hashnode.dev/b",
                "https://hashnode.dev/",
                "https://competitor.com/c",
            ],
            target_domain_appeared=True,
            target_domain_cited=True,
        )
    ]
    result = extract_competitor_domains(obs, target_identity=ident)
    keys = {c["site_key"] for c in result["competitors"]}
    assert "nik-hil.hashnode.dev" not in keys
    # Sibling / platform apex dropped by default on multi-tenant
    assert "other-user.hashnode.dev" not in keys
    assert "hashnode.dev" not in keys
    assert "competitor.com" in keys
    assert result["competitors"][0]["raw_host"]
    assert result["competitors"][0]["identity_kind"]


def test_domain_label_not_platform_for_hashnode_tenant():
    from aeo_mvp.analyzers.base import domain_label

    assert domain_label("https://nik-hil.hashnode.dev/x") == "nik-hil"
    assert domain_label("https://example.com/") == "example"
