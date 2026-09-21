# AEO Leadership Demo UI (Gradio)

Polished B2B demo UI for leadership walkthroughs of the AEO MVP.  
**Presentation only** — no scoring, crawl, or SSRF logic lives here. The UI talks exclusively to the secured FastAPI API.

## Start

### 1. API

```bash
cd /workspace   # or repo root
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ui]"
export AEO_API_KEY=dev-local-key-change-me
uvicorn aeo_mvp.api.app:app --host 127.0.0.1 --port 8000
```

### 2. Gradio UI

```bash
source .venv/bin/activate
export AEO_API_BASE_URL=http://127.0.0.1:8000
export AEO_API_KEY=dev-local-key-change-me
python ui/gradio/app.py
```

Open `http://127.0.0.1:7860` (laptop/desktop: 1366×768, 1440×900, 1920×1080).

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `AEO_API_BASE_URL` | `http://127.0.0.1:8000` | FastAPI base URL |
| `AEO_API_KEY` | _(empty)_ | Bearer token for API (required when API auth is on) |
| `AEO_UI_JOB_TIMEOUT` | `180` | Seconds to poll a job |
| `GRADIO_SERVER_NAME` | `127.0.0.1` | Bind host |
| `GRADIO_SERVER_PORT` | `7860` | Bind port |

## Demo vs real

| | Demo | Real URL |
| --- | --- | --- |
| Trigger | **▶ One-click demo** (or Analyze with demo fixtures via API `demo_mode=true`) | Paste `https://…` + Analyze |
| Network | No live crawl — fixtures under `src/aeo_mvp/demo/fixtures/` | API crawls same-host from seed (SSRF-guarded) |
| Provider | `options.provider=demo` | `auto` (or configured visibility providers) |
| Drafts | Requests deterministic skeleton draft when checkbox on | Same flag; paid LLM drafts are not implied |

The UI **never fetches the target URL itself**.

## Architecture

```
ui/gradio/
  app.py              # Gradio Blocks + job poll + async page enrichment
  glossary.py         # Executive ⓘ tips + technical glossary
  components/         # KPI cards + info helpers
  views/              # overview / page detail / analyze option builders
  services/
    api_client.py     # sync + async HTTP (AsyncClient for enrichment)
    enrichment.py     # selection tokens + session cache + bounded concurrency
    adapters.py       # report → view models (CURRENT vs RECOMMENDED)
    opportunities.py  # Biggest Opportunities ordering (documented)
    formatters.py     # KPI display
    sanitize.py       # escape / safe markdown / code fences
  styles/             # B2B theme + CSS (offline font fallbacks)
  tests/              # unit + async enrichment + XSS + integration
```

Gradio is an optional extra (`pip install -e ".[ui]"` or `.[demo-ui]`). Core API deps stay unchanged.

## Async page enrichment (post–PR #36 hardening)

Selecting a non-primary page used to call `content_optimization` **synchronously** and freeze the UI.

Now:

1. **Stage A (immediate):** page header + CURRENT/observed signals render right away. Recs / Brief / Evidence show localized “Additional optimization analysis loading…” — the page is never blanked.
2. **Stage B (async):** `AeoApiClient.content_optimization_async` uses **`httpx.AsyncClient`** (not a blocking Client inside `async def`).
3. **Selection token:** each select bumps `selection_id`; stale responses after A→B navigation are discarded.
4. **Session cache:** keyed by `job_id + page_id` on Gradio `State` (loading|success|error). Revisiting a page is instant; no process-global cross-user cache.
5. **First-page enrichment:** Analyze create/poll stays a **synchronous** generator. It is not fully async. When the first page still needs enrichment, that generator yields the report and CURRENT signals first, then calls enrichment in the **same** generator, then yields the panels. The enrichment call does not run before that first report yield.
6. **In-flight ownership:** ``claim`` on the session cache is atomic for one `job_id + page_id`. Only the owner POSTs. Concurrent handlers on that same session cache wait for SUCCESS or ERROR. A mutex serializes the claim; it does not store payloads and is not a cross-session cache. Cleanup removes only that owner's `LOADING` marker.
7. **Queue:** Gradio `queue(default_concurrency_limit=4)`; enrichment is not `queue=False`. In-process semaphore bounds concurrent enrichment calls.
8. **Errors:** 404/409/timeout/5xx map to user-safe copy; unexpected failures are logged. Observed signals stay visible.

Page selection is a separate async generator. Revisiting a cached page does not POST again.

## Multi-page `max_pages`

| Layer | Cap |
| --- | --- |
| **UI request (multi mode)** | **20** (`UI_MULTI_MAX_PAGES`) |
| Backend hard ceiling | **25** (`schemas.JobOptions.max_pages` `le=25`) |

The UI never requests more than 20. Demo fixtures still load the full fixture site (API ignores `max_pages` in demo mode) — overview copy notes this.

## Screens / product story

1. Brand + URL + mode (single page vs multi-page same-host crawl seed)
2. Status stages from real job status (honest labels — not fake percentages)
3. **KPI cards** (HTML): AEO Health, Entity Clarity, Visibility, Gaps, Opportunities — each with executive ⓘ tip
4. Overview markdown + Biggest Opportunities (deterministic; dropdown → page detail)
5. Pages table (multi-page; truncated URLs) + page selector + page-detail header (title/URL/status/depth)
6. Detail tabs: **CURRENT (observed)** → **Recommendations** → **Brief & Draft** → **CURRENT vs RECOMMENDED** → **Evidence**
7. Guide accordion: story + **technical details / full glossary** (methodology versions)

### Honesty labels

- **CURRENT** = observed page signals — **not a live browser render**
- **RECOMMENDED** = brief + suggested structure/draft when returned (skeleton / generated)
- Never labeled as a final optimized page
- Empty states for no recs / gaps / draft / evidence

### Biggest Opportunities ordering

See `services/opportunities.py`:

1. Recommendations by `rank` asc, then `-priority_score`, then `code`
2. Then high/medium content gaps not already covered by recommendation URLs
3. Cap at 8

## Tests

```bash
source .venv/bin/activate
pytest -q -rs
```

UI tests live under `ui/gradio/tests/` including `test_async_enrichment.py` (async HTTP, race discard, cache, rapid nav, 404/timeout, synthetic 20-page table).

**Note:** the folder is named `ui/gradio/` per layout requirement. Tests/conftest strip `.../ui` from `sys.path` so `import gradio` resolves to the third-party package, not this directory.

## Security

- No new SSRF surface — UI only calls `AEO_API_BASE_URL`
- External strings HTML-escaped before Markdown/HTML surfaces
- Raw HTML (if ever shown) only inside fenced code blocks
- XSS-style fixtures covered in `tests/test_sanitize.py`
- Offline-capable font stacks if Google Fonts CDN is blocked

## Known limits

- Laptop/desktop oriented; not a mobile product UI
- Demo mode always loads the full fixture site (API ignores max_pages for demo)
- `page_intelligence` on multi-page jobs is primary-page oriented; other pages use async `POST /content-optimization` enrichment
- Visibility metrics are sample estimates — not consumer ChatGPT/Gemini/Perplexity rankings
- No job cancel/list; poll-only progress
- Drafts default to deterministic skeleton when requested — not paid LLM prose unless the API is configured for that separately
- Prefetch covers only the first selected page, and only after the primary report is on screen

## Visual QA artifacts

Screenshots from runtime verification live under:

`docs/verification/artifacts/leadership-ui/`
