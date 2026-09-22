"""Service helpers for content-optimization API (SSRF + job/page resolution)."""

from __future__ import annotations

import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from aeo_mvp.config import USER_AGENT, get_settings
from aeo_mvp.content.models import CONTENT_OPTIMIZATION_METHODOLOGY
from aeo_mvp.content.pipeline import run_content_optimization
from aeo_mvp.crawler.fetch import fetch_url
from aeo_mvp.db.models import ExperimentConfig, Job, Page, SiteProfile
from aeo_mvp.security.ssrf import SSRFError, is_obviously_unsafe_url


class OptimizationRequestError(ValueError):
    """Client-facing validation error for optimization requests."""


# Job pipeline selects a primary page (homepage / important / shallowest) and
# optionally a small number of additional pages — never the full crawl set.
CONTENT_OPT_PAGE_CAP = 3


def _page_has_html(page: Page) -> bool:
    return bool(page.html and str(page.html).strip())


def _path_of(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url or "").path or "/").rstrip("/") or "/"


def select_pages_for_content_optimization(
    pages: list[Page],
    *,
    site_profile: dict[str, Any] | None = None,
    max_pages: int = CONTENT_OPT_PAGE_CAP,
) -> tuple[list[Page], dict[str, Any]]:
    """Select primary page(s) for Phase 5 — documented selection rule.

    Priority (stable):
      1. Homepage: depth 0 and path ``/``
      2. URLs listed in SiteProfile ``important_pages``
      3. Remaining by depth, then URL (same order as ``resolve_page_html``)

    Cap: at most ``max_pages`` (default 3). Prefer a single homepage when present.
    """
    eligible = [p for p in pages if _page_has_html(p)]
    cap = max(1, min(int(max_pages), CONTENT_OPT_PAGE_CAP))
    selection: dict[str, Any] = {
        "rule": "homepage_then_important_then_depth",
        "cap": cap,
        "eligible_count": len(eligible),
    }
    if not eligible:
        selection["reason"] = "no_eligible_page_html"
        return [], selection

    important_urls: set[str] = set()
    profile = site_profile or {}
    for item in profile.get("important_pages") or []:
        if isinstance(item, dict) and item.get("url"):
            important_urls.add(str(item["url"]))
        elif isinstance(item, str):
            important_urls.add(item)
    # StructuredSiteProfile nest (when SiteUnderstanding.to_dict is stored)
    structured = profile.get("structured") if isinstance(profile.get("structured"), dict) else {}
    for item in (structured or {}).get("important_pages") or []:
        if isinstance(item, dict) and item.get("url"):
            important_urls.add(str(item["url"]))

    def _rank(p: Page) -> tuple[int, int, int, str, str]:
        path = _path_of(p.url or "")
        is_home = 0 if (int(p.depth or 0) == 0 and path == "/") else 1
        is_important = 0 if (p.url or "") in important_urls else 1
        return (is_home, is_important, int(p.depth or 0), p.url or "", p.id or "")

    ranked = sorted(eligible, key=_rank)
    # Prefer exactly the homepage when it ranks first; still allow up to cap.
    chosen = ranked[:cap]
    selection["selected_urls"] = [p.url for p in chosen]
    selection["selected_page_ids"] = [p.id for p in chosen]
    selection["reason"] = (
        "homepage"
        if chosen and _path_of(chosen[0].url or "") == "/" and int(chosen[0].depth or 0) == 0
        else ("important_page" if chosen and (chosen[0].url or "") in important_urls else "depth_order")
    )
    return chosen, selection


def queryset_from_discovery(discovery: Any) -> Any:
    """Prefer frozen discovery QuerySet (+ fingerprint) over ad-hoc reshapes."""
    if discovery is None:
        return {"members": [], "query_set_version": "query-set-v3"}
    qs = getattr(discovery, "query_set", None)
    fingerprint = getattr(discovery, "fingerprint", None)
    if isinstance(qs, dict) and (qs.get("members") or qs.get("queries")):
        out = dict(qs)
        if fingerprint and not out.get("fingerprint"):
            out["fingerprint"] = fingerprint
        return out
    if hasattr(discovery, "to_dict"):
        data = discovery.to_dict()
        if isinstance(data, dict):
            if fingerprint and not data.get("fingerprint"):
                data = {**data, "fingerprint": fingerprint}
            return data
    if isinstance(discovery, dict):
        return discovery
    return {"members": [], "query_set_version": "query-set-v3"}


