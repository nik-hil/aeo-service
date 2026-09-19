#!/usr/bin/env python3
"""Phase 7 post-publish llm-mention remeasure (same seed / query-set path).

Locks to Phase 6 authoritative baseline knobs:
  - selection_seed=3236362228
  - provider=openai_compatible
  - experiment llm_mention (via openai_compatible; not DO web_search)
  - paid_retrieval_opt_in=false by default (ADR-026 closed)

Does NOT claim causality. Does NOT invent live results.
Refuse to mark publish complete unless PHASE7_PUBLISH_STATUS.json says published=true
(or --allow-unpublished-remeasure for dry diagnostics).
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
DEFAULT_SEED = 3236362228
OUT_DIR = ROOT / "docs" / "verification" / "artifacts" / "phase7"
PUBLISH_STATUS = OUT_DIR / "PHASE7_PUBLISH_STATUS.json"
BASELINE_CONFIRMED = OUT_DIR / "PHASE7_BASELINE_CONFIRMED.json"


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


def load_publish_status(path: Path = PUBLISH_STATUS) -> dict:
    if not path.is_file():
        return {"published": False, "status": "MISSING_STATUS_FILE"}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Expected object JSON in {path}")
    return data


def baseline_remeasure_options(
    *,
    seed: int = DEFAULT_SEED,
    paid_retrieval_opt_in: bool = False,
    max_pages: int = 20,
    provider: str = "openai_compatible",
) -> dict:
    """Job options matching Phase 6 authoritative llm_mention baseline path."""
    if paid_retrieval_opt_in:
        raise ValueError(
            "Refusing paid_retrieval_opt_in=true in phase7 default helper "
            "(ADR-026 stays closed; use an explicit gated path if CoS later opts in)."
        )
    if provider != "openai_compatible":
        raise ValueError(
            f"Phase 7 remeasure requires provider=openai_compatible for llm_mention parity; got {provider!r}"
        )
    return {
        "paid_retrieval_opt_in": False,
        "content_optimization": True,
        "content_draft": True,
        "draft_paid": False,
        "provider": "openai_compatible",
        "selection_seed": int(seed),
        "query_top_n": 20,
        "max_pages": int(max_pages),
        "max_depth": 2,
    }


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
    if paid:
        raise SystemExit("ADR-026: phase7 helper refuses paid retrieval.")
    if options.get("provider") == "demo":
        raise SystemExit(
            "provider=demo rewrites base_url to demo.example — refuse for real-site runs."
        )

    job = create_job_record(session, url, demo_mode=False, options=options)
    session.commit()
    job_id = job.id
    t0 = time.time()
    job = await run_job(session, job_id, worker_id="phase7-remeasure")
    session.commit()
    report = build_report(session, job)
    pages = session.query(Page).filter(Page.job_id == job_id).all()
    summary = {
        "phase": 7,
        "purpose": "post_publish_llm_mention_remeasure",
        "job_id": job_id,
        "status": job.status,
        "base_url": job.base_url,
        "demo_mode": bool(job.demo_mode),
        "page_count": len(pages),
        "page_urls": [p.url for p in pages],
        "paid_retrieval_opt_in": False,
        "provider_requested": options.get("provider"),
        "selection_seed": options.get("selection_seed"),
        "do_key_present": bool(settings.effective_do_api_key),
        "openai_key_present": bool(settings.openai_api_key),
        "adr026_gate": "closed",
        "elapsed_s": round(time.time() - t0, 1),
        "report_keys": sorted(report.keys()),
        "content_optimization_status": (report.get("content_optimization") or {}).get(
            "status"
        ),
        "error_message": job.error_message,
        "causal_claim": "NOT_ESTABLISHED",
    }
    session.close()
    return {"summary": summary, "report": report}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--db", default="sqlite:////tmp/aeo_phase7_remeasure.db")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument(
        "--allow-unpublished-remeasure",
        action="store_true",
        help="Run even if PHASE7_PUBLISH_STATUS.json has published=false (diagnostics only).",
    )
    ap.add_argument(
        "--print-options-only",
        action="store_true",
        help="Print locked job options JSON and exit (no network).",
    )
    args = ap.parse_args()

    options = baseline_remeasure_options(
        seed=args.seed, paid_retrieval_opt_in=False, max_pages=args.max_pages
    )

    if args.print_options_only:
        payload = {
            "options": options,
            "baseline_confirmed_present": BASELINE_CONFIRMED.is_file(),
            "publish_status": load_publish_status(),
        }
        print(json.dumps(payload, indent=2))
        return 0

    pub = load_publish_status()
    if not pub.get("published") and not args.allow_unpublished_remeasure:
        print(
            json.dumps(
                {
                    "error": "refusing_remeasure_until_published",
                    "publish_status": pub,
                    "hint": "Set published=true after live Hashnode publish, or pass "
                    "--allow-unpublished-remeasure for diagnostics only.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    result = asyncio.run(_run(args.url, options, args.db))
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "PHASE7_POST_PUBLISH_JOB_SUMMARY.json").write_text(
        json.dumps(result["summary"], indent=2) + "\n", encoding="utf-8"
    )
    (out / "PHASE7_POST_PUBLISH_REPORT_EXCERPT.json").write_text(
        json.dumps(_slim(result["report"]), indent=2, default=str)[:3_000_000] + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], indent=2))
    return 0 if result["summary"].get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
