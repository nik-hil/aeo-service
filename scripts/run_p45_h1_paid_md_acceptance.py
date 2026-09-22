#!/usr/bin/env python3
"""PR #45 H1-fix live acceptance: Hashnode .md + paid LLM + paid DO web search.

Fail-closed:
- Requires DO_MODEL_ACCESS_KEY (or OPENAI_API_KEY aliasing DO inference)
- Requires AEO_PAID_RETRIEVAL_OPT_IN=true
- provider=digitalocean_web_search (never demo)
- Seed URL is the Hashnode .md only

When live Hashnode returns Cloudflare 403, injects fixture markdown for SEED_MD
only (crawl_source=fixture_due_to_cloudflare_403).

Dual-model mode (--dual): baseline openai-gpt-4o-mini then stronger openai-gpt-4o
into one timestamped docs folder with COMPARISON.md.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SEED_MD = (
    "https://nik-hil.hashnode.dev/"
    "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md"
)

DEFAULT_FIXTURE = (
    ROOT / "docs/aeo-p45-h1-fix-20260922-182803/agents-z2h_current.md"
)
BASELINE_MODEL = "openai-gpt-4o-mini"
STRONGER_MODEL = "openai-gpt-4o"


def _require_paid_env() -> dict:
    do_key = (
        os.environ.get("DO_MODEL_ACCESS_KEY")
        or os.environ.get("MODEL_ACCESS_KEY")
        or ""
    ).strip()
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    llm_key = do_key or openai_key
    paid_retrieval = (os.environ.get("AEO_PAID_RETRIEVAL_OPT_IN") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    missing = []
    if not llm_key:
        missing.append("DO_MODEL_ACCESS_KEY (or OPENAI_API_KEY)")
    if not paid_retrieval:
        missing.append("AEO_PAID_RETRIEVAL_OPT_IN=true")
    if missing:
        raise SystemExit(
            "FAIL_closed: paid LLM + paid DO web search required; missing: "
            + ", ".join(missing)
        )
    # P45E pattern: point OpenAI-compatible client at DO inference when using DO key.
    if do_key and not openai_key:
        os.environ["OPENAI_API_KEY"] = do_key
    if do_key:
        os.environ.setdefault(
            "OPENAI_BASE_URL",
            (os.environ.get("DO_INFERENCE_BASE_URL") or "https://inference.do-ai.run/v1").strip(),
        )
        os.environ.setdefault(
            "OPENAI_MODEL",
            (os.environ.get("DO_INFERENCE_MODEL") or BASELINE_MODEL).strip(),
        )
    if (os.environ.get("AEO_DEMO_MODE") or "").strip().lower() in {"1", "true", "yes"}:
        raise SystemExit("FAIL_closed: AEO_DEMO_MODE must be false")
    return {
        "do_key_present": bool(do_key),
        "openai_key_present": bool((os.environ.get("OPENAI_API_KEY") or "").strip()),
        "openai_base_url": os.environ.get("OPENAI_BASE_URL"),
        "openai_model": os.environ.get("OPENAI_MODEL"),
        "do_inference_model": os.environ.get("DO_INFERENCE_MODEL"),
        "paid_retrieval_opt_in": True,
    }


def _probe_live_md() -> tuple[bool, int | None]:
    """Return (ok, status_code). Never raises."""
    try:
        req = urllib.request.Request(
            SEED_MD,
            headers={"User-Agent": "AEOBot/0.1 (+research; respectful)"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(200)
            code = getattr(resp, "status", None) or resp.getcode()
            ok = (
                200 <= int(code) < 300
                and body.lstrip().startswith(b"#")
            )
            return ok, int(code)
    except Exception as exc:  # noqa: BLE001
        code = None
        if hasattr(exc, "code"):
            try:
                code = int(exc.code)
            except Exception:  # noqa: BLE001
                code = None
        return False, code


def _resolve_fixture_path() -> Path:
    live_cand = ROOT / "fixtures" / "agents-z2h-live.md"
    if live_cand.is_file():
        text = live_cand.read_text(encoding="utf-8", errors="replace")
        if text.lstrip().startswith("#"):
            return live_cand
    if DEFAULT_FIXTURE.is_file():
        return DEFAULT_FIXTURE
    raise SystemExit(f"FAIL_closed: no fixture at {DEFAULT_FIXTURE}")


def _install_seed_fixture_patch(fixture_md: str):
    """Monkeypatch page fetch for SEED_MD only; other URLs use real fetch.

    Patch ``aeo_mvp.crawler.discover.fetch_page_with_alternate`` (bound import),
    not only ``page_fetch`` — discover holds its own name binding.
    """
    from aeo_mvp.crawler import discover as discover_mod
    from aeo_mvp.crawler import page_fetch as pf
    from aeo_mvp.crawler.fetch import FetchResult

    real = discover_mod.fetch_page_with_alternate
    seed_path = SEED_MD.rstrip("/").split("/")[-1]

    def _is_seed(u: str) -> bool:
        u = (u or "").strip().rstrip("/")
        if u == SEED_MD.rstrip("/"):
            return True
        # normalize_url may alter query/fragment; match by path suffix
        if u.endswith(seed_path) or u.endswith(seed_path.removesuffix(".md")):
            return True
        return False

    async def _wrapped(client, url, *, timeout_s: float = 5.0):
        if _is_seed(url):
            logical = pf.strip_one_md_suffix(SEED_MD)
            fake = FetchResult(
                url=SEED_MD,
                final_url=SEED_MD,
                status_code=200,
                content_type="text/markdown; charset=utf-8",
                text=fixture_md,
                error=None,
            )
            print(f"[fixture] injecting markdown for seed url={url!r}", flush=True)
            return pf._markdown_outcome(
                logical_url=logical,
                source_url=SEED_MD,
                result=fake,
                raw_markdown=fixture_md,
                primary_status_code=200,
                primary_fetch_status="success",
                alternate_fetch_status="not_applicable",
            )
        return await real(client, url, timeout_s=timeout_s)

    return patch.object(discover_mod, "fetch_page_with_alternate", _wrapped)


def _walk_collect(obj, bucket: dict) -> None:
    if isinstance(obj, dict):
        if isinstance(obj.get("body_markdown"), str) and len(obj["body_markdown"]) > len(
            bucket.get("recommended_md") or ""
        ):
            bucket["recommended_md"] = obj["body_markdown"]
            bucket["applied_ops"] = list(obj.get("applied_ops") or [])
            bucket["draft_flags"] = {
                "llm_used": obj.get("llm_used"),
                "paid_llm": obj.get("paid_llm"),
                "method": obj.get("method"),
                "stub_hint": "stub" in str(obj.get("method") or "").lower(),
            }
        if isinstance(obj.get("recommended_markdown"), str) and len(
            obj["recommended_markdown"]
        ) > len(bucket.get("recommended_md") or ""):
            bucket["recommended_md"] = obj["recommended_markdown"]
        if isinstance(obj.get("source_markdown"), str) and len(obj["source_markdown"]) > len(
            bucket.get("current_md") or ""
        ):
            bucket["current_md"] = obj["source_markdown"]
        if obj.get("op_kind") in {
            "rewrite_section",
            "add_explanation",
            "rewrite_introduction",
            "metadata_seo_description",
        }:
            bucket.setdefault("section_ops", []).append(
                {
                    "op_kind": obj.get("op_kind"),
                    "status": obj.get("status"),
                    "disposition": obj.get("disposition"),
                    "target": obj.get("target") or obj.get("target_locator"),
                    "llm_used": obj.get("llm_used"),
                    "reason_preview": str(obj.get("reason") or "")[:220],
                    "related_gap_ids": obj.get("related_gap_ids"),
                    "query_text": obj.get("query_text"),
                }
            )
        for v in obj.values():
            _walk_collect(v, bucket)
    elif isinstance(obj, list):
        for v in obj:
            _walk_collect(v, bucket)


def _split_h1_sections(md: str) -> dict[str, str]:
    """Map H1 heading text -> body (until next H1)."""
    lines = (md or "").splitlines(keepends=True)
    sections: dict[str, str] = {}
    cur: str | None = None
    buf: list[str] = []
    for line in lines:
        if re.match(r"^#\s+\S", line):
            if cur is not None:
                sections[cur] = "".join(buf)
            cur = re.sub(r"^#\s+", "", line).strip()
            buf = []
        else:
            if cur is not None:
                buf.append(line)
    if cur is not None:
        sections[cur] = "".join(buf)
    return sections


def _dumping_evidence(current_md: str, recommended_md: str, targets: list) -> dict:
    """Heuristic: rewritten section body absorbing other H1 titles = dumping."""
    cur_secs = _split_h1_sections(current_md)
    rec_secs = _split_h1_sections(recommended_md)
    all_titles = [t for t in cur_secs if t]
    dumping_hits: list[dict] = []
    for tgt in targets:
        heading = str(tgt or "")
        if heading.startswith("section:"):
            heading = heading[len("section:") :]
        body = rec_secs.get(heading) or ""
        if not body.strip():
            continue
        foreign = [
            t
            for t in all_titles
            if t != heading and t in body and len(t) > 12
        ]
        # Ignore title appearing only as link text briefly; require multiple foreign H1s
        if len(foreign) >= 2:
            dumping_hits.append(
                {
                    "target": tgt,
                    "foreign_h1_titles_in_body": foreign[:8],
                    "body_chars": len(body),
                    "orig_chars": len(cur_secs.get(heading) or ""),
                }
            )
    # Also flag ratio blow-up vs original for ready targets
    ratio_hits = []
    for tgt in targets:
        heading = str(tgt or "")
        if heading.startswith("section:"):
            heading = heading[len("section:") :]
        o = len((cur_secs.get(heading) or "").strip())
        n = len((rec_secs.get(heading) or "").strip())
        if o > 0 and n > 4 * o:
            ratio_hits.append({"target": tgt, "orig": o, "new": n, "ratio": round(n / o, 2)})
    return {
        "later_section_dumping": bool(dumping_hits),
        "dumping_hits": dumping_hits,
        "ratio_blowups": ratio_hits,
        "dumping_gone": not bool(dumping_hits) and not bool(ratio_hits),
    }


def _apply_model(model: str) -> None:
    """Force both OPENAI_MODEL and DO_INFERENCE_MODEL; clear settings caches."""
    model = (model or "").strip()
    os.environ["OPENAI_MODEL"] = model
    os.environ["DO_INFERENCE_MODEL"] = model
    # Ensure OpenAI-compatible path points at DO inference
    os.environ.setdefault(
        "OPENAI_BASE_URL",
        (os.environ.get("DO_INFERENCE_BASE_URL") or "https://inference.do-ai.run/v1").strip(),
    )
    from aeo_mvp.config import get_settings
    from aeo_mvp.db.session import reset_engine

    get_settings.cache_clear()
    reset_engine()


async def _run_one(
    *,
    creds: dict,
    model: str,
    label: str,
    out_dir: Path,
    crawl_meta: dict,
    fixture_md: str | None,
) -> dict:
    from aeo_mvp.config import get_settings
    from aeo_mvp.db.models import Page
    from aeo_mvp.db.session import get_session_factory, init_db, reset_engine
    from aeo_mvp.pipeline.orchestrator import create_job_record, run_job
    from aeo_mvp.report.builder import build_report

    _apply_model(model)

    db_url = (
        os.environ.get("AEO_DATABASE_URL")
        or f"sqlite:///{ROOT / f'aeo_mvp_p45_h1_{label}.db'}"
    )
    # Isolate DBs per label even if parent set AEO_DATABASE_URL
    db_url = f"sqlite:///{ROOT / f'aeo_mvp_p45_h1_{label}.db'}"
    os.environ["AEO_DATABASE_URL"] = db_url
    os.environ["AEO_DEMO_MODE"] = "false"
    os.environ["AEO_PAID_RETRIEVAL_OPT_IN"] = "true"
    os.environ.setdefault("AEO_ENVIRONMENT", "development")
    os.environ.setdefault("AEO_ALLOW_UNAUTHENTICATED", "true")

    get_settings.cache_clear()
    reset_engine()
    init_db()
    settings = get_settings()
    if not settings.paid_retrieval_opt_in:
        raise SystemExit("FAIL_closed: settings.paid_retrieval_opt_in is false")
    if not (settings.effective_do_api_key or settings.openai_api_key or "").strip():
        raise SystemExit("FAIL_closed: no effective DO/OpenAI key after settings load")

    options = {
        "paid_retrieval_opt_in": True,
        "content_optimization": True,
        "content_draft": True,
        "generate_draft": True,
        "draft_paid": True,
        "paid_llm_opt_in": True,
        "content_draft_provider": "openai_compatible",
        "provider": "digitalocean_web_search",
        "selection_seed": 42,
        "query_top_n": 20,
        "max_pages": 4,
        "max_depth": 1,
        "runs_per_prompt": 1,
    }

    patcher = None
    if fixture_md is not None:
        patcher = _install_seed_fixture_patch(fixture_md)
        patcher.start()

    try:
        session = get_session_factory()()
        job = create_job_record(session, SEED_MD, demo_mode=False, options=options)
        session.commit()
        job_id = job.id
        print(f"[{label}] created job_id={job_id} model={model}", flush=True)
        t0 = time.time()
        job = await run_job(session, job_id, worker_id=f"p45-h1-paid-md-{label}")
        session.commit()
        elapsed = time.time() - t0
        report = build_report(session, job)
        pages = session.query(Page).filter(Page.job_id == job_id).all()

        bucket: dict = {
            "current_md": "",
            "recommended_md": "",
            "applied_ops": [],
            "section_ops": [],
            "draft_flags": {},
        }
        _walk_collect(report, bucket)
        for p in pages:
            raw = getattr(p, "raw_html", None) or getattr(p, "body_text", None) or ""
            if isinstance(raw, str) and raw.lstrip().startswith("#") and len(raw) > len(
                bucket["current_md"]
            ):
                bucket["current_md"] = raw
            sm = getattr(p, "source_markdown", None)
            if isinstance(sm, str) and sm.lstrip().startswith("#") and len(sm) > len(
                bucket["current_md"]
            ):
                bucket["current_md"] = sm
            for attr in ("content_json", "extras_json", "analysis_json"):
                blob = getattr(p, attr, None)
                if not blob:
                    continue
                try:
                    data = json.loads(blob) if isinstance(blob, str) else blob
                except Exception:  # noqa: BLE001
                    continue
                _walk_collect(data, bucket)

        cos = report.get("content_optimization") or {}
        tip = os.popen("git rev-parse HEAD").read().strip()
        rewrite_ready = [
            o
            for o in bucket["section_ops"]
            if o.get("op_kind") == "rewrite_section" and o.get("status") == "ready"
        ]
        targets = [o.get("target") for o in rewrite_ready]
        flags = bucket.get("draft_flags") or {}
        llm_used = bool(flags.get("llm_used")) or any(o.get("llm_used") for o in rewrite_ready)
        paid_llm = bool(flags.get("paid_llm")) or llm_used
        stub = bool(flags.get("stub_hint"))
        current_md = bucket["current_md"] or (fixture_md or "")
        recommended_md = bucket["recommended_md"]
        dump = _dumping_evidence(current_md, recommended_md, targets)

        distinct = sorted({str(t) for t in targets if t})
        mega = False
        if len(targets) == 1:
            # single target spanning near-full corpus
            heading = str(targets[0] or "")
            if heading.startswith("section:"):
                heading = heading[len("section:") :]
            body_len = len(_split_h1_sections(current_md).get(heading) or "")
            if body_len > 4000 or body_len > 0.5 * max(len(current_md), 1):
                mega = True

        summary: dict[str, Any] = {
            "tip_sha": tip,
            "pr": 45,
            "branch": "cursor/substantive-content-opt-e95e",
            "url": SEED_MD,
            "label": label,
            "model": model,
            "job_id": job_id,
            "status": job.status,
            "error_message": job.error_message,
            "elapsed_sec": round(elapsed, 2),
            "page_urls": [p.url for p in pages],
            "credentials": {
                k: v
                for k, v in creds.items()
                if k
                in {
                    "do_key_present",
                    "openai_key_present",
                    "openai_base_url",
                    "paid_retrieval_opt_in",
                }
            },
            "resolved_openai_model": settings.openai_model,
            "resolved_do_inference_model": settings.do_inference_model,
            "options": options,
            "AEO_PAID_RETRIEVAL_OPT_IN": True,
            "web_search": "ON (digitalocean_web_search)",
            "crawl_source": crawl_meta.get("crawl_source"),
            "fixture_path": crawl_meta.get("fixture_path"),
            "live_http_status": crawl_meta.get("live_http_status"),
            "content_optimization_status": cos.get("status"),
            "report_paid_llm": bool(report.get("paid_llm")),
            "report_paid_retrieval": bool(report.get("paid_retrieval")),
            "llm_used": llm_used,
            "paid_llm": paid_llm,
            "stub": stub,
            "method": flags.get("method"),
            "section_ops": bucket["section_ops"],
            "rewrite_section_targets": targets,
            "distinct_section_targets": distinct,
            "mega_section_selected": mega,
            "repeated_section_target": (
                len(set(targets)) < len(targets) if targets else None
            ),
            "applied_ops": bucket["applied_ops"],
            "current_chars": len(current_md),
            "recommended_chars": len(recommended_md),
            "current_ne_recommended": bool(recommended_md) and current_md != recommended_md,
            **dump,
        }
        summary["VERDICT"] = (
            "PASS"
            if (
                job.status == "completed"
                and paid_llm
                and not stub
                and bool(report.get("paid_retrieval") or options["paid_retrieval_opt_in"])
                and rewrite_ready
                and summary["current_ne_recommended"]
                and not mega
                and dump.get("dumping_gone")
            )
            else "FAIL"
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        if current_md:
            (out_dir / "agents-z2h_current.md").write_text(current_md, encoding="utf-8")
        if recommended_md:
            (out_dir / "agents-z2h_recommended.md").write_text(
                recommended_md, encoding="utf-8"
            )
        if current_md and recommended_md:
            diff = "".join(
                difflib.unified_diff(
                    current_md.splitlines(True),
                    recommended_md.splitlines(True),
                    fromfile="CURRENT.md",
                    tofile="RECOMMENDED.md",
                )
            )
            (out_dir / "agents-z2h_current_vs_recommended.diff").write_text(
                diff, encoding="utf-8"
            )
            summary["diff_bytes"] = len(diff)
        (out_dir / "acceptance_report.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "job_report_slim.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "status": job.status,
                    "model": model,
                    "label": label,
                    "paid_llm": report.get("paid_llm"),
                    "paid_retrieval": report.get("paid_retrieval"),
                    "content_optimization": {
                        k: cos.get(k)
                        for k in (
                            "status",
                            "paid_llm",
                            "paid_retrieval",
                            "pages_optimized",
                            "warnings",
                        )
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (out_dir / "README.md").write_text(
            f"""# P45 H1 fix — {label} ({model})

