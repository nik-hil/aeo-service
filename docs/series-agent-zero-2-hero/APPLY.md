# Apply RECOMMENDED Markdown to Hashnode

Each `*-RECOMMENDED.md` file in this directory is **paste-ready** for the matching Hashnode post.

## Steps

1. Open the live post on Hashnode (or the Hashnode Markdown editor for that slug).
2. Open the matching `agents-zero-to-hero-N-…-RECOMMENDED.md` from this directory (see `MANIFEST.json` for slug ↔ file mapping).
3. Replace the post body with the full contents of the RECOMMENDED file.
4. Preview, then publish / update.

Do **not** edit `src/`, `ui/`, tests, or dependencies to apply these changes — paste into Hashnode only.

## Truncation caveat (#9 and #10)

For posts **#9** (context management) and **#10** (skills on demand), the Hashnode `.md` endpoint used as AEO input is truncated compared with the HTML article. The RECOMMENDED files for those two posts follow that truncated source. Re-run AEO against full Markdown (or HTML-derived Markdown) before treating #9/#10 as complete replacements of the live HTML posts.

## Series

https://nik-hil.hashnode.dev/series/agent-zero-2-hero
