# Agents Zero to Hero — AEO RECOMMENDED Markdown

Paste-ready Hashnode Markdown for the **Agents Zero to Hero** series, produced by the live AEO PoC.

| | |
| --- | --- |
| Source series | https://nik-hil.hashnode.dev/series/agent-zero-2-hero |
| Domain | `nik-hil.hashnode.dev` |
| Pipeline | Live AEO on CoS box (`--live`); **ok=13**, **fail=0** |
| Content discovery | Sitemap → 13 `…/slug.md` URIs (series HTML is not crawlable by this PoC) |

## Contents

- `APPLY.md` — how to publish each file back to Hashnode
- `MANIFEST.json` — file inventory and per-article metadata
- `RERUN-NOTES.md` — #9/#10 slug republish and truncated-file replacement
- 13 `*-RECOMMENDED.md` files — optimized Markdown, one per series post

## #9 and #10 republish

Articles **#9** and **#10** were republished on Hashnode under new slugs with full Markdown (the original posts were truncated mid-sentence). Live AEO was re-run against the full sources. Old truncated recommendation filenames were removed; see `RERUN-NOTES.md`.

| n | New slug / md URL |
| --- | --- |
| 9 | https://nik-hil.hashnode.dev/agents-zero-to-hero-9-building-context-compaction-for-ai-agents.md |
| 10 | https://nik-hil.hashnode.dev/agents-zero-to-hero-10-building-on-demand-skills-for-ai-agents.md |

## Docs only

This directory is documentation output only. It does not change application code under `src/`, `ui/`, tests, or dependencies.
