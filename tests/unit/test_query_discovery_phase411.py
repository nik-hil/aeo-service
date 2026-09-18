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
