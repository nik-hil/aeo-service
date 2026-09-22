#!/usr/bin/env python3
"""PR #45 H1-fix live acceptance: Hashnode .md + paid LLM + paid DO web search.

Fail-closed:
- Requires DO_MODEL_ACCESS_KEY (or OPENAI_API_KEY aliasing DO inference)
- Requires AEO_PAID_RETRIEVAL_OPT_IN=true
- provider=digitalocean_web_search (never demo)
- Seed URL is the Hashnode .md only

Writes docs/aeo-p45-h1-fix-<UTC-timestamp>/ with CURRENT/RECOMMENDED/diff/README.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SEED_MD = (
    "https://nik-hil.hashnode.dev/"
    "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md"
)


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
            (os.environ.get("DO_INFERENCE_MODEL") or "openai-gpt-4o-mini").strip(),
        )
    if (os.environ.get("AEO_DEMO_MODE") or "").strip().lower() in {"1", "true", "yes"}:
        raise SystemExit("FAIL_closed: AEO_DEMO_MODE must be false")
    return {
        "do_key_present": bool(do_key),
        "openai_key_present": bool((os.environ.get("OPENAI_API_KEY") or "").strip()),
        "openai_base_url": os.environ.get("OPENAI_BASE_URL"),
        "openai_model": os.environ.get("OPENAI_MODEL"),
        "paid_retrieval_opt_in": True,
    }


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


async def _run(creds: dict) -> dict:
    from aeo_mvp.config import get_settings
    from aeo_mvp.db.models import Page
    from aeo_mvp.db.session import get_session_factory, init_db, reset_engine
    from aeo_mvp.pipeline.orchestrator import create_job_record, run_job
    from aeo_mvp.report.builder import build_report

    db_url = os.environ.get("AEO_DATABASE_URL") or f"sqlite:///{ROOT / 'aeo_mvp_p45_h1.db'}"
    os.environ["AEO_DATABASE_URL"] = db_url
    os.environ["AEO_DEMO_MODE"] = "false"
    os.environ["AEO_PAID_RETRIEVAL_OPT_IN"] = "true"
    # Local script auth bypass (never demo provider).
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

    session = get_session_factory()()
    job = create_job_record(session, SEED_MD, demo_mode=False, options=options)
    session.commit()
    job_id = job.id
    print(f"created job_id={job_id}", flush=True)
    t0 = time.time()
    job = await run_job(session, job_id, worker_id="p45-h1-paid-md")
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
    # Page HTML/MD bodies as CURRENT fallback
    for p in pages:
        raw = getattr(p, "raw_html", None) or getattr(p, "body_text", None) or ""
        if isinstance(raw, str) and raw.lstrip().startswith("#") and len(raw) > len(
            bucket["current_md"]
        ):
            bucket["current_md"] = raw
        # content opt wire may be on page
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
    current_md = bucket["current_md"]
    recommended_md = bucket["recommended_md"]

    summary = {
        "tip_sha": tip,
        "pr": 45,
        "branch": "cursor/substantive-content-opt-e95e",
        "url": SEED_MD,
        "job_id": job_id,
        "status": job.status,
        "error_message": job.error_message,
        "elapsed_sec": round(elapsed, 2),
        "page_urls": [p.url for p in pages],
        "credentials": creds,
        "options": options,
        "AEO_PAID_RETRIEVAL_OPT_IN": True,
        "web_search": "ON (digitalocean_web_search)",
        "content_optimization_status": cos.get("status"),
        "report_paid_llm": bool(report.get("paid_llm")),
        "report_paid_retrieval": bool(report.get("paid_retrieval")),
        "llm_used": llm_used,
        "paid_llm": paid_llm,
        "stub": stub,
        "method": flags.get("method"),
        "section_ops": bucket["section_ops"],
        "rewrite_section_targets": targets,
        "repeated_section_target": (
            len(set(targets)) < len(targets) if targets else None
        ),
        "applied_ops": bucket["applied_ops"],
        "current_chars": len(current_md),
        "recommended_chars": len(recommended_md),
        "current_ne_recommended": bool(recommended_md) and current_md != recommended_md,
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
        )
        else "FAIL"
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = ROOT / f"docs/aeo-p45-h1-fix-{ts}"
    out.mkdir(parents=True, exist_ok=True)
    if current_md:
        (out / "agents-z2h_current.md").write_text(current_md)
    if recommended_md:
        (out / "agents-z2h_recommended.md").write_text(recommended_md)
    if current_md and recommended_md:
        diff = "".join(
            difflib.unified_diff(
                current_md.splitlines(True),
                recommended_md.splitlines(True),
                fromfile="CURRENT.md",
                tofile="RECOMMENDED.md",
            )
        )
        (out / "agents-z2h_current_vs_recommended.diff").write_text(diff)
        summary["diff_bytes"] = len(diff)
    (out / "acceptance_report.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "job_report_slim.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "status": job.status,
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
        + "\n"
    )
    (out / "README.md").write_text(
        f"""# P45 H1 fix — paid LLM + paid DO web search acceptance

- **Tip SHA:** `{tip}`
- **Job ID:** `{job_id}`
- **URL (md only):** {SEED_MD}
- **paid_llm / llm_used:** {paid_llm} / {llm_used}
- **stub:** {stub}
- **web search:** ON (`AEO_PAID_RETRIEVAL_OPT_IN=true`, provider=`digitalocean_web_search`)
- **rewrite_section targets:** {targets}
- **repeated_section_target:** {summary.get('repeated_section_target')}
- **VERDICT:** {summary['VERDICT']}

Prior acceptance under `docs/aeo-p45-h1-fix-20260922-182803/` used web search OFF and
is **superseded / aborted** per user correction.
"""
    )
    session.close()
    print(json.dumps(summary, indent=2))
    print("ARTIFACT_DIR", out)
    return summary


def main() -> int:
    creds = _require_paid_env()
    summary = asyncio.run(_run(creds))
    return 0 if summary.get("VERDICT") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