def _attach_hashnode_recommended_markdown(
    wire: dict[str, Any],
    *,
    page_url: str,
    page_id: str | None = None,
    title: str | None = None,
    source_markdown: str | None = None,
    content_representation: str | None = None,
    source_url: str | None = None,
    canonical_url: str | None = None,
) -> dict[str, Any]:
    """Attach Hashnode recommended Markdown + provenance onto an opt wire dict.

    Content-optimization ownership: when source Markdown is available in a
    Hashnode context, rewrite **proposals** are generated here (via
    ``enrich_ops_with_rewrite_proposals``) and attached onto edit ops /
    change-plan items before the Markdown generator runs. The generator only
    validates and applies; it does not invent rewrite copy.
    """
    from aeo_mvp.content.rewrite_proposal import enrich_ops_with_rewrite_proposals
    from aeo_mvp.platform.hashnode.applicability import is_hashnode_markdown_context
    from aeo_mvp.platform.hashnode.markdown_generator import generate_recommended_markdown

    intel = dict(wire.get("page_intelligence") or {})
    if page_id:
        intel["page_id"] = page_id
    if source_url is not None:
        intel["source_url"] = source_url
    if content_representation is not None:
        intel["content_representation"] = content_representation
    if canonical_url is not None:
        intel["canonical_url"] = canonical_url
    elif page_url:
        intel.setdefault("canonical_url", page_url)
    if source_markdown:
        intel["source_markdown"] = source_markdown

    if source_markdown and is_hashnode_markdown_context(
        url=page_url,
        content_representation=content_representation,
        source_url=source_url,
    ):
        gap_flat: list[dict[str, Any]] = []
        for block in wire.get("content_gaps") or []:
            if isinstance(block, dict):
                for g in block.get("gaps") or []:
                    if isinstance(g, dict):
                        gap_flat.append(g)
        brief_wire = (wire.get("optimization_briefs") or [None])[0] or wire.get("brief") or {}
        if not isinstance(brief_wire, dict):
            brief_wire = {}
        rec_hints: list[dict[str, Any]] = []
        draft_list_in = list(wire.get("content_drafts") or [])
        for d in draft_list_in:
            if isinstance(d, dict) and isinstance(d.get("recommendations"), list):
                rec_hints.extend(
                    r for r in d["recommendations"] if isinstance(r, dict)
                )
        # Soft signals from brief work_queue / action codes when present on wire.
        for key in ("recommendations", "selected_recommendations"):
            for r in wire.get(key) or []:
                if isinstance(r, dict):
                    rec_hints.append(r)
        edit_ops_in: list[dict[str, Any]] = [
            e for e in (brief_wire.get("edit_ops") or []) if isinstance(e, dict)
        ]
        change_plan_in: list[dict[str, Any]] = []
        for d in draft_list_in:
            if isinstance(d, dict):
                change_plan_in.extend(
                    c for c in (d.get("change_plan") or []) if isinstance(c, dict)
                )

        # --- Content optimization layer: generate rewrite proposals ---
        # Prefer edit_ops; fall back to change_plan / work_queue when needed.
        ops_seed: list[dict[str, Any]] = list(edit_ops_in)
        if not ops_seed:
            ops_seed = list(change_plan_in)
        if not ops_seed:
            for item in brief_wire.get("work_queue") or []:
                if isinstance(item, dict):
                    ops_seed.append(item)
        enriched_ops, _proposal, enrich_warnings = enrich_ops_with_rewrite_proposals(
            ops_seed,
            source_markdown=source_markdown,
            page_intelligence=intel,
            h1=str(intel.get("h1") or intel.get("title") or "").strip() or None,
        )
        # Sync enriched payloads onto change_plan rows (same targets).
        enriched_by_target: dict[str, dict[str, Any]] = {}
        for op in enriched_ops:
            if not isinstance(op, dict):
                continue
            key = str(
                op.get("target")
                or op.get("target_locator")
                or op.get("anchor_locator")
                or ""
            ).strip().lower()
            if key and op.get("proposed"):
                enriched_by_target[key] = op

        def _sync_proposal_fields(row: dict[str, Any]) -> dict[str, Any]:
            key = str(
                row.get("target")
                or row.get("target_locator")
                or row.get("anchor_locator")
                or ""
            ).strip().lower()
            src = enriched_by_target.get(key)
            if not src:
                return row
            out = dict(row)
            for field in (
                "original",
                "proposed",
                "evidence",
                "related_gap_ids",
                "reason",
            ):
                if src.get(field) is not None:
                    out[field] = src[field]
            if src.get("instruction") and not out.get("instruction"):
                out["instruction"] = src["instruction"]
            if src.get("reason") and not out.get("reason"):
                out["reason"] = src["reason"]
            return out

        edit_ops_enriched = [
            _sync_proposal_fields(dict(op)) if isinstance(op, dict) else op
            for op in (enriched_ops if enriched_ops else edit_ops_in)
        ]
        change_plan_enriched = [
            _sync_proposal_fields(dict(c)) for c in change_plan_in if isinstance(c, dict)
        ]
        # Persist enriched ops onto brief wire so opt-layer output carries payload.
        brief_out = dict(brief_wire)
        if edit_ops_enriched:
            brief_out["edit_ops"] = edit_ops_enriched
        if enrich_warnings:
            brief_out.setdefault("warnings", [])
            if isinstance(brief_out["warnings"], list):
                brief_out["warnings"] = list(brief_out["warnings"]) + list(
                    enrich_warnings
                )

        recommended = generate_recommended_markdown(
            source_markdown=source_markdown,
            page_intelligence=intel,
            brief=brief_out,
            gaps=gap_flat,
            recommendations=rec_hints or None,
            edit_ops=edit_ops_enriched or None,
            change_plan=change_plan_enriched or None,
            content_drafts=[d for d in draft_list_in if isinstance(d, dict)] or None,
            title_hint=title,
            source_url=source_url,
        )
        from aeo_mvp.platform.hashnode.markdown_generator import (
            SUGGESTED_MARKDOWN_SUBTITLE,
        )

        draft_entry = {
            "page_url": page_url,
            "page_id": page_id,
            "status": "generated" if recommended.ok else "skipped_no_meaningful_draft",
            "generator": recommended.generator_version,
            "writer": recommended.generator_version,
            "generator_version": recommended.generator_version,
            "content_provenance": "recommended_from_source_markdown",
            "body_markdown": recommended.body,
            "disclaimer": SUGGESTED_MARKDOWN_SUBTITLE,
            "warnings": list(recommended.warnings),
            "changed": recommended.changed,
            "source_url": recommended.source_url,
            "title": recommended.title,
            "applied_ops": list(recommended.applied_ops),
            "llm_used": False,
            "paid": False,
            "paid_llm": False,
            "paid_retrieval_used": False,
        }
        if recommended.seo_description:
            draft_entry["seo_description"] = recommended.seo_description
            draft_entry["meta_description"] = recommended.seo_description
        draft_list = list(wire.get("content_drafts") or [])
        existing0 = draft_list[0] if draft_list and isinstance(draft_list[0], dict) else {}
        if recommended.rewrite_provenance:
            draft_entry["rewrite_provenance"] = dict(recommended.rewrite_provenance)
            # Surface onto change_plan for UI/report (what/why/gap/evidence).
            prov = recommended.rewrite_provenance
            plan = [
                c
                for c in (
                    existing0.get("change_plan")
                    or change_plan_enriched
                    or change_plan_in
                    or []
                )
                if isinstance(c, dict)
            ]
            if not plan:
                plan = [
                    {
                        "action": "rewrite",
                        "target": "introduction",
                        "reason": prov.get("why") or "",
                        "original": prov.get("original") or "",
                        "proposed": prov.get("proposed") or "",
                        "evidence": list(prov.get("evidence") or []),
                        "related_gap_ids": list(prov.get("related_gap_ids") or []),
                    }
                ]
            else:
                updated_plan = []
                for item in plan:
                    row = dict(item)
                    target = str(
                        row.get("target") or row.get("target_locator") or ""
                    ).lower()
                    reason = str(
                        row.get("reason") or row.get("instruction") or ""
                    ).lower()
                    if row.get("action") == "rewrite" and (
                        "intro" in target
                        or target.startswith("section:")
                        or "answer-first" in reason
                        or target in {"introduction", "intro", "opening"}
                    ):
                        row["original"] = prov.get("original") or row.get("original")
                        row["proposed"] = prov.get("proposed")
                        row["evidence"] = list(prov.get("evidence") or [])
                        if prov.get("related_gap_ids") and not row.get(
                            "related_gap_ids"
                        ):
                            row["related_gap_ids"] = list(prov.get("related_gap_ids") or [])
                    updated_plan.append(row)
                plan = updated_plan or plan
            draft_entry["change_plan"] = plan
        if draft_list:
            draft_list[0] = {**existing0, **draft_entry}
        else:
            draft_list = [draft_entry]
        wire["content_drafts"] = draft_list
        wire["draft"] = draft_list[0]
        intel["recommended_markdown"] = recommended.body
        # Persist opt-layer enriched brief (proposals attached before apply).
        if wire.get("optimization_briefs"):
            briefs = list(wire["optimization_briefs"])
            if briefs and isinstance(briefs[0], dict):
                briefs[0] = {**briefs[0], **brief_out}
                wire["optimization_briefs"] = briefs
        wire["brief"] = brief_out
        if enrich_warnings:
            wire.setdefault("warnings", [])
            if isinstance(wire["warnings"], list):
                wire["warnings"] = list(wire["warnings"]) + [
                    w for w in enrich_warnings if w not in wire["warnings"]
                ]

    wire["page_intelligence"] = intel
    return wire


