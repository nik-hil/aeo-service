#!/usr/bin/env python3
"""PR #45 H1-fix live acceptance: Hashnode .md + paid LLM + paid DO web search.

Supports dual-model comparison:
  baseline  = openai-gpt-4o-mini  (P45E / OPENAI_MODEL path default on DO inference)
  stronger  = openai-gpt-4o       (Settings.do_inference_model default)

Fail-closed without DO_MODEL_ACCESS_KEY (or OPENAI_API_KEY). Explicitly enables
AEO_PAID_RETRIEVAL_OPT_IN for this acceptance script only. Never uses demo provider.

Usage:
  python3 scripts/run_p45_h1_paid_md_acceptance.py              # both models
  python3 scripts/run_p45_h1_paid_md_acceptance.py --only baseline
  python3 scripts/run_p45_h1_paid_md_acceptance.py --only stronger
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SEED_MD = (
    "https://nik-hil.hashnode.dev/"
    "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md"
)

# Documented model pair for this acceptance (repo-supported DO Inference ids).
BASELINE_MODEL = "openai-gpt-4o-mini"  # P45E paid path / chat default on DO
STRONGER_MODEL = "openai-gpt-4o"  # Settings.do_inference_model default (stronger)


def _sanitize_model(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", model.strip()) or "model"


def _require_paid_key() -> dict:
    do_key = (
        os.environ.get("DO_MODEL_ACCESS_KEY")
        or os.environ.get("MODEL_ACCESS_KEY")
        or ""
    ).strip()
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    llm_key = do_key or openai_key
    if not llm_key:
        raise SystemExit(
            "FAIL_closed: DO_MODEL_ACCESS_KEY (or OPENAI_API_KEY) required for "
            "paid LLM + paid DO web search acceptance"
        )
    if (os.environ.get("AEO_DEMO_MODE") or "").strip().lower() in {"1", "true", "yes"}:
        raise SystemExit("FAIL_closed: AEO_DEMO_MODE must be false")
    # Explicit opt-in for this acceptance script (ADR-026 master switch).
    os.environ["AEO_PAID_RETRIEVAL_OPT_IN"] = "true"
    os.environ["AEO_DEMO_MODE"] = "false"
    if do_key and not openai_key:
        os.environ["OPENAI_API_KEY"] = do_key
    os.environ.setdefault(
        "OPENAI_BASE_URL",
        (os.environ.get("DO_INFERENCE_BASE_URL") or "https://inference.do-ai.run/v1").strip(),
    )
    os.environ.setdefault(
        "DO_INFERENCE_BASE_URL",
        "https://inference.do-ai.run/v1",
    )
    return {
        "do_key_present": bool(do_key),
        "openai_key_present": bool((os.environ.get("OPENAI_API_KEY") or "").strip()),
        "openai_base_url": os.environ.get("OPENAI_BASE_URL"),
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


async def _run_one(*, label: str, model: str, creds: dict, out: Path, ts: str) -> dict:
    from aeo_mvp.config import get_settings
    from aeo_mvp.db.models import Page
    from aeo_mvp.db.session import get_session_factory, init_db, reset_engine
    from aeo_mvp.pipeline.orchestrator import create_job_record, run_job
    from aeo_mvp.report.builder import build_report

    os.environ["OPENAI_MODEL"] = model
    os.environ["DO_INFERENCE_MODEL"] = model
    os.environ["AEO_PAID_RETRIEVAL_OPT_IN"] = "true"
    os.environ["AEO_DEMO_MODE"] = "false"

    db_url = os.environ.get("AEO_DATABASE_URL") or f"sqlite:///{ROOT / f'aeo_mvp_p45_h1_{label}.db'}"
    os.environ["AEO_DATABASE_URL"] = db_url
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
        "llm_model": model,
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
    print(f"[{label}] created job_id={job_id} model={model}", flush=True)
    t0 = time.time()
    job = await run_job(session, job_id, worker_id=f"p45-h1-{label}")
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
    flags = bucket.get("draft_flags") or {}
    rewrite_ready = [
        o
        for o in bucket["section_ops"]
        if o.get("op_kind") == "rewrite_section" and o.get("status") == "ready"
    ]
    targets = [o.get("target") for o in rewrite_ready]
    llm_used = bool(flags.get("llm_used")) or any(o.get("llm_used") for o in rewrite_ready)
    paid_llm = bool(flags.get("paid_llm")) or llm_used
    stub = bool(flags.get("stub_hint"))
    current_md = bucket["current_md"]
    recommended_md = bucket["recommended_md"]
    model_slug = _sanitize_model(model)

    prefix = f"{ts}_{label}_{model_slug}"
    if current_md:
        (out / f"{prefix}_current.md").write_text(current_md)
    if recommended_md:
        (out / f"{prefix}_recommended.md").write_text(recommended_md)
    diff_bytes = 0
    if current_md and recommended_md:
        diff = "".join(
            difflib.unified_diff(
                current_md.splitlines(True),
                recommended_md.splitlines(True),
                fromfile="CURRENT.md",
                tofile="RECOMMENDED.md",
            )
        )
        (out / f"{prefix}_current_vs_recommended.diff").write_text(diff)
        diff_bytes = len(diff)

    summary = {
        "label": label,
        "model": model,
        "job_id": job_id,
        "status": job.status,
        "error_message": job.error_message,
        "elapsed_sec": round(elapsed, 2),
        "page_urls": [p.url for p in pages],
        "options": options,
        "credentials": creds,
        "web_search": "ON (digitalocean_web_search)",
        "AEO_PAID_RETRIEVAL_OPT_IN": True,
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
        "diff_bytes": diff_bytes,
        "current_ne_recommended": bool(recommended_md) and current_md != recommended_md,
        "artifact_prefix": prefix,
    }
    summary["VERDICT"] = (
        "PASS"
        if (
            job.status == "completed"
            and paid_llm
            and not stub
            and rewrite_ready
            and summary["current_ne_recommended"]
        )
        else "FAIL"
    )
    # Publishability heuristic (not a publish action)
    if summary["VERDICT"] != "PASS":
        summary["would_publish"] = False
        summary["would_publish_reason"] = "acceptance VERDICT != PASS"
    elif summary.get("repeated_section_target"):
        summary["would_publish"] = False
        summary["would_publish_reason"] = "repeated rewrite_section target"
    else:
        summary["would_publish"] = True
        summary["would_publish_reason"] = (
            "paid grounded section ops applied to distinct targets; review before publish"
        )

    (out / f"{prefix}_report.json").write_text(json.dumps(summary, indent=2) + "\n")
    session.close()
    print(json.dumps({k: summary[k] for k in (
        "label", "model", "job_id", "status", "VERDICT", "rewrite_section_targets",
        "llm_used", "paid_llm", "stub", "would_publish"
    )}, indent=2), flush=True)
    return summary


def _write_comparison(out: Path, ts: str, tip: str, runs: list[dict]) -> None:
    by_label = {r["label"]: r for r in runs}
    base = by_label.get("baseline")
    strong = by_label.get("stronger")
    lines = [
        f"# P45 H1 fix — model comparison (`{ts}`)",
        "",
        f"- **Tip SHA:** `{tip}`",
        f"- **URL:** {SEED_MD}",
        "- **Web search:** ON (`AEO_PAID_RETRIEVAL_OPT_IN=true`, provider=`digitalocean_web_search`)",
        f"- **Baseline model:** `{BASELINE_MODEL}`",
        f"- **Stronger model:** `{STRONGER_MODEL}`",
        "",
        "## Side-by-side",
        "",
        "| Field | Baseline | Stronger |",
        "|-------|----------|----------|",
    ]

    def cell(run: dict | None, key: str):
        if not run:
            return "—"
        v = run.get(key)
        if isinstance(v, list):
            return ", ".join(str(x) for x in v) or "∅"
        return str(v)

    for key, label in [
        ("model", "model"),
        ("job_id", "job_id"),
        ("status", "status"),
        ("VERDICT", "VERDICT"),
        ("llm_used", "llm_used"),
        ("paid_llm", "paid_llm"),
        ("stub", "stub"),
        ("method", "method"),
        ("rewrite_section_targets", "rewrite_section targets"),
        ("repeated_section_target", "repeated_section_target"),
        ("current_chars", "current_chars"),
        ("recommended_chars", "recommended_chars"),
        ("diff_bytes", "diff_bytes"),
        ("elapsed_sec", "elapsed_sec"),
        ("would_publish", "would_publish"),
        ("would_publish_reason", "would_publish_reason"),
    ]:
        lines.append(f"| {label} | {cell(base, key)} | {cell(strong, key)} |")

    lines.extend(
        [
            "",
            "## Qualitative notes",
            "",
            "- Selection correctness (H1 fix): both runs must target distinct local sections "
            "(e.g. complete-flow → `# The complete flow`, not the H3 mega-span).",
            "- Repeated-section dumping: see `repeated_section_target`.",
            "- Publishability: neither run publishes; `would_publish` is a review heuristic only.",
            "",
        ]
    )
    if base and strong:
        bt = set(base.get("rewrite_section_targets") or [])
        st = set(strong.get("rewrite_section_targets") or [])
        lines.append(f"- Target overlap: `{sorted(bt & st)}`")
        lines.append(f"- Baseline-only targets: `{sorted(bt - st)}`")
        lines.append(f"- Stronger-only targets: `{sorted(st - bt)}`")
        lines.append("")
        if (base.get("recommended_chars") or 0) and (strong.get("recommended_chars") or 0):
            delta = (strong["recommended_chars"] or 0) - (base["recommended_chars"] or 0)
            lines.append(f"- Recommended char delta (stronger − baseline): **{delta}**")
    (out / f"{ts}_model_comparison.md").write_text("\n".join(lines) + "\n")


async def _main_async(only: str | None) -> int:
    creds = _require_paid_key()
    tip = os.popen("git rev-parse HEAD").read().strip()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = ROOT / f"docs/aeo-p45-h1-fix-{ts}"
    out.mkdir(parents=True, exist_ok=True)

    plan = []
    if only in (None, "baseline"):
        plan.append(("baseline", BASELINE_MODEL))
    if only in (None, "stronger"):
        plan.append(("stronger", STRONGER_MODEL))

    runs = []
    for label, model in plan:
        runs.append(await _run_one(label=label, model=model, creds=creds, out=out, ts=ts))

    if len(runs) >= 2:
        _write_comparison(out, ts, tip, runs)

    overall = {
        "tip_sha": tip,
        "pr": 45,
        "branch": "cursor/substantive-content-opt-e95e",
        "url": SEED_MD,
        "timestamp": ts,
        "baseline_model": BASELINE_MODEL,
        "stronger_model": STRONGER_MODEL,
        "runs": runs,
        "VERDICT": (
            "PASS"
            if runs and all(r.get("VERDICT") == "PASS" for r in runs)
            else "FAIL"
        ),
    }
    (out / "acceptance_report.json").write_text(json.dumps(overall, indent=2) + "\n")
    (out / "README.md").write_text(
        f"""# P45 H1 fix — dual-model paid acceptance

