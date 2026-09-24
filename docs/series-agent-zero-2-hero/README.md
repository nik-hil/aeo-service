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
- 13 `*-RECOMMENDED.md` files — optimized Markdown, one per series post

## Caveat

Hashnode `.md` endpoints for **#9** and **#10** are truncated relative to the HTML articles. The corresponding `*-RECOMMENDED.md` files track that truncated source (they are not full-article rewrites of the HTML).

## Docs only

This directory is documentation output only. It does not change application code under `src/`, `ui/`, tests, or dependencies.