def optimize_job_pages(
    pages: list[Page],
    *,
    queryset: Any,
    site_profile: dict[str, Any] | None,
    options: dict[str, Any] | None = None,
    visibility_observations: list[dict[str, Any]] | None = None,
    llm_api_key: str | None = None,
) -> dict[str, Any]:
    """Run Phase 5 via shared ``run_content_optimization`` on selected crawl pages.

    Selection: homepage → important_pages → depth order; capped (see
    ``select_pages_for_content_optimization``). Honest skip when no HTML.
    Never enables paid DO retrieval. Draft Null unless content_draft/draft_paid.
    Wire shape matches ``ContentOptimizationResult.to_dict`` (+ job metadata).
    """
    opts = dict(options or {})
    content_draft = bool(opts.get("content_draft") or opts.get("generate_draft"))
    draft_paid = bool(opts.get("draft_paid") or opts.get("paid_llm_opt_in"))
    cfg = {
        "generate_draft": content_draft,
        "content_draft": content_draft,
        "content_draft_provider": opts.get("content_draft_provider"),
        "draft_paid": draft_paid,
    }
    # Fail-safe: only pass LLM key when paid draft is explicitly opted in.
    api_key = llm_api_key if draft_paid else None
    max_pages = int(opts.get("content_optimization_max_pages") or CONTENT_OPT_PAGE_CAP)
    max_pages = max(1, min(max_pages, CONTENT_OPT_PAGE_CAP))

    base: dict[str, Any] = {
        "methodology": CONTENT_OPTIMIZATION_METHODOLOGY,
        "enabled": True,
        "paid_retrieval": False,
        "paid_llm": False,
        "pages_considered": len(pages),
        "pages_optimized": 0,
        "page_ids": [],
        "skipped_page_ids": [p.id for p in pages if not _page_has_html(p)],
        "page_selection": None,
    }

    if not pages:
        return {
            **base,
            "status": "skipped_no_pages",
            "page_intelligence": None,
            "content_gaps": [],
            "optimization_briefs": [],
            "content_drafts": [],
            "warnings": ["no_crawled_pages"],
            "page_selection": {"rule": "homepage_then_important_then_depth", "reason": "no_pages"},
        }

    selected, selection = select_pages_for_content_optimization(
        pages, site_profile=site_profile, max_pages=max_pages
    )
    base["page_selection"] = selection

    if not selected:
        return {
            **base,
            "status": "skipped_no_html",
            "page_intelligence": None,
            "content_gaps": [],
            "optimization_briefs": [],
            "content_drafts": [],
            "warnings": ["no_eligible_page_html"],
        }

    # Single primary page → exact ContentOptimizationResult.to_dict shape.
    # Additional capped pages append to list keys only.
    content_gaps: list[dict[str, Any]] = []
    optimization_briefs: list[dict[str, Any]] = []
    content_drafts: list[dict[str, Any]] = []
    page_ids: list[str] = []
    primary_intel: dict[str, Any] | None = None
    primary_qoa: dict[str, Any] | None = None
    any_paid_llm = False

    for idx, page in enumerate(selected):
        page_md = getattr(page, "source_markdown", None)
        result = run_content_optimization(
            html=page.html,
            url=page.url or "",
            title_hint=page.title,
            queryset=queryset,
            site_profile=site_profile,
            config=cfg,
            generate_draft=content_draft,
            draft_paid=draft_paid,
            llm_api_key=api_key,
            visibility_observations=visibility_observations,
            source_markdown=page_md,
        )
        wire = result.to_dict()
        wire = _attach_hashnode_recommended_markdown(
            wire,
            page_url=page.url or "",
            page_id=page.id,
            title=page.title,
            source_markdown=page_md,
            content_representation=getattr(page, "content_representation", None),
            source_url=getattr(page, "source_url", None),
            canonical_url=getattr(page, "canonical_url", None) or page.url,
        )
        intel = dict(wire.get("page_intelligence") or {})

        if idx == 0:
            primary_intel = intel
            primary_qoa = wire.get("question_opportunity_analysis")
        content_gaps.extend(wire.get("content_gaps") or [])
        optimization_briefs.extend(wire.get("optimization_briefs") or [])
        content_drafts.extend(wire.get("content_drafts") or [])
        page_ids.append(page.id)
        any_paid_llm = any_paid_llm or bool(wire.get("paid_llm"))

    out = {
        **base,
        "status": "completed",
        "pages_optimized": len(page_ids),
        "page_ids": page_ids,
        # Authoritative ContentOptimizationResult.to_dict keys
        "page_intelligence": primary_intel,
        "content_gaps": content_gaps,
        "optimization_briefs": optimization_briefs,
        "content_drafts": content_drafts,
        "gap_report": content_gaps[0] if content_gaps else None,
        "brief": optimization_briefs[0] if optimization_briefs else None,
        "draft": content_drafts[0] if content_drafts else None,
        "paid_llm": any_paid_llm,
        "paid_retrieval": False,
    }
    if primary_qoa is not None:
        out["question_opportunity_analysis"] = primary_qoa
    return out


