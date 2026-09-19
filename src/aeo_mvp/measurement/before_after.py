"""Reproducible before/after measurement for AEO validation (Phase 6).

Captures baseline visibility / coverage, maps recommendations to expected
effects, and compares post-change snapshots.

Honesty rules
-------------
- Never claim causality unless ``evidence_class == "causal_evidence"`` and
  the experiment controlled for query-set version, seed, provider, and
  methodology.
- Demo / unpaid visibility is labeled ``synthetic`` and is not AI-search proof.
- Coverage deltas (page_coverage) are content-readiness signals, not
  appearance/citation proof.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

MEASUREMENT_METHODOLOGY = "aeo-before-after-v1"

EvidenceClass = Literal[
    "observed_improvement",
    "correlation",
    "hypothesis",
    "causal_evidence",
]

EVIDENCE_CLASSES: tuple[str, ...] = (
    "observed_improvement",
    "correlation",
    "hypothesis",
    "causal_evidence",
)


@dataclass
class QueryVisibilityRow:
    """Per-query visibility observation at one measurement point."""

    query: str
    query_id: str | None = None
    appeared: bool | None = None
    cited: bool | None = None
    mention_estimate: float | None = None
    provider: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BaselineSnapshot:
    """Baseline measurement point (visibility and/or coverage)."""

    methodology: str = MEASUREMENT_METHODOLOGY
    target_domain: str = ""
    timestamp: str | None = None
    job_id: str | None = None
    query_set_version: str | None = None
    query_set_fingerprint: str | None = None
    selection_seed: int | str | None = None
    provider: str | None = None
    experiment_kind: str | None = None
    retrieval_enabled: bool | None = None
    paid_retrieval: bool | None = None
    visibility_mode: Literal["ai_search", "llm_mention", "demo_synthetic", "none"] = (
        "none"
    )
    n_queries: int = 0
    appeared_count: int | None = None
    cited_count: int | None = None
    appearance_rate: float | None = None
    citation_rate: float | None = None
    mention_rate: float | None = None
    mention_rate_provenance: str | None = None
    per_query: list[QueryVisibilityRow] = field(default_factory=list)
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    page_urls: list[str] = field(default_factory=list)
    source: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["per_query"] = [
            q.to_dict() if hasattr(q, "to_dict") else q for q in self.per_query
        ]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineSnapshot:
        raw = dict(data)
        rows = []
        for q in raw.pop("per_query", []) or []:
            if isinstance(q, QueryVisibilityRow):
                rows.append(q)
            elif isinstance(q, dict):
                rows.append(
                    QueryVisibilityRow(
                        query=str(q.get("query") or ""),
                        query_id=q.get("query_id"),
                        appeared=q.get("appeared"),
                        cited=q.get("cited"),
                        mention_estimate=q.get("mention_estimate"),
                        provider=q.get("provider"),
                        notes=str(q.get("notes") or ""),
                    )
                )
        raw["per_query"] = rows
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class PostChangeSnapshot(BaselineSnapshot):
    """Post-change measurement; same fields as baseline plus change notes."""

    change_source: Literal["live_cms", "fixture_simulated", "unknown"] = "unknown"
    applied_recommendation_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_baseline(
        cls,
        baseline: BaselineSnapshot,
        *,
        change_source: Literal["live_cms", "fixture_simulated", "unknown"] = "unknown",
        applied_recommendation_ids: list[str] | None = None,
    ) -> PostChangeSnapshot:
        base = BaselineSnapshot.from_dict(baseline.to_dict())
        return cls(
            **{k: getattr(base, k) for k in BaselineSnapshot.__dataclass_fields__},
            change_source=change_source,
            applied_recommendation_ids=list(applied_recommendation_ids or []),
        )


@dataclass
class OptimizationMapping:
    """Recommendation → website change → page → queries → expected effect."""

    recommendation_id: str
    page_url: str
    problem: str
    recommended_change: str
    website_change: str
    queries_affected: list[str] = field(default_factory=list)
    expected_effect: str = ""
    expected_aeo_relevance: str = (
        "Improved extractable answer units / page_coverage for linked probes; "
        "not a ranking or citation guarantee."
    )
    provenance: str = "derived"
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonResult:
    methodology: str = MEASUREMENT_METHODOLOGY
    evidence_class: EvidenceClass = "hypothesis"
    evidence_rationale: str = ""
    baseline: dict[str, Any] = field(default_factory=dict)
    post: dict[str, Any] = field(default_factory=dict)
    deltas: dict[str, Any] = field(default_factory=dict)
    page_level: list[dict[str, Any]] = field(default_factory=list)
    query_level: list[dict[str, Any]] = field(default_factory=list)
    methodology_parity: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rate(num: int | None, den: int | None) -> float | None:
    if num is None or den is None or den <= 0:
        return None
    return round(float(num) / float(den), 4)


def _dig(d: dict[str, Any], *path: str, default: Any = None) -> Any:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def extract_baseline_from_report(
    report: dict[str, Any],
    *,
    source: str = "job_report",
) -> BaselineSnapshot:
    """Extract a baseline snapshot from a job report or live Phase 4 summary."""
    warnings: list[str] = []
    disc = report.get("discovered_queries") or report.get("query_set") or {}
    if not isinstance(disc, dict):
        disc = {}
    qs = disc.get("query_set") if isinstance(disc.get("query_set"), dict) else disc
    exp = report.get("experiment") or {}
    if not isinstance(exp, dict):
        exp = {}

    provider = (
        exp.get("provider_name")
        or report.get("provider")
        or _dig(report, "visibility", "provider")
    )
    experiment_kind = exp.get("experiment_kind") or report.get("experiment_kind")
    retrieval_enabled = exp.get("retrieval_enabled")
    if retrieval_enabled is None:
        retrieval_enabled = report.get("retrieval_enabled")

    paid = report.get("paid_retrieval")
    if paid is None:
        paid = disc.get("paid_retrieval_opt_in")

    vis_block = report.get("visibility_obs") or report.get("visibility") or {}
    if not isinstance(vis_block, dict):
        vis_block = {}

    appeared = vis_block.get("appeared")
    cited = vis_block.get("cited")
    n = vis_block.get("n") or vis_block.get("observations")
    if n is None:
        n = disc.get("selected_count") or len(disc.get("queries") or []) or 0

    metrics = report.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}

    appearance_rate = None
    citation_rate = None
    mention_rate = None
    mention_prov = None

    for key in (
        "target_domain_appearance_rate",
        "ai_search_appearance_rate",
        "appearance_rate",
    ):
        block = metrics.get(key) or report.get(key)
        if isinstance(block, dict) and block.get("value") is not None:
            appearance_rate = float(block["value"])
            break
    for key in ("ai_search_citation_rate", "citation_rate"):
        block = metrics.get(key) or report.get(key)
        if isinstance(block, dict) and block.get("value") is not None:
            citation_rate = float(block["value"])
            break
    for key in (
        "ai_search_mention_rate",
        "llm_mention_rate",
        "mention_rate",
    ):
        block = metrics.get(key) or report.get(key)
        if isinstance(block, dict) and block.get("value") is not None:
            mention_rate = float(block["value"])
            mention_prov = block.get("provenance")
            break

    if appeared is not None and n:
        appearance_rate = appearance_rate if appearance_rate is not None else _rate(
            int(appeared), int(n)
        )
    if cited is not None and n:
        citation_rate = citation_rate if citation_rate is not None else _rate(
            int(cited), int(n)
        )

    # Classify visibility mode honestly
    if experiment_kind == "ai_search_visibility" and retrieval_enabled:
        mode: Literal["ai_search", "llm_mention", "demo_synthetic", "none"] = (
            "ai_search"
        )
    elif provider == "demo" or experiment_kind == "llm_mention":
        mode = "demo_synthetic" if provider == "demo" else "llm_mention"
        if provider == "demo":
            warnings.append(
                "Visibility provider=demo — metrics are synthetic, not AI-search proof."
            )
    elif appeared is None and cited is None:
        mode = "none"
        warnings.append("No visibility appearance/citation counts in report.")
    else:
        mode = "llm_mention"

    per_query: list[QueryVisibilityRow] = []
    audits = vis_block.get("audits") or report.get("match_audits") or []
    if isinstance(audits, list):
        for a in audits:
            if not isinstance(a, dict):
                continue
            per_query.append(
                QueryVisibilityRow(
                    query=str(a.get("query") or a.get("prompt") or ""),
                    query_id=a.get("query_id") or a.get("prompt_id"),
                    appeared=a.get("appeared"),
                    cited=a.get("cited"),
                    provider=provider,
                )
            )

    coverage_summary: dict[str, Any] = {}
    gaps = report.get("content_gaps") or []
    if isinstance(gaps, list) and gaps and isinstance(gaps[0], dict):
        coverage_summary = dict(gaps[0].get("coverage_summary") or {})
    elif isinstance(report.get("gap_report"), dict):
        coverage_summary = dict(
            (report["gap_report"] or {}).get("coverage_summary") or {}
        )

    seed = (
        qs.get("selection_seed")
        or qs.get("effective_seed")
        or _dig(disc, "seed_resolution", "effective_seed")
    )
    fingerprint = (
        qs.get("fingerprint")
        or disc.get("fingerprint")
        or report.get("fingerprint")
    )
    qs_version = (
        qs.get("query_set_version")
        or disc.get("query_set_version")
        or report.get("query_set_version")
    )

    pages = report.get("page_urls") or []
    if not pages and isinstance(report.get("crawl"), dict):
        pages = list((report["crawl"] or {}).get("page_urls") or [])

    return BaselineSnapshot(
        target_domain=str(
            report.get("base_url")
            or report.get("url")
            or _dig(report, "target_site", "hostname")
            or ""
        ),
        timestamp=report.get("emitted_at") or report.get("completed_at"),
        job_id=report.get("job_id"),
        query_set_version=qs_version,
        query_set_fingerprint=fingerprint,
        selection_seed=seed,
        provider=str(provider) if provider else None,
        experiment_kind=str(experiment_kind) if experiment_kind else None,
        retrieval_enabled=bool(retrieval_enabled)
        if retrieval_enabled is not None
        else None,
        paid_retrieval=bool(paid) if paid is not None else None,
        visibility_mode=mode,
        n_queries=int(n or 0),
        appeared_count=int(appeared) if appeared is not None else None,
        cited_count=int(cited) if cited is not None else None,
        appearance_rate=appearance_rate,
        citation_rate=citation_rate,
        mention_rate=mention_rate,
        mention_rate_provenance=mention_prov,
        per_query=per_query,
        coverage_summary=coverage_summary,
        page_urls=[str(p) for p in pages],
        source=source,
        warnings=warnings,
    )


def extract_coverage_snapshot(
    *,
    page_url: str,
    coverage_summary: dict[str, Any],
    gap_count: int,
    query_set_version: str | None = None,
    fingerprint: str | None = None,
    selection_seed: int | str | None = None,
    label: str = "coverage",
) -> BaselineSnapshot:
    """Build a coverage-only snapshot (content readiness, not AI visibility)."""
    return BaselineSnapshot(
        target_domain=page_url,
        query_set_version=query_set_version,
        query_set_fingerprint=fingerprint,
        selection_seed=selection_seed,
        visibility_mode="none",
        n_queries=int(coverage_summary.get("queries") or 0),
        coverage_summary={**coverage_summary, "gap_count": gap_count},
        page_urls=[page_url],
        source=label,
        warnings=[
            "Coverage snapshot only — page_coverage ≠ AI visibility ≠ health-v1."
        ],
    )


def compare_snapshots(
    baseline: BaselineSnapshot,
    post: BaselineSnapshot | PostChangeSnapshot,
    *,
    mappings: list[OptimizationMapping] | None = None,
    require_parity: bool = True,
) -> ComparisonResult:
    """Compare baseline vs post; assign an honest evidence class."""
    caveats: list[str] = list(baseline.warnings) + list(post.warnings)
    parity = {
        "query_set_version_match": (
            baseline.query_set_version == post.query_set_version
            and baseline.query_set_version is not None
        ),
        "fingerprint_match": (
            baseline.query_set_fingerprint == post.query_set_fingerprint
            and baseline.query_set_fingerprint is not None
        ),
        "seed_match": baseline.selection_seed == post.selection_seed,
        "provider_match": baseline.provider == post.provider,
        "experiment_kind_match": baseline.experiment_kind == post.experiment_kind,
        "visibility_mode_baseline": baseline.visibility_mode,
        "visibility_mode_post": post.visibility_mode,
    }

    deltas: dict[str, Any] = {}
    for field_name in (
        "appearance_rate",
        "citation_rate",
        "mention_rate",
        "appeared_count",
        "cited_count",
    ):
        b = getattr(baseline, field_name)
        p = getattr(post, field_name)
        if b is not None and p is not None:
            deltas[field_name] = {
                "baseline": b,
                "post": p,
                "delta": (p - b) if isinstance(p, (int, float)) else None,
            }

    # Coverage deltas
    b_cov = baseline.coverage_summary or {}
    p_cov = post.coverage_summary or {}
    cov_delta: dict[str, Any] = {}
    for k in ("covered", "gapped", "thin", "full", "partial", "gap_count", "queries"):
        if k in b_cov or k in p_cov:
            bv, pv = b_cov.get(k), p_cov.get(k)
            cov_delta[k] = {
                "baseline": bv,
                "post": pv,
                "delta": (pv - bv)
                if isinstance(bv, (int, float)) and isinstance(pv, (int, float))
                else None,
            }
    if cov_delta:
        deltas["coverage"] = cov_delta

    query_level: list[dict[str, Any]] = []
    b_by_id = {
        (q.query_id or q.query): q for q in baseline.per_query if (q.query_id or q.query)
    }
    for pq in post.per_query:
        key = pq.query_id or pq.query
        bq = b_by_id.get(key)
        if not bq:
            continue
        query_level.append(
            {
                "query_id": pq.query_id,
                "query": pq.query or bq.query,
                "appeared": {"baseline": bq.appeared, "post": pq.appeared},
                "cited": {"baseline": bq.cited, "post": pq.cited},
            }
        )

    page_level: list[dict[str, Any]] = []
    if mappings:
        for m in mappings:
            page_level.append(
                {
                    "page_url": m.page_url,
                    "recommendation_id": m.recommendation_id,
                    "queries_affected": list(m.queries_affected),
                    "expected_effect": m.expected_effect,
                    "expected_aeo_relevance": m.expected_aeo_relevance,
                }
            )

    # Evidence class assignment (conservative)
    evidence: EvidenceClass = "hypothesis"
    rationale = "Insufficient controlled evidence for stronger claims."

    change_source = getattr(post, "change_source", "unknown")
    same_mode = baseline.visibility_mode == post.visibility_mode
    both_ai = baseline.visibility_mode == "ai_search" and same_mode
    parity_ok = (
        parity["query_set_version_match"]
        and parity["fingerprint_match"]
        and parity["provider_match"]
    )
    d_app = (deltas.get("appearance_rate") or {}).get("delta")
    d_cit = (deltas.get("citation_rate") or {}).get("delta")
    rates_improved = isinstance(d_app, (int, float)) and d_app > 0

    if change_source == "fixture_simulated":
        evidence = "hypothesis"
        rationale = (
            "Post-change path used offline HTML fixtures (CMS publish not performed). "
            "Coverage deltas support a hypothesis only."
        )
        caveats.append("Live CMS publish was not performed.")
    elif baseline.visibility_mode == "demo_synthetic" or post.visibility_mode == (
        "demo_synthetic"
    ):
        evidence = "hypothesis"
        rationale = (
            "Demo/synthetic visibility cannot support observed AI-search improvement."
        )
    elif both_ai and rates_improved:
        if parity_ok and parity["seed_match"]:
            evidence = "observed_improvement"
            rationale = (
                "AI-search appearance rate increased under matching methodology; "
                "treat as observed improvement / correlation, not proven causation "
                "unless confounders were controlled."
            )
        else:
            evidence = "correlation"
            rationale = (
                "Appearance rate increased but methodology parity is incomplete "
                "(query-set / fingerprint / provider / seed) — correlation only."
            )
    elif both_ai and isinstance(d_app, (int, float)) and d_app == 0 and (
        isinstance(d_cit, (int, float)) and d_cit == 0
    ):
        evidence = "hypothesis"
        rationale = "No appearance/citation rate change observed."
    elif cov_delta and change_source != "live_cms":
        evidence = "hypothesis"
        rationale = (
            "Content coverage changed in fixture simulation; "
            "not equivalent to live visibility improvement."
        )
    elif cov_delta and both_ai:
        evidence = "correlation"
        rationale = "Coverage and visibility both measured; causal link not established."

    if baseline.visibility_mode == "none" and post.visibility_mode == "none":
        caveats.append(
            "Comparison is coverage-only (no AI-search appearance/citation metrics)."
        )

    if require_parity and not parity_ok and both_ai:
        caveats.append(
            "Methodology parity incomplete — do not interpret rate deltas as "
            "site-quality improvement."
        )
        if evidence == "observed_improvement":
            evidence = "correlation"

    return ComparisonResult(
        evidence_class=evidence,
        evidence_rationale=rationale,
        baseline=baseline.to_dict(),
        post=post.to_dict() if hasattr(post, "to_dict") else asdict(post),
        deltas=deltas,
        page_level=page_level,
        query_level=query_level,
        methodology_parity=parity,
        caveats=caveats,
    )


def mappings_from_brief(
    brief: dict[str, Any],
    *,
    max_items: int = 8,
) -> list[OptimizationMapping]:
    """Derive optimization mappings from an opt-brief-v1 dict."""
    page = str(brief.get("target_url") or brief.get("page_url") or "")
    out: list[OptimizationMapping] = []
    work = brief.get("work_queue") or []
    for i, w in enumerate(work[:max_items]):
        if not isinstance(w, dict):
            continue
        action = w.get("action") or "edit"
        target = w.get("target") or ""
        reason = w.get("reason") or ""
        qids = list(w.get("related_query_ids") or [])
        gids = list(w.get("related_gap_ids") or [])
        rid = f"{brief.get('brief_id') or 'brief'}:{action}:{target}"[:120]
        out.append(
            OptimizationMapping(
                recommendation_id=rid or f"rec_{i}",
                page_url=page,
                problem=reason or f"{action} needed for {target}",
                recommended_change=f"{action} {target}".strip(),
                website_change=f"Apply '{action}' on '{target}' ({reason})",
                queries_affected=qids,
                expected_effect=(
                    "Raise page_coverage for linked queries via clearer answer units."
                ),
                provenance="derived",
                evidence_refs=gids,
            )
        )
    if not out and brief.get("action"):
        out.append(
            OptimizationMapping(
                recommendation_id=str(brief.get("brief_id") or "brief"),
                page_url=page,
                problem=str(brief.get("executive_summary") or "")[:240],
                recommended_change=str(brief.get("action")),
                website_change=str(brief.get("action")),
                queries_affected=list(brief.get("target_query_ids") or [])[:8],
                expected_effect="Improve answerability for targeted probes.",
                provenance=str(brief.get("provenance_notes") or "derived"),
                evidence_refs=list(brief.get("gap_ids") or [])[:8],
            )
        )
    return out
