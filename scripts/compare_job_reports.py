#!/usr/bin/env python3
"""Compare two AEO job reports (baseline vs post) using aeo-before-after-v1.

Usage:
  python scripts/compare_job_reports.py baseline.json post.json [--out result.json]

Does not claim causality. Prints evidence_class and deltas.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aeo_mvp.measurement.before_after import (  # noqa: E402
    PostChangeSnapshot,
    compare_snapshots,
    extract_baseline_from_report,
    mappings_from_brief,
)


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Expected object JSON in {path}")
    # Allow wrapping {report: {...}} or Phase 4 live summary shapes
    if "report" in data and isinstance(data["report"], dict):
        return data["report"]
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("baseline", type=Path)
    ap.add_argument("post", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--change-source",
        choices=("live_cms", "fixture_simulated", "unknown"),
        default="unknown",
    )
    args = ap.parse_args()

    base_report = _load(args.baseline)
    post_report = _load(args.post)

    baseline = extract_baseline_from_report(base_report, source=str(args.baseline))
    post_base = extract_baseline_from_report(post_report, source=str(args.post))
    post = PostChangeSnapshot.from_baseline(
        post_base,
        change_source=args.change_source,  # type: ignore[arg-type]
        applied_recommendation_ids=[],
    )

    mappings = []
    for brief in post_report.get("optimization_briefs") or base_report.get(
        "optimization_briefs"
    ) or []:
        if isinstance(brief, dict):
            mappings.extend(mappings_from_brief(brief))

    result = compare_snapshots(baseline, post, mappings=mappings)
    payload = result.to_dict()
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(
        f"\n# evidence_class={result.evidence_class} "
        f"rationale={result.evidence_rationale}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
