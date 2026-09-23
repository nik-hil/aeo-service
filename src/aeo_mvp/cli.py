"""CLI: python -m aeo_mvp.cli <md> --domain ... [--live] --out <dir>"""

from __future__ import annotations

import argparse
import json
import sys

from aeo_mvp.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Hashnode Markdown AEO PoC (LLM semantics + DO web_search plumbing)"
    )
    p.add_argument("markdown", help="Path to Hashnode .md file")
    p.add_argument("--domain", default=None, help="Target domain for visibility")
    p.add_argument(
        "--live",
        action="store_true",
        help="Enable DigitalOcean web_search visibility (requires AEO_LLM_API_KEY)",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Write CURRENT.md, RECOMMENDED.md, DIFF.patch, report.json",
    )
    p.add_argument(
        "--skip-quality-eval",
        action="store_true",
        help="Skip final LLM quality evaluation step",
    )
    args = p.parse_args(argv)

    report = run_pipeline(
        args.markdown,
        target_domain=args.domain,
        dry_run=not args.live,
        skip_quality_eval=args.skip_quality_eval,
        write_artifacts_dir=args.out,
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