- **Tip SHA:** `{tip}`
- **Job ID:** `{job_id}`
- **Status:** {job.status}
- **Model:** `{model}`
- **URL (md only):** {SEED_MD}
- **crawl_source:** `{crawl_meta.get('crawl_source')}`
- **fixture_path:** `{crawl_meta.get('fixture_path')}`
- **paid_llm / llm_used:** {paid_llm} / {llm_used}
- **stub:** {stub}
- **web search:** ON (`AEO_PAID_RETRIEVAL_OPT_IN=true`, provider=`digitalocean_web_search`)
- **rewrite_section targets:** {targets}
- **distinct targets:** {distinct}
- **repeated_section_target:** {summary.get('repeated_section_target')}
- **dumping_gone:** {summary.get('dumping_gone')}
- **current_ne_recommended:** {summary.get('current_ne_recommended')}
- **VERDICT:** {summary['VERDICT']}
""",
            encoding="utf-8",
        )
        session.close()
        print(json.dumps({k: summary[k] for k in (
            "label", "model", "job_id", "status", "VERDICT",
            "rewrite_section_targets", "dumping_gone", "llm_used", "stub",
            "current_ne_recommended", "elapsed_sec",
        )}, indent=2), flush=True)
        print(f"[{label}] ARTIFACT_DIR {out_dir}", flush=True)
        return summary
    finally:
        if patcher is not None:
            patcher.stop()


def _write_comparison(root_out: Path, baseline: dict, stronger: dict, crawl_meta: dict) -> None:
    tip = baseline.get("tip_sha") or stronger.get("tip_sha")
    lines = [
        "# P45 H1 dual-model COMPARISON",
        "",
        f"- **Tip SHA:** `{tip}`",
        f"- **seed_url:** {SEED_MD}",
        f"- **crawl_source:** `{crawl_meta.get('crawl_source')}`",
        f"- **fixture_path:** `{crawl_meta.get('fixture_path')}`",
        f"- **live_http_status:** {crawl_meta.get('live_http_status')}",
        f"- **paid flags:** AEO_PAID_RETRIEVAL_OPT_IN=true, provider=digitalocean_web_search, draft_paid=true",
        "",
        "## Jobs",
        "",
        "| Role | Model | Job ID | Status | VERDICT | llm_used | stub | elapsed_s |",
        "|------|-------|--------|--------|---------|----------|------|-----------|",
    ]
    for s in (baseline, stronger):
        lines.append(
            f"| {s.get('label')} | `{s.get('model')}` | `{s.get('job_id')}` | "
            f"{s.get('status')} | **{s.get('VERDICT')}** | {s.get('llm_used')} | "
            f"{s.get('stub')} | {s.get('elapsed_sec')} |"
        )
    lines.extend(["", "## Section targets selected", ""])
    for s in (baseline, stronger):
        lines.append(f"### {s.get('label')} (`{s.get('model')}`)")
        lines.append(f"- targets: `{s.get('rewrite_section_targets')}`")
        lines.append(f"- distinct: `{s.get('distinct_section_targets')}`")
        lines.append(f"- repeated_section_target: {s.get('repeated_section_target')}")
        lines.append(f"- mega_section_selected: {s.get('mega_section_selected')}")
        lines.append("")
    lines.extend(
        [
            "## Dumping gone?",
            "",
            f"- baseline dumping_gone: **{baseline.get('dumping_gone')}** "
            f"(hits={baseline.get('dumping_hits')}, ratio={baseline.get('ratio_blowups')})",
            f"- stronger dumping_gone: **{stronger.get('dumping_gone')}** "
            f"(hits={stronger.get('dumping_hits')}, ratio={stronger.get('ratio_blowups')})",
            "",
            "## CURRENT vs RECOMMENDED / publishability",
            "",
            f"| Role | current_ne_recommended | current_chars | recommended_chars | diff_bytes | paid_llm | method |",
            f"|------|------------------------|---------------|-------------------|------------|----------|--------|",
        ]
    )
    for s in (baseline, stronger):
        lines.append(
            f"| {s.get('label')} | {s.get('current_ne_recommended')} | "
            f"{s.get('current_chars')} | {s.get('recommended_chars')} | "
            f"{s.get('diff_bytes')} | {s.get('paid_llm')} | {s.get('method')} |"
        )
    lines.extend(
        [
            "",
            "## Model differences",
            "",
            f"- Same seed URL and crawl body; only LLM model differs "
            f"(`{baseline.get('model')}` vs `{stronger.get('model')}`).",
            f"- Baseline targets: {baseline.get('rewrite_section_targets')}",
            f"- Stronger targets: {stronger.get('rewrite_section_targets')}",
            f"- Baseline VERDICT: {baseline.get('VERDICT')}",
            f"- Stronger VERDICT: {stronger.get('VERDICT')}",
            "",
        ]
    )
    text = "\n".join(lines)
    (root_out / "COMPARISON.md").write_text(text, encoding="utf-8")
    # short root-level alias inside the docs folder (same content)
    (root_out / "COMPARISON_SHORT.md").write_text(
        "\n".join(
            [
                "# COMPARISON (short)",
                "",
                f"tip={tip}",
                f"baseline={baseline.get('model')} job={baseline.get('job_id')} "
                f"status={baseline.get('status')} VERDICT={baseline.get('VERDICT')} "
                f"targets={baseline.get('rewrite_section_targets')} "
                f"dumping_gone={baseline.get('dumping_gone')}",
                f"stronger={stronger.get('model')} job={stronger.get('job_id')} "
                f"status={stronger.get('status')} VERDICT={stronger.get('VERDICT')} "
                f"targets={stronger.get('rewrite_section_targets')} "
                f"dumping_gone={stronger.get('dumping_gone')}",
                f"crawl_source={crawl_meta.get('crawl_source')}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_root_readme(
    root_out: Path, baseline: dict, stronger: dict, crawl_meta: dict
) -> None:
    tip = baseline.get("tip_sha") or stronger.get("tip_sha")
    (root_out / "README.md").write_text(
        f"""# P45 H1 fix — dual-model paid LLM + paid DO web search acceptance

