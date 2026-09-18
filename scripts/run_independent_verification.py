#!/usr/bin/env python3
"""Independent verification harness (P0 + P1 sections).

Starts checks: import app, run demo job, recompute health, assert
experiment_kind/retrieval_enabled, P1 report sections, pytest subset.
Writes docs/verification/VERIFY-COMPLETE-DRAFT.md (full Verifier sign-off later).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "verification" / "VERIFY-COMPLETE-DRAFT.md"

P1_KEYS = (
    "ai_crawler_access",
    "site_understanding",
    "discovered_queries",
    "executive_summary",
    "page_findings",
)


def _section(name: str, ok: bool, details: str) -> dict:
    return {"name": name, "status": "PASS" if ok else "FAIL", "details": details}


def _write(results: list[dict], extra_fail: str | None = None) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    overall = "PASS" if results and all(x["status"] == "PASS" for x in results) else "FAIL"
    lines = [
        "# VERIFY-COMPLETE-DRAFT",
        "",
        f"**Generated:** {now}",
        "**Harness:** `scripts/run_independent_verification.py`",
        "**Note:** Draft only — full Verifier sign-off comes later.",
        "",
        f"**Overall:** {overall}",
        "",
    ]
    if extra_fail:
        lines += [f"> Abort: {extra_fail}", ""]
    lines.append("## Results")
    lines.append("")
    for r in results:
        lines.append(f"### {r['status']}: {r['name']}")
        lines.append("")
        lines.append("```")
        lines.append((r["details"] or "")[:2000])
        lines.append("```")
        lines.append("")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT} overall={overall}")


def main() -> int:
    results: list[dict] = []

    try:
        from aeo_mvp.api.app import create_app

        app = create_app()
        results.append(_section("import_app", True, f"create_app ok; routes={len(app.routes)}"))
    except Exception as exc:  # noqa: BLE001
        results.append(_section("import_app", False, str(exc)))
        _write(results, extra_fail="Import failed; aborting remaining checks.")
        return 1

    try:
        from aeo_mvp.config import get_settings
        from aeo_mvp.db.models import Report, ScoreComponent, VisibilityObservation
        from aeo_mvp.db.session import get_session_factory, init_db, reset_engine
        from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record
        from aeo_mvp.scoring.health import health_from_components

        get_settings.cache_clear()
        reset_engine()
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        url = f"sqlite:///{tmp.name}"
        os.environ["AEO_DATABASE_URL"] = url
        get_settings.cache_clear()
        reset_engine()
        init_db(url)
        factory = get_session_factory(url)
        session = factory()
        job = create_job_record(
            session,
            "https://demo.example/",
            demo_mode=True,
            options={"provider": "demo", "runs_per_prompt": 3},
        )
        session.commit()
        asyncio.run(JobOrchestrator(session).run(job.id))
        session.commit()
        session.refresh(job)
        report_row = session.query(Report).filter_by(job_id=job.id).one()
        data = json.loads(report_row.report_json)
        exp = data.get("experiment") or {}
        ok = (
            job.status == "completed"
            and exp.get("experiment_kind") == "llm_mention"
            and exp.get("retrieval_enabled") is False
            and "llm_mention_rate" in exp
            and "ai_mention_rate" not in exp
        )
        results.append(
            _section(
                "demo_job",
                ok,
                f"status={job.status} experiment_kind={exp.get('experiment_kind')} "
                f"retrieval_enabled={exp.get('retrieval_enabled')} "
                f"keys={sorted(exp.keys())}",
            )
        )

        missing = [k for k in P1_KEYS if k not in data]
        p1_ok = not missing
        if p1_ok:
            p1_ok = bool(data["ai_crawler_access"].get("agents"))
            p1_ok = p1_ok and bool(data["site_understanding"].get("organization_brand"))
            p1_ok = p1_ok and bool(data["discovered_queries"].get("queries"))
            p1_ok = p1_ok and "overall_health" in data["executive_summary"]
            recs = data.get("recommendations") or []
            p1_ok = p1_ok and bool(recs) and bool(recs[0].get("recommended_action"))
        results.append(
            _section(
                "p1_report_sections",
                p1_ok,
                f"missing={missing} "
                f"agents={len((data.get('ai_crawler_access') or {}).get('agents') or [])} "
                f"brand={(data.get('site_understanding') or {}).get('organization_brand')} "
                f"dq={len((data.get('discovered_queries') or {}).get('queries') or [])} "
                f"exec_keys={sorted((data.get('executive_summary') or {}).keys())}",
            )
        )

        comps = {
            r.component: r.score
            for r in session.query(ScoreComponent).filter_by(job_id=job.id).all()
        }
        needed = ["technical", "content", "entity", "structured_data", "answerability"]
        if all(k in comps for k in needed):
            recomputed = health_from_components(
                comps["technical"],
                comps["content"],
                comps["entity"],
                comps["structured_data"],
                comps["answerability"],
            )
            stored = comps.get("health")
            match = stored is not None and abs(float(stored) - float(recomputed)) < 0.05
            results.append(
                _section("health_recompute", match, f"stored={stored} recomputed={recomputed}")
            )
        else:
            results.append(_section("health_recompute", False, f"components={sorted(comps)}"))

        obs = session.query(VisibilityObservation).filter_by(job_id=job.id).all()
        obs_ok = bool(obs) and all(
            (o.experiment_kind == "llm_mention" and int(o.retrieval_enabled or 0) == 0) for o in obs
        )
        results.append(
            _section("observation_flags", obs_ok, f"n={len(obs)} ok={obs_ok}")
        )

        # Honesty: no false AI-search claims in report blob
        blob = json.dumps(data)
        banned = ["ChatGPT ranking", "official AI share of voice", "ai_mention_rate"]
        honest = all(b not in blob for b in banned)
        results.append(_section("no_false_ai_search_claims", honest, f"banned_checked={banned}"))

        session.close()
        reset_engine()
        get_settings.cache_clear()
    except Exception as exc:  # noqa: BLE001
        results.append(_section("demo_job", False, repr(exc)))

    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/unit/test_ssrf.py",
                "tests/unit/test_scoring.py",
                "tests/unit/test_ai_crawlers.py",
                "tests/unit/test_site_understanding.py",
                "tests/unit/test_query_discovery.py",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        ok = proc.returncode == 0
        tail = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-1200:]
        results.append(_section("pytest_ssrf_scoring_p1", ok, tail.strip()))
    except Exception as exc:  # noqa: BLE001
        results.append(_section("pytest_ssrf_scoring_p1", False, repr(exc)))

    _write(results)
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
