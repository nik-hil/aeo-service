"""Phase 4.1.1 — Harden evidence provenance trust boundary (tests A–J).

CORRECTIVE ONLY. No paid DigitalOcean calls. Does not claim full VERIFY.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from aeo_mvp.queries.evidence import (
    EvidenceRecord,
    normalize_provenance,
    observed_evidence_classes,
    stamp_evidence_dict,
)
from aeo_mvp.queries.generate import CandidateQuery
from aeo_mvp.queries.generate_v2 import (
    _evidence_classes_from_understanding,
    generate_candidates_v2,
)
from aeo_mvp.queries.quality import evaluate_query_v2
from aeo_mvp.queries.discovery import discover_queries
from aeo_mvp.understanding.site import SiteUnderstanding

# --- helpers ---


def _cand(
    *,
    text: str,
    evidence: list[dict],
    intent: str = "informational",
    topic: str = "tracing",
    entity: str = "SignalWatch",
) -> CandidateQuery:
    return CandidateQuery(
        query_id=f"q_{hashlib.sha256(text.encode()).hexdigest()[:8]}",
        text=text,
        intent=intent,  # type: ignore[arg-type]
        topic=topic,
        entity=entity,
        source_evidence=evidence,
        evidence_classes=sorted(
            {e.get("evidence_class", "metadata") for e in evidence}
        ),
        confidence=0.35,
    )


def _evd_status(q: CandidateQuery, u: SiteUnderstanding) -> str:
    d = evaluate_query_v2(q, u)
    return next(x for x in d.dimensions if x.name == "evidence_support").status


def _saas_u() -> SiteUnderstanding:
    return SiteUnderstanding(
        organization_brand="SignalWatch",
        products_services=["SignalWatch Metrics", "SignalWatch Traces"],
        topics=[
            "Distributed tracing overview",
            "Metrics cardinality control",
            "Alert routing policies",
            "OpenTelemetry collectors",
        ],
        audience_hints=["for SREs"],
        industry_category_guess="observability",
        site_genre="saas_product",
        commercial_intents=["pricing", "trial"],
        structured={
            "primary_topics": {
                "evidence": [
                    {
                        "evidence_class": "title_h1",
                        "provenance": "observed",
                        "snippet": "Distributed tracing",
                    },
                    {
                        "evidence_class": "article_body",
                        "provenance": "observed",
                        "snippet": "OpenTelemetry",
                    },
                ]
            },
            "org_name": {
                "evidence": [
                    {
                        "evidence_class": "og_meta",
                        "provenance": "observed",
                        "snippet": "SignalWatch",
                    }
                ]
            },
            "products": {
                "evidence": [
                    {
                        "evidence_class": "jsonld",
                        "provenance": "observed",
                        "snippet": "SignalWatch Metrics",
                    }
                ]
            },
            "site_genre": {
                "evidence": [
                    {
                        "evidence_class": "jsonld",
                        "provenance": "observed",
                        "snippet": "saas_product",
                    }
                ]
            },
        },
        evidence_hash="phase411-saas",
        important_pages=[{"url": "https://signalwatch.example/"}] * 8,
    )


# --- A: missing → compatibility ---


def test_a_missing_provenance_maps_to_compatibility():
    assert normalize_provenance(None) == "compatibility"
    assert normalize_provenance("") == "compatibility"
    rec = EvidenceRecord.from_dict({"evidence_class": "title_h1", "snippet": "x"})
    assert rec is not None
    assert rec.provenance == "compatibility"
    stamped = stamp_evidence_dict({"evidence_class": "tags_series"})
    assert stamped["provenance"] == "compatibility"


# --- B: unknown → compatibility; SiteProfile labels → derived ---


def test_b_unknown_provenance_maps_to_compatibility():
    assert normalize_provenance("api_observation") == "compatibility"
    assert normalize_provenance("bogus") == "compatibility"
    assert normalize_provenance("synthetic_demo") == "compatibility"


def test_b2_siteprofile_labels_map_to_derived():
    """Architect lock: heuristic/derived_metric/llm_assist → derived (not observed)."""
    assert normalize_provenance("heuristic") == "derived"
    assert normalize_provenance("derived_metric") == "derived"
    assert normalize_provenance("llm_assist") == "derived"
    rec = EvidenceRecord.from_dict(
        {"evidence_class": "title_h1", "provenance": "llm_assist"}
    )
    assert rec is not None
    assert rec.provenance == "derived"
    stamped = stamp_evidence_dict(
        {"evidence_class": "og_meta"}, field_provenance="heuristic"
    )
    assert stamped["provenance"] == "derived"
    assert stamped["provenance"] != "observed"


# --- C: obs + derived → QSQ-EVD FAIL ---


def test_c_observed_plus_derived_fails_evd():
    u = _saas_u()
    q = _cand(
        text="What is distributed tracing in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "observed"},
            {"evidence_class": "article_body", "provenance": "derived"},
        ],
    )
    assert _evd_status(q, u) == "fail"
    assert len(observed_evidence_classes(q.source_evidence)) == 1


# --- D: obs + compat → QSQ-EVD FAIL ---


def test_d_observed_plus_compatibility_fails_evd():
    u = _saas_u()
    q = _cand(
        text="What is distributed tracing in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "observed"},
            {"evidence_class": "article_body", "provenance": "compatibility"},
        ],
    )
    assert _evd_status(q, u) == "fail"
    assert len(observed_evidence_classes(q.source_evidence)) == 1


# --- E: two distinct observed → PASS ---


def test_e_two_distinct_observed_passes_evd():
    u = _saas_u()
    q = _cand(
        text="What is distributed tracing in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "observed", "snippet": "t"},
            {
                "evidence_class": "article_body",
                "provenance": "observed",
                "snippet": "b",
            },
        ],
    )
    assert _evd_status(q, u) == "pass"
    assert len(observed_evidence_classes(q.source_evidence)) == 2


# --- F: two same class observed → FAIL (≥2 DISTINCT classes) ---


def test_f_two_same_observed_class_fails_evd():
    u = _saas_u()
    q = _cand(
        text="What is distributed tracing in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "observed", "snippet": "a"},
            {"evidence_class": "title_h1", "provenance": "observed", "snippet": "b"},
        ],
    )
    assert _evd_status(q, u) == "fail"
    assert len(observed_evidence_classes(q.source_evidence)) == 1


# --- G: preserve explicit observed ---


def test_g_preserve_explicit_observed():
    assert normalize_provenance("observed") == "observed"
    rec = EvidenceRecord.from_dict(
        {"evidence_class": "og_meta", "provenance": "observed"}
    )
    assert rec is not None
    assert rec.provenance == "observed"
    stamped = stamp_evidence_dict(
        {"evidence_class": "jsonld", "provenance": "observed"}
    )
    assert stamped["provenance"] == "observed"


# --- H: generate_v2 missing → compatibility, never observed ---


def test_h_generate_v2_missing_provenance_becomes_compatibility_not_observed():
    u = SiteUnderstanding(
        organization_brand="SignalWatch",
        topics=["Distributed tracing overview", "Metrics cardinality"],
        site_genre="saas_product",
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1", "snippet": "tracing"},
                    {"evidence_class": "tags_series", "snippet": "otel"},
                ]
            },
            "org_name": {"evidence": [{"evidence_class": "og_meta", "snippet": "SW"}]},
        },
        evidence_hash="phase411-missing",
    )
    classes = _evidence_classes_from_understanding(u)
    for items in classes.values():
        for item in items:
            if not isinstance(item, dict):
                continue
            # Structured items without provenance must not become observed
            if item.get("locator") in (
                "legacy_topic",
                "legacy_brand",
                "legacy_genre",
            ):
                assert item["provenance"] == "compatibility"
            elif "snippet" in item and item.get("evidence_class") in (
                "title_h1",
                "tags_series",
                "og_meta",
            ):
                assert item["provenance"] == "compatibility"
                assert item["provenance"] != "observed"

    cands, _plan = generate_candidates_v2(u)
    # Generation may still produce candidates (class presence), but none may
    # carry manufactured observed provenance from missing inputs.
    for q in cands:
        for ev in q.source_evidence:
            if isinstance(ev, dict) and "provenance" in ev:
                # If original structured lacked provenance, must be compatibility
                assert ev["provenance"] in (
                    "observed",
                    "derived",
                    "compatibility",
                )
            if isinstance(ev, dict) and ev.get("snippet") in (
                "tracing",
                "otel",
                "SW",
            ):
                assert ev.get("provenance") == "compatibility"

    # QSQ-EVD rejects these (no ≥2 observed)
    if cands:
        assert _evd_status(cands[0], u) == "fail"


def test_h2_field_heuristic_inherits_as_derived_not_observed():
    """Missing evidence provenance + field heuristic → derived; never observed."""
    u = SiteUnderstanding(
        organization_brand="SignalWatch",
        topics=["Distributed tracing overview", "Metrics cardinality"],
        site_genre="saas_product",
        structured={
            "primary_topics": {
                "provenance": "heuristic",
                "evidence": [
                    {"evidence_class": "title_h1", "snippet": "tracing"},
                    {"evidence_class": "article_body", "snippet": "body"},
                ],
            },
            "org_name": {
                "provenance": "derived_metric",
                "evidence": [{"evidence_class": "og_meta", "snippet": "SW"}],
            },
        },
        evidence_hash="phase411-field-heuristic",
    )
    classes = _evidence_classes_from_understanding(u)
    for cls_name in ("title_h1", "article_body"):
        items = classes.get(cls_name) or []
        assert any(
            isinstance(i, dict) and i.get("provenance") == "derived" for i in items
        )
        assert not any(
            isinstance(i, dict)
            and i.get("snippet") in ("tracing", "body")
            and i.get("provenance") == "observed"
            for i in items
        )
    og = classes.get("og_meta") or []
    assert any(isinstance(i, dict) and i.get("provenance") == "derived" for i in og)

    cands, _ = generate_candidates_v2(u)
    if cands:
        assert _evd_status(cands[0], u) == "fail"
        assert len(observed_evidence_classes(cands[0].source_evidence)) == 0


# --- I: derived preserved ---


def test_i_derived_provenance_preserved():
    assert normalize_provenance("derived") == "derived"
    rec = EvidenceRecord.from_dict(
        {"evidence_class": "title_h1", "provenance": "derived"}
    )
    assert rec is not None
    assert rec.provenance == "derived"
    stamped = stamp_evidence_dict(
        {"evidence_class": "jsonld", "provenance": "derived"}
    )
    assert stamped["provenance"] == "derived"

    u = SiteUnderstanding(
        organization_brand="SignalWatch",
        topics=["Distributed tracing overview", "Metrics cardinality"],
        site_genre="saas_product",
        structured={
            "primary_topics": {
                "evidence": [
                    {
                        "evidence_class": "title_h1",
                        "provenance": "derived",
                        "snippet": "t",
                    },
                    {
                        "evidence_class": "article_body",
                        "provenance": "derived",
                        "snippet": "b",
                    },
                ]
            }
        },
        evidence_hash="phase411-derived",
    )
    classes = _evidence_classes_from_understanding(u)
    title_items = classes.get("title_h1") or []
    assert any(
        isinstance(i, dict) and i.get("provenance") == "derived" for i in title_items
    )


# --- J: SignalWatch / synthetic SaaS regression ---


def test_j_signalwatch_saas_regression_with_explicit_observed():
    u = _saas_u()
    cands, plan = generate_candidates_v2(u)
    assert len(cands) >= plan.min_candidates or len(cands) >= 12
    joined = " | ".join(c.text.lower() for c in cands)
    assert "signalwatch" in joined
    assert "hashnode" not in joined
    assert "project management" not in joined

    r = discover_queries(
        u,
        top_n=20,
        options={"selection_seed": 42},
        discovery_only=True,
    )
    assert r.method == "query-discovery-v2"
    assert r.selected_count >= 8
    assert r.paid_retrieval_opt_in is False
    # Accepted members satisfy strongest QSQ-EVD
    for q in r.queries:
        obs = observed_evidence_classes(q.source_evidence)
        assert len(obs) >= 2, f"{q.query!r} obs={obs}"


# --- grep-guard: no unsafe promotion helpers remain in generate_v2 ---


def test_no_unsafe_observed_promotion_in_generate_v2():
    src = Path(__file__).resolve().parents[2] / "src/aeo_mvp/queries/generate_v2.py"
    text = src.read_text(encoding="utf-8")
    # Forbidden patterns that manufacture observed from missing/unknown
    assert 'setdefault("provenance", "observed")' not in text
    assert "setdefault('provenance', 'observed')" not in text
    assert re.search(
        r'provenance["\']?\s*\)?\s*not in[\s\S]{0,80}observed[\s\S]{0,80}'
        r'\][\s\S]{0,40}\[["\']provenance["\']\]\s*=\s*["\']observed["\']',
        text,
    ) is None
    # Positive: uses stamp / normalize path
    assert "stamp_evidence_dict" in text


# =============================================================================
# Evaluator Phase 4.1.1 — query-set-quality-v1.1.1 gates (P1–P8)
# P1/P2/P3/P4/P5/P8 FAIL blocks merge. Does not claim full VERIFY.
# =============================================================================


_REPO = Path(__file__).resolve().parents[2]
_QUERIES = _REPO / "src/aeo_mvp/queries"
_FREEZE_PATHS = (
    "src/aeo_mvp/security/ssrf.py",
    "src/aeo_mvp/target_site.py",
    "src/aeo_mvp/domains.py",
    "src/aeo_mvp/scoring/health.py",
    "src/aeo_mvp/visibility/digitalocean_web_search.py",
)


def _adapter_sources() -> dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in (
            _QUERIES / "generate_v2.py",
            _QUERIES / "generate.py",
            _QUERIES / "evidence.py",
        )
    }


def test_p1_normalize_missing_unknown_to_compatibility_never_observed():
    """P1 (blocking): missing/unknown → compatibility; never silent observed."""
    from aeo_mvp.queries.quality import QUERY_SET_QUALITY_METHODOLOGY

    assert QUERY_SET_QUALITY_METHODOLOGY == "query-set-quality-v1.1.1"
    for raw in (None, "", "unknown", "api_observation", "synthetic_demo", "estimate"):
        assert normalize_provenance(raw) == "compatibility"
        assert normalize_provenance(raw) != "observed"
    rec = EvidenceRecord.from_dict({"evidence_class": "title_h1"})
    assert rec is not None and rec.provenance == "compatibility"
    assert stamp_evidence_dict({"evidence_class": "og_meta"})["provenance"] == (
        "compatibility"
    )


def test_p2_no_implicit_observed_setdefault_or_stamp_to_observed():
    """P2 (blocking): ban setdefault/stamp-to-observed in query adapters."""
    banned = (
        'setdefault("provenance", "observed")',
        "setdefault('provenance', 'observed')",
        'setdefault("provenance",\'observed\')',
        '["provenance"] = "observed"',
        "['provenance'] = 'observed'",
    )
    for name, text in _adapter_sources().items():
        for pat in banned:
            assert pat not in text, f"{name} contains banned pattern: {pat}"
        # No branch that assigns observed when provenance missing/not-in
        assert (
            re.search(
                r'if\s+.*provenance.*not in[\s\S]{0,120}'
                r'\[["\']provenance["\']\]\s*=\s*["\']observed["\']',
                text,
            )
            is None
        ), f"{name}: implicit observed promotion branch"
        assert "normalize_provenance" in text or "stamp_evidence_dict" in text


def test_p3_qsq_evd_requires_two_distinct_observed_only():
    """P3 (blocking): QSQ-EVD ≥2 distinct observed; derived/compat do not count."""
    u = _saas_u()
    assert (
        _evd_status(
            _cand(
                text="What is distributed tracing in SignalWatch?",
                evidence=[
                    {"evidence_class": "title_h1", "provenance": "observed"},
                    {"evidence_class": "article_body", "provenance": "observed"},
                ],
            ),
            u,
        )
        == "pass"
    )
    for evidence in (
        [
            {"evidence_class": "title_h1", "provenance": "observed"},
            {"evidence_class": "article_body", "provenance": "derived"},
        ],
        [
            {"evidence_class": "title_h1", "provenance": "observed"},
            {"evidence_class": "article_body", "provenance": "compatibility"},
        ],
        [
            {"evidence_class": "title_h1", "provenance": "derived"},
            {"evidence_class": "og_meta", "provenance": "derived"},
        ],
        [
            {"evidence_class": "title_h1", "provenance": "observed"},
            {"evidence_class": "title_h1", "provenance": "observed"},
        ],
    ):
        q = _cand(text="What is distributed tracing in SignalWatch?", evidence=evidence)
        assert _evd_status(q, u) == "fail"
        assert len(observed_evidence_classes(q.source_evidence)) < 2


def test_p4_generator_preserves_explicit_fills_missing_compatibility():
    """P4 (blocking): preserve observed|derived|compatibility; missing → compatibility."""
    u = SiteUnderstanding(
        organization_brand="AcmeGarden",
        topics=["Tomato pruning calendar", "Soil amendments for clay"],
        site_genre="personal_tech_blog",
        structured={
            "primary_topics": {
                "evidence": [
                    {
                        "evidence_class": "title_h1",
                        "provenance": "observed",
                        "snippet": "Tomato pruning",
                    },
                    {
                        "evidence_class": "tags_series",
                        "provenance": "derived",
                        "snippet": "soil",
                    },
                    {"evidence_class": "article_body", "snippet": "clay"},  # missing
                ]
            },
            "org_name": {
                "evidence": [
                    {
                        "evidence_class": "og_meta",
                        "provenance": "compatibility",
                        "snippet": "AcmeGarden",
                    }
                ]
            },
        },
        evidence_hash="phase411-p4",
    )
    classes = _evidence_classes_from_understanding(u)
    by_snip = {
        i.get("snippet"): i.get("provenance")
        for items in classes.values()
        for i in items
        if isinstance(i, dict) and i.get("snippet")
    }
    assert by_snip.get("Tomato pruning") == "observed"
    assert by_snip.get("soil") == "derived"
    assert by_snip.get("clay") == "compatibility"
    assert by_snip.get("AcmeGarden") == "compatibility"
    assert "observed" not in {
        by_snip.get("clay"),
        by_snip.get("AcmeGarden"),
        by_snip.get("soil"),
    }

    cands, _ = generate_candidates_v2(u)
    for q in cands:
        for ev in q.source_evidence:
            if not isinstance(ev, dict):
                continue
            assert ev.get("provenance") in (
                "observed",
                "derived",
                "compatibility",
            )
            if ev.get("snippet") == "clay":
                assert ev["provenance"] == "compatibility"


def test_p5_missing_unknown_regression_evd_fail():
    """P5 (blocking): missing/unknown provenance on candidates → EVD fail."""
    u = _saas_u()
    missing = _cand(
        text="What is distributed tracing in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "snippet": "x"},
            {"evidence_class": "article_body", "snippet": "y"},
        ],
    )
    assert _evd_status(missing, u) == "fail"
    assert len(observed_evidence_classes(missing.source_evidence)) == 0

    unknown = _cand(
        text="What is distributed tracing in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "bogus"},
            {"evidence_class": "article_body", "provenance": "api_observation"},
        ],
    )
    # from_dict / observed_evidence_classes treat unknown as compatibility
    assert len(observed_evidence_classes(unknown.source_evidence)) == 0
    assert _evd_status(unknown, u) == "fail"

    # Generator path: missing structured → candidates cannot pass EVD
    weak = SiteUnderstanding(
        organization_brand="SignalWatch",
        topics=["Distributed tracing overview", "Metrics cardinality"],
        site_genre="saas_product",
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1", "snippet": "t"},
                    {"evidence_class": "tags_series", "snippet": "m"},
                ]
            }
        },
        evidence_hash="phase411-p5",
    )
    cands, _ = generate_candidates_v2(weak)
    assert cands  # viability may still generate
    for q in cands:
        assert _evd_status(q, weak) == "fail"
        assert len(observed_evidence_classes(q.source_evidence)) == 0


def test_p6_arbitrary_site_synthetic_same_provenance_rules():
    """P6: arbitrary non-Hashnode synthetic site follows same trust boundary."""
    u = SiteUnderstanding(
        organization_brand="CedarLedger",
        products_services=["Cedar Books", "Cedar Invoicing"],
        topics=[
            "Double-entry bookkeeping basics",
            "Invoice reconciliation workflows",
            "Multi-currency ledgers",
            "Audit trail retention",
        ],
        audience_hints=["for accountants"],
        industry_category_guess="accounting",
        site_genre="saas_product",
        commercial_intents=["pricing", "trial"],
        structured={
            "primary_topics": {
                "evidence": [
                    {
                        "evidence_class": "title_h1",
                        "provenance": "observed",
                        "snippet": "Double-entry",
                    },
                    {
                        "evidence_class": "article_body",
                        "provenance": "observed",
                        "snippet": "reconciliation",
                    },
                ]
            },
            "org_name": {
                "evidence": [
                    {
                        "evidence_class": "og_meta",
                        "provenance": "observed",
                        "snippet": "CedarLedger",
                    }
                ]
            },
            "products": {
                "evidence": [
                    {
                        "evidence_class": "jsonld",
                        "provenance": "observed",
                        "snippet": "Cedar Books",
                    }
                ]
            },
        },
        evidence_hash="phase411-cedar",
        important_pages=[{"url": "https://cedarledger.example/"}] * 8,
    )
    # Missing provenance must not become observed
    weak = SiteUnderstanding(
        organization_brand="CedarLedger",
        topics=["Double-entry bookkeeping basics", "Invoice reconciliation"],
        site_genre="saas_product",
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1", "snippet": "books"},
                    {"evidence_class": "jsonld", "snippet": "schema"},
                ]
            }
        },
        evidence_hash="phase411-cedar-weak",
    )
    classes = _evidence_classes_from_understanding(weak)
    for items in classes.values():
        for i in items:
            if isinstance(i, dict) and i.get("snippet") in ("books", "schema"):
                assert i["provenance"] == "compatibility"

    r = discover_queries(
        u, top_n=20, options={"selection_seed": 11}, discovery_only=True
    )
    assert r.selected_count >= 8
    joined = " ".join(q.query.lower() for q in r.queries)
    assert "cedar" in joined
    assert "hashnode" not in joined
    for q in r.queries:
        assert len(observed_evidence_classes(q.source_evidence)) >= 2


def test_p7_freezes_held_no_query_set_v4():
    """P7: freezes intact; query-set-v3 / query-quality-v1; no v4 bump."""
    import subprocess

    from aeo_mvp.queries.quality import QUALITY_VERSION, QUERY_SET_QUALITY_METHODOLOGY
    from aeo_mvp.queries.select_v2 import (
        QUERY_SET_VERSION,
        SELECTION_SEED_METHOD,
        DISCOVERY_METHOD_V2,
    )
    from aeo_mvp.queries.intent_budget import INTENT_BUDGET_ID
    from aeo_mvp.scoring.health import HEALTH_FORMULA_VERSION

    assert QUALITY_VERSION == "query-quality-v1"
    assert QUERY_SET_QUALITY_METHODOLOGY == "query-set-quality-v1.1.1"
    assert QUERY_SET_VERSION == "query-set-v3"
    assert QUERY_SET_VERSION != "query-set-v4"
    assert SELECTION_SEED_METHOD == "sha256_seeded_tiebreak_v1"
    assert DISCOVERY_METHOD_V2 == "query-discovery-v2"
    assert INTENT_BUDGET_ID == "intent-budget-v1"
    assert HEALTH_FORMULA_VERSION == "health-v1"
    for rel in _FREEZE_PATHS:
        assert (_REPO / rel).is_file(), rel
    # Freeze paths must be byte-identical to main tip
    diff = subprocess.run(
        ["git", "diff", "main", "--", *_FREEZE_PATHS],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert diff.returncode == 0
    assert diff.stdout == "", f"freeze diff non-empty:\n{diff.stdout[:500]}"
    verify_corrective = (
        _REPO / "docs/verification/VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.md"
    )
    assert verify_corrective.is_file()
    # Verifier-owned Phase 4.1.1 artifact must be present (not engineering claim)
    assert (
        _REPO / "docs/verification/VERIFY-PHASE4.1.1-PROVENANCE-2026-09-18.md"
    ).is_file()
    assert (
        _REPO / "docs/verification/VERIFY-PHASE4.1.1-PROVENANCE-2026-09-18.json"
    ).is_file()
    # Must not overwrite Phase 4.1 corrective VERIFY in this branch
    vdiff = subprocess.run(
        [
            "git",
            "diff",
            "main",
            "--",
            "docs/verification/VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.md",
            "docs/verification/VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.json",
        ],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert vdiff.stdout == ""


def test_p8_no_paid_digitalocean_in_discovery_dry_run():
    """P8 (blocking): discovery_only / dry-run makes zero paid DO / httpx calls."""
    from unittest.mock import patch

    u = _saas_u()
    with patch("httpx.AsyncClient") as mock_async:
        with patch("httpx.Client") as mock_client:
            r = discover_queries(
                u,
                top_n=20,
                options={
                    "selection_seed": 42,
                    "discovery_only": True,
                    "paid_retrieval_opt_in": True,
                },
                discovery_only=True,
                paid_retrieval_opt_in=True,
            )
            mock_client.assert_not_called()
            mock_async.assert_not_called()
    assert r.paid_retrieval_opt_in is False
    assert r.paid_retrieval_ready is False
    assert r.method == "query-discovery-v2"