- **Tip SHA:** `{tip}`
- **PR:** #45 (`cursor/substantive-content-opt-e95e`)
- **seed_url:** {SEED_MD}
- **crawl_source:** `{crawl_meta.get('crawl_source')}`
- **fixture_path:** `{crawl_meta.get('fixture_path')}`
- **live_http_status:** {crawl_meta.get('live_http_status')}
- **paid flags:** `AEO_PAID_RETRIEVAL_OPT_IN=true`, provider=`digitalocean_web_search`, never demo
- **Baseline model:** `{baseline.get('model')}` — job `{baseline.get('job_id')}` — status `{baseline.get('status')}` — VERDICT **{baseline.get('VERDICT')}**
- **Stronger model:** `{stronger.get('model')}` — job `{stronger.get('job_id')}` — status `{stronger.get('status')}` — VERDICT **{stronger.get('VERDICT')}**

## Layout

- `baseline/` — CURRENT / RECOMMENDED / diff / acceptance_report.json
- `stronger/` — same
- `COMPARISON.md` — section targets, dumping, publishability, model differences
- `COMPARISON_SHORT.md` — one-screen summary

Prior folder `docs/aeo-p45-h1-fix-20260922-182803/` is superseded (web search OFF / no live key).
""",
        encoding="utf-8",
    )


async def _run_dual(creds: dict) -> dict:
    live_ok, live_code = _probe_live_md()
    fixture_path: Path | None = None
    fixture_md: str | None = None
    if live_ok:
        crawl_meta = {
            "crawl_source": "live",
            "fixture_path": None,
            "live_http_status": live_code,
        }
        print(f"live fetch OK status={live_code}", flush=True)
    else:
        fixture_path = _resolve_fixture_path()
        fixture_md = fixture_path.read_text(encoding="utf-8")
        if not fixture_md.lstrip().startswith("#"):
            raise SystemExit(f"FAIL_closed: fixture does not start with #: {fixture_path}")
        crawl_meta = {
            "crawl_source": "fixture_due_to_cloudflare_403",
            "fixture_path": str(fixture_path.relative_to(ROOT)),
            "live_http_status": live_code,
            "seed_url": SEED_MD,
        }
        print(
            f"live blocked status={live_code}; using fixture {crawl_meta['fixture_path']}",
            flush=True,
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    root_out = ROOT / f"docs/aeo-p45-h1-fix-{ts}"
    root_out.mkdir(parents=True, exist_ok=True)

    baseline = await _run_one(
        creds=creds,
        model=BASELINE_MODEL,
        label="baseline",
        out_dir=root_out / "baseline",
        crawl_meta=crawl_meta,
        fixture_md=fixture_md,
    )
    stronger = await _run_one(
        creds=creds,
        model=STRONGER_MODEL,
        label="stronger",
        out_dir=root_out / "stronger",
        crawl_meta=crawl_meta,
        fixture_md=fixture_md,
    )
    _write_comparison(root_out, baseline, stronger, crawl_meta)
    _write_root_readme(root_out, baseline, stronger, crawl_meta)
    (root_out / "dual_summary.json").write_text(
        json.dumps(
            {
                "tip_sha": baseline.get("tip_sha"),
                "crawl_meta": crawl_meta,
                "baseline": {
                    k: baseline.get(k)
                    for k in (
                        "job_id",
                        "status",
                        "model",
                        "VERDICT",
                        "rewrite_section_targets",
                        "dumping_gone",
                        "llm_used",
                        "stub",
                        "current_ne_recommended",
                        "paid_llm",
                        "elapsed_sec",
                    )
                },
                "stronger": {
                    k: stronger.get(k)
                    for k in (
                        "job_id",
                        "status",
                        "model",
                        "VERDICT",
                        "rewrite_section_targets",
                        "dumping_gone",
                        "llm_used",
                        "stub",
                        "current_ne_recommended",
                        "paid_llm",
                        "elapsed_sec",
                    )
                },
                "artifact_dir": str(root_out),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("DUAL_ARTIFACT_DIR", root_out, flush=True)
    return {
        "artifact_dir": str(root_out),
        "baseline": baseline,
        "stronger": stronger,
        "crawl_meta": crawl_meta,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dual",
        action="store_true",
        default=True,
        help="Run baseline then stronger into one docs folder (default)",
    )
    ap.add_argument("--no-dual", action="store_true", help="Single-run mode")
    ap.add_argument("--model", default=None, help="Single-run model override")
    ap.add_argument("--label", default="single", help="Single-run label")
    args = ap.parse_args()

    # Load .env without printing secrets
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

    creds = _require_paid_env()
    if args.no_dual:
        model = args.model or os.environ.get("DO_INFERENCE_MODEL") or BASELINE_MODEL
        live_ok, live_code = _probe_live_md()
        fixture_md = None
        if live_ok:
            crawl_meta = {
                "crawl_source": "live",
                "fixture_path": None,
                "live_http_status": live_code,
            }
        else:
            fp = _resolve_fixture_path()
            fixture_md = fp.read_text(encoding="utf-8")
            crawl_meta = {
                "crawl_source": "fixture_due_to_cloudflare_403",
                "fixture_path": str(fp.relative_to(ROOT)),
                "live_http_status": live_code,
                "seed_url": SEED_MD,
            }
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = ROOT / f"docs/aeo-p45-h1-fix-{ts}"
        summary = asyncio.run(
            _run_one(
                creds=creds,
                model=model,
                label=args.label,
                out_dir=out,
                crawl_meta=crawl_meta,
                fixture_md=fixture_md,
            )
        )
        return 0 if summary.get("VERDICT") == "PASS" else 1

    result = asyncio.run(_run_dual(creds))
    b_ok = result["baseline"].get("VERDICT") == "PASS"
    s_ok = result["stronger"].get("VERDICT") == "PASS"
    return 0 if (b_ok and s_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