- **Tip SHA:** `{tip}`
- **URL (md only):** {SEED_MD}
- **paid LLM + paid DO web search:** required (both runs)
- **Baseline model:** `{BASELINE_MODEL}`
- **Stronger model:** `{STRONGER_MODEL}`
- **Overall VERDICT:** {overall['VERDICT']}

## Artifacts

Per run: `{{ts}}_{{baseline|stronger}}_{{model}}_current.md`, `_recommended.md`, `_current_vs_recommended.diff`, `_report.json`.

Comparison: `{ts}_model_comparison.md`

## Runs

"""
        + "\n".join(
            f"- **{r['label']}** `{r['model']}` job `{r['job_id']}` → {r['VERDICT']}; "
            f"targets={r.get('rewrite_section_targets')}; would_publish={r.get('would_publish')}"
            for r in runs
        )
        + "\n"
    )
    print("ARTIFACT_DIR", out)
    print(json.dumps({"VERDICT": overall["VERDICT"], "runs": [
        {"label": r["label"], "model": r["model"], "VERDICT": r["VERDICT"], "job_id": r["job_id"]}
        for r in runs
    ]}, indent=2))
    return 0 if overall["VERDICT"] == "PASS" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", choices=["baseline", "stronger"], default=None)
    args = ap.parse_args()
    return asyncio.run(_main_async(args.only))


if __name__ == "__main__":
    raise SystemExit(main())