def _load_queryset_from_job(session: Session, job: Job) -> dict[str, Any] | None:
    cfg = (
        session.query(ExperimentConfig)
        .filter(ExperimentConfig.job_id == job.id)
        .order_by(ExperimentConfig.created_at.desc())
        .first()
    )
    if not cfg or not cfg.discovered_queries_json:
        return None
    try:
        data = json.loads(cfg.discovered_queries_json)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"members": [{"query": q} for q in data], "query_set_version": "query-set-v3"}
    return None


def load_site_profile(session: Session, job: Job) -> dict[str, Any] | None:
    row = session.query(SiteProfile).filter(SiteProfile.job_id == job.id).one_or_none()
    if not row or not row.profile_json:
        return None
    try:
        return json.loads(row.profile_json)
    except json.JSONDecodeError:
        return None


def resolve_page_html(
    session: Session,
    *,
    job_id: str | None,
    page_id: str | None,
    source_url: str | None,
    html: str | None,
    url_hint: str | None,
    allow_empty_html: bool = False,
) -> tuple[str | None, str, str | None, dict[str, Any]]:
    """Resolve page HTML + provenance extras (source_markdown, representation)."""
    extras: dict[str, Any] = {}
    if html is not None and source_url:
        raise OptimizationRequestError(
            "Provide either html (offline) or source_url (live), not both"
        )

    if job_id:
        job = session.get(Job, job_id)
        if job is None:
            raise OptimizationRequestError(f"Unknown job {job_id}")
        page: Page | None = None
        if page_id:
            page = session.get(Page, page_id)
            if page is None or page.job_id != job.id:
                raise OptimizationRequestError(
                    f"Page {page_id} not found on job {job_id}"
                )
        else:
            pages = (
                session.query(Page)
                .filter(Page.job_id == job.id)
                .order_by(Page.depth, Page.url)
                .all()
            )
            page = pages[0] if pages else None
        if page is None:
            raise OptimizationRequestError(f"Job {job_id} has no pages")
        page_html = page.html
        if not (page_html and str(page_html).strip()) and not allow_empty_html:
            fetch_err = getattr(page, "fetch_error", None)
            raise OptimizationRequestError(
                f"Page {page.id} has empty or missing HTML"
                + (f" (fetch_error={fetch_err})" if fetch_err else "")
                + "; pass allow_empty_html=true to analyze empty content"
            )
        extras = {
            "page_id": page.id,
            "source_markdown": getattr(page, "source_markdown", None),
            "content_representation": getattr(page, "content_representation", None),
            "source_url": getattr(page, "source_url", None),
            "canonical_url": getattr(page, "canonical_url", None) or page.url,
        }
        return page_html, page.url, page.title, extras

    if source_url:
        if is_obviously_unsafe_url(source_url):
            raise SSRFError(f"Unsafe URL rejected by SSRF policy: {source_url!r}")
        return None, source_url, None, extras

    if html is not None:
        if not str(html).strip() and not allow_empty_html:
            raise OptimizationRequestError(
                "html is empty; pass allow_empty_html=true to analyze empty content"
            )
        return html, url_hint or "", None, extras

    raise OptimizationRequestError(
        "Provide job_id (+ optional page_id), or source_url, or html (+ optional url)"
    )


