"""CLI: python -m aeo_mvp.cli <md> --domain ... [--live] [--prompts-file ...] --out <dir>"""

from __future__ import annotations

import argparse
import json
import sys

from aeo_mvp.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Hashnode Markdown AEO PoC (LLM semantics + DO web_search plumbing). "
            "Visibility is OBSERVED DigitalOcean web_search only — not ChatGPT UI."
        )
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
        help=(
            "Write CURRENT.md, RECOMMENDED.md, DIFF.patch, SUMMARY.md, "
            "VISIBILITY.md, report.json"
        ),
    )
    p.add_argument(
        "--skip-quality-eval",
        action="store_true",
        help="Skip final LLM quality evaluation step",
    )
    p.add_argument(
        "--skip-accuracy",
        action="store_true",
        help="Skip brand-fact / accuracy pass (OBSERVED vs CURRENT)",
    )
    p.add_argument(
        "--prompts-file",
        default=None,
        help=(
            "Frozen prompt-set JSON file. When set, visibility uses these prompts "
            "instead of LLM query rediscovery. See docs/PROMPT_SET.md."
        ),
    )
    p.add_argument(
        "--competitors",
        default=None,
        help=(
            "Competitor brands for share metrics. Comma/newline separated "
            "'Name|domain' or 'Name:domain' (e.g. 'Acme|acme.com,Beta:beta.io')."
        ),
    )
    p.add_argument(
        "--competitors-file",
        default=None,
        help="Optional JSON file of competitors (see docs/PROMPT_SET.md).",
    )
    args = p.parse_args(argv)

    report = run_pipeline(
        args.markdown,
        target_domain=args.domain,
        dry_run=not args.live,
        skip_quality_eval=args.skip_quality_eval,
        skip_accuracy=args.skip_accuracy,
        write_artifacts_dir=args.out,
        prompts_file=args.prompts_file,
        competitors=args.competitors,
        competitors_file=args.competitors_file,
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
