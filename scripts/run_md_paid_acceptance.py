#!/usr/bin/env python3
"""CoS re-run: live MD-URI analysis with paid DO web_search (ADR-026).

Usage (on a box with secrets):
  export AEO_API_KEY=...
  export AEO_PAID_RETRIEVAL_OPT_IN=true          # ADR-026 master switch
  export DO_MODEL_ACCESS_KEY=...               # or MODEL_ACCESS_KEY
  export AEO_VISIBILITY_PROVIDER=digitalocean_web_search   # optional; auto also OK
  # Optional LLM draft path (still refuse-live stub unless implemented):
  export OPENAI_API_KEY=...                    # only if exercising openai_compatible
  export AEO_API_BASE_URL=http://127.0.0.1:8000

  # API must be started with the SAME env (master switch is read at process start):
  uvicorn aeo_mvp.api.app:app --host 127.0.0.1 --port 8000

  python3 scripts/run_md_paid_acceptance.py

Outputs under /opt/cursor/artifacts/md-paid-acceptance/ (or ARTIFACT_DIR).

Constraints:
- Seeds ONLY the Hashnode .md URI (not HTML).
- Does NOT publish to Hashnode.
- Fail-closed: if AEO_PAID_RETRIEVAL_OPT_IN is false or DO key missing, exits non-zero
  after writing credential_probe.json (unless ALLOW_UNPAID_FALLBACK=1).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

MD_URL = (
    "https://nik-hil.hashnode.dev/"
    "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md"
)
ARTIFACT_DIR = Path(
    os.environ.get("ARTIFACT_DIR", "/opt/cursor/artifacts/md-paid-acceptance")
)


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def probe_credentials() -> dict:
    do_key = os.environ.get("DO_MODEL_ACCESS_KEY") or os.environ.get("MODEL_ACCESS_KEY")
    probe = {
        "AEO_PAID_RETRIEVAL_OPT_IN": _truthy(os.environ.get("AEO_PAID_RETRIEVAL_OPT_IN")),
        "DO_MODEL_ACCESS_KEY_or_MODEL_ACCESS_KEY": bool(do_key),
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "AEO_VISIBILITY_PROVIDER": os.environ.get("AEO_VISIBILITY_PROVIDER") or "auto",
        "md_url": MD_URL,
        "paid_path_ready": _truthy(os.environ.get("AEO_PAID_RETRIEVAL_OPT_IN"))
        and bool(do_key),
    }
    return probe


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    probe = probe_credentials()
    (ARTIFACT_DIR / "credential_probe.json").write_text(
        json.dumps(probe, indent=2) + "\n", encoding="utf-8"
    )
    allow_unpaid = _truthy(os.environ.get("ALLOW_UNPAID_FALLBACK"))
    if not probe["paid_path_ready"] and not allow_unpaid:
        (ARTIFACT_DIR / "STATUS.txt").write_text(
            "BLOCKED: paid credentials / ADR-026 master switch not ready.\n"
            "Set AEO_PAID_RETRIEVAL_OPT_IN=true and DO_MODEL_ACCESS_KEY "
            "(or MODEL_ACCESS_KEY), restart API, re-run.\n"
            "Or set ALLOW_UNPAID_FALLBACK=1 to capture MD CURRENT/RECOMMENDED/Q&O "
            "without paid DO retrieval.\n",
            encoding="utf-8",
        )
        print(json.dumps(probe, indent=2))
        print("BLOCKED_PAID_PATH — see", ARTIFACT_DIR / "STATUS.txt")
        return 2

    base = (os.environ.get("AEO_API_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
    key = os.environ.get("AEO_API_KEY") or ""
    if not key:
        print("AEO_API_KEY required", file=sys.stderr)
        return 2
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}

    options = {
        "mode": "single",
        "max_pages": 1,
        "max_depth": 0,
        "content_optimization": True,
        "content_draft": True,
        # Request opt-in; env master switch still wins (ADR-026).
        "paid_retrieval_opt_in": True,
        # Paid path: digitalocean_web_search. Unpaid fallback: auto (demo if no keys).
        "provider": (
            os.environ.get("AEO_VISIBILITY_PROVIDER")
            or (
                "digitalocean_web_search"
                if probe["paid_path_ready"]
                else "auto"
            )
        ),
        "draft_paid": bool(os.environ.get("OPENAI_API_KEY")),
        "paid_llm_opt_in": bool(os.environ.get("OPENAI_API_KEY")),
    }

    with httpx.Client(base_url=base, headers=headers, timeout=300.0) as client:
        r = client.post(
            "/api/v1/jobs",
            json={"url": MD_URL, "demo_mode": False, "options": options},
        )
        r.raise_for_status()
        job_id = r.json()["id"]
        (ARTIFACT_DIR / "job_id.txt").write_text(job_id, encoding="utf-8")
        print("job", job_id)

        status = "pending"
        payload: dict = {}
        for i in range(180):
            payload = client.get(f"/api/v1/jobs/{job_id}").json()
            status = str(payload.get("status") or "")
            if i % 5 == 0 or status in {"completed", "failed"}:
                print(i, status, payload.get("error_message"))
            if status in {"completed", "failed"}:
                break
            time.sleep(2)
        (ARTIFACT_DIR / "job_status.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        if status != "completed":
            (ARTIFACT_DIR / "STATUS.txt").write_text(
                f"JOB_FAILED status={status}\n", encoding="utf-8"
            )
            return 1

        report = client.get(f"/api/v1/jobs/{job_id}/report").json()
        pages = client.get(f"/api/v1/jobs/{job_id}/pages").json()
        (ARTIFACT_DIR / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        (ARTIFACT_DIR / "pages.json").write_text(
            json.dumps(pages, indent=2) + "\n", encoding="utf-8"
        )

        items = pages.get("pages") if isinstance(pages, dict) else pages
        page = (items or [{}])[0]
        page_id = page.get("id")
        page_url = page.get("url")
        rep = page.get("content_representation")
        src_md = page.get("source_markdown")
        (ARTIFACT_DIR / "page_meta.json").write_text(
            json.dumps(
                {
                    "page_id": page_id,
                    "url": page_url,
                    "content_representation": rep,
                    "source_markdown_chars": len(src_md or ""),
                    "seed_was_md_uri": MD_URL.endswith(".md"),
                    "paid_retrieval_report": report.get("paid_retrieval"),
                    "experiment": report.get("experiment"),
                    "visibility_disclaimer": (report.get("experiment") or {}).get(
                        "disclaimer"
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if src_md:
            (ARTIFACT_DIR / "current_source_markdown.md").write_text(
                src_md, encoding="utf-8"
            )

        opt = client.post(
            "/api/v1/content-optimization",
            json={"job_id": job_id, "page_id": page_id, "content_draft": True},
        )
        opt.raise_for_status()
        wire = opt.json()
        (ARTIFACT_DIR / "content_optimization.json").write_text(
            json.dumps(wire, indent=2) + "\n", encoding="utf-8"
        )

        pi = wire.get("page_intelligence") or report.get("page_intelligence") or {}
        current = (
            pi.get("source_markdown")
            or src_md
            or pi.get("recommended_markdown")  # never prefer this for CURRENT
            or ""
        )
        # Prefer page-store source_markdown for CURRENT
        current = src_md or pi.get("source_markdown") or ""
        drafts = wire.get("content_drafts") or report.get("content_drafts") or []
        recommended = ""
        if drafts and isinstance(drafts[0], dict):
            recommended = (
                drafts[0].get("body_markdown")
                or drafts[0].get("recommended_markdown")
                or ""
            )
        recommended = (
            recommended
            or (pi.get("recommended_markdown") or "")
            or ""
        )
        (ARTIFACT_DIR / "CURRENT.md").write_text(current or "", encoding="utf-8")
        (ARTIFACT_DIR / "RECOMMENDED.md").write_text(
            recommended or "", encoding="utf-8"
        )

        qoa = wire.get("question_opportunity_analysis") or report.get(
            "question_opportunity_analysis"
        )
        if qoa:
            (ARTIFACT_DIR / "question_opportunity_analysis.json").write_text(
                json.dumps(qoa, indent=2) + "\n", encoding="utf-8"
            )
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
                from aeo_mvp.content.question_opportunities import (  # noqa: WPS433
                    analysis_to_markdown,
                )

                (ARTIFACT_DIR / "qoa_section.md").write_text(
                    analysis_to_markdown(qoa), encoding="utf-8"
                )
            except Exception as exc:  # noqa: BLE001
                (ARTIFACT_DIR / "qoa_section.md").write_text(
                    f"(render failed: {exc})\n", encoding="utf-8"
                )

        # Diff summary (intro-focused + size)
        def _intro(text: str, n: int = 40) -> str:
            lines = (text or "").splitlines()
            return "\n".join(lines[:n])

        diff_note = {
            "current_chars": len(current or ""),
            "recommended_chars": len(recommended or ""),
            "identical": (current or "").strip() == (recommended or "").strip(),
            "current_intro": _intro(current or ""),
            "recommended_intro": _intro(recommended or ""),
            "qoa_question_count": len((qoa or {}).get("questions") or []),
            "paid_path_ready": probe["paid_path_ready"],
            "allow_unpaid_fallback": allow_unpaid,
            "representation": rep,
        }
        (ARTIFACT_DIR / "diff_summary.json").write_text(
            json.dumps(diff_note, indent=2) + "\n", encoding="utf-8"
        )
        (ARTIFACT_DIR / "STATUS.txt").write_text(
            "OK\n" if probe["paid_path_ready"] else "OK_UNPAID_FALLBACK\n",
            encoding="utf-8",
        )
        print("wrote artifacts to", ARTIFACT_DIR)
        print(
            "qoa=",
            diff_note["qoa_question_count"],
            "rep=",
            rep,
            "paid_ready=",
            probe["paid_path_ready"],
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