async def fetch_html_ssrf_safe(url: str) -> tuple[str | None, str, str | None]:
    settings = get_settings()
    # SSRF resolve+validate+IP-pin happens once inside fetch_url (no prior resolve).
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        result = await fetch_url(client, url, timeout_s=settings.crawl_timeout_s)
    if result.error or not result.text:
        raise OptimizationRequestError(
            f"Failed to fetch source_url: {result.error or 'empty_body'}"
        )
    return result.text, result.final_url or url, None


def run_from_resolved(
    *,
    html: str | None,
    url: str,
    title_hint: str | None,
    queryset: Any,
    site_profile: dict[str, Any] | None,
    config: dict[str, Any] | None,
    generate_draft: bool,
    draft_paid: bool,
    llm_api_key: str | None,
    allow_empty_html: bool = False,
    source_markdown: str | None = None,
    visibility_observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not (html and str(html).strip()) and not allow_empty_html:
        raise OptimizationRequestError(
            "empty_page_html; pass allow_empty_html=true to analyze empty content"
        )
    result = run_content_optimization(
        html=html,
        url=url,
        title_hint=title_hint,
        queryset=queryset,
        site_profile=site_profile,
        config=config,
        generate_draft=generate_draft,
        draft_paid=draft_paid,
        llm_api_key=llm_api_key,
        source_markdown=source_markdown,
        visibility_observations=visibility_observations,
    )
    return result.to_dict()


def prepare_queryset(
    session: Session,
    job: Job | None,
    queryset: dict[str, Any] | list[Any] | None,
) -> Any:
    if queryset is not None:
        return queryset
    if job is not None:
        return _load_queryset_from_job(session, job)
    return {"members": [], "query_set_version": "query-set-v3"}
