#!/usr/bin/env python3
"""Phase 6 Hashnode validation runner (cost-safe defaults).

Default: paid_retrieval_opt_in=false. Never invent live DO results.
Requires network for live crawl; writes artifacts under docs/verification/artifacts/phase6/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aeo_mvp.config import get_settings  # noqa: E402
from aeo_mvp.db.models import Page  # noqa: E402
from aeo_mvp.db.session import get_session_factory, init_db, reset_engine  # noqa: E402
from aeo_mvp.pipeline.orchestrator import create_job_record, run_job  # noqa: E402
from aeo_mvp.report.builder import build_report  # noqa: E402

DEFAULT_URL = "https://nik-hil.hashnode.dev/"
OUT_DIR = ROOT / "docs" / "verification" / "artifacts" / "phase6"


def _slim(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("html", "raw_html", "body_html") and isinstance(v, str) and len(v) > 400:
                out[k] = f"[omitted html len={len(v)}]"
            else:
                out[k] = _slim(v)
        return out
    if isinstance(obj, list):
        return [_slim(x) for x in obj]
    if isinstance(obj, str) and len(obj) > 30000:
        return obj[:30000] + "...[truncated]"
    return obj


async def _run(url: str, options: dict, db_url: str) -> dict:
    os.environ["AEO_DATABASE_URL"] = db_url
    os.environ.setdefault("AEO_PAID_RETRIEVAL_OPT_IN", "false")
    os.environ.setdefault("AEO_DEMO_MODE", "false")
    get_settings.cache_clear()
    reset_engine()
    init_db()
    session = get_session_factory()()
    settings = get_settings()
    paid = bool(options.get("paid_retrieval_opt_in", False))
    if paid and not settings.effective_do_api_key:
        raise SystemExit(
            "Refusing paid_retrieval_opt_in=true without DO_MODEL_ACCESS_KEY "
            "(ADR-026: key alone never authorizes spend; key also required)."
        )
    if options.get("provider") == "demo":
        raise SystemExit(
            "provider=demo rewrites base_url to demo.example — refuse for real-site runs."
        )

    job = create_job_record(session, url, demo_mode=False, options=options)
    session.commit()
    job_id = job.id
    t0 = time.time()
    job = await run_job(session, job_id, worker_id="phase6-script")
    session.commit()
    report = build_report(session, job)
    pages = session.query(Page).filter(Page.job_id == job_id).all()
    summary = {
        "job_id": job_id,
        "status": job.status,
        "base_url": job.base_url,
        "demo_mode": bool(job.demo_mode),
        "page_count": len(pages),
        "page_urls": [p.url for p in pages],
        "paid_retrieval_opt_in": paid,
        "provider_requested": options.get("provider", "auto"),
        "do_key_present": bool(settings.effective_do_api_key),
        "openai_key_present": bool(settings.openai_api_key),
        "adr026_gate": "open" if paid and settings.effective_do_api_key else "closed",
        "elapsed_s": round(time.time() - t0, 1),
        "report_keys": sorted(report.keys()),
        "content_optimization_status": (report.get("content_optimization") or {}).get(
            "status"
        ),
        "error_message": job.error_message,
    }
    session.close()
    return {"summary": summary, "report": report}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--db", default="sqlite:////tmp/aeo_phase6_hashnode.db")
    ap.add_argument(
        "--paid-retrieval",
        action="store_true",
        help="Set paid_retrieval_opt_in=true (requires DO key; still ADR-026 gated)",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    options = {
        "paid_retrieval_opt_in": bool(args.paid_retrieval),
        "content_optimization": True,
        "content_draft": True,
        "draft_paid": False,
        "provider": "auto",
        "selection_seed": args.seed,
        "query_top_n": 20,
        "max_pages": args.max_pages,
        "max_depth": 2,
    }
    result = asyncio.run(_run(args.url, options, args.db))
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "PHASE6_HASHNODE_JOB_SUMMARY.json").write_text(
        json.dumps(result["summary"], indent=2) + "\n", encoding="utf-8"
    )
    (out / "PHASE6_HASHNODE_JOB_REPORT_EXCERPT.json").write_text(
        json.dumps(_slim(result["report"]), indent=2, default=str)[:3_000_000] + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], indent=2))
    return 0 if result["summary"].get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
