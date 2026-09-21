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
  app.py              # Gradio Blocks composition + job orchestration (poll only)
  glossary.py         # ⓘ definitions + guide copy
  components/         # small presentation helpers
  views/              # overview / page detail / analyze option builders
  services/
    api_client.py     # thin HTTP client
    adapters.py       # report → view models
    opportunities.py  # Biggest Opportunities ordering (documented)
    formatters.py     # KPI display
    sanitize.py       # escape / safe markdown / code fences
  styles/             # B2B theme + CSS
  tests/              # unit + integration + security
```

Gradio is an optional extra (`pip install -e ".[ui]"` or `.[demo-ui]`). Core API deps stay unchanged.

## Screens / product story

1. Brand + URL + mode (single page vs multi-page same-host crawl seed)
2. Status stages (honest labels — not fake percentages)
3. Overview: AEO Health + components + visibility caveats
4. Biggest Opportunities (deterministic; click → page detail)
5. Pages table (multi-page) + page selector
6. Detail tabs: **Before** → **Recommendations** → **Brief & Draft** → **Evidence**
7. Guide accordion: “How to read this report” + full glossary

### Before / Brief & Draft honesty

- **Before** = observed/derived extracted signals (title, headings, answer blocks)
- **Brief & Draft** = content gaps (existing report fields) + optimization brief + draft when the API returns one
- Skeleton drafts labeled **Optimization Draft (deterministic skeleton)** — never “final optimized page”

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

UI tests live under `ui/gradio/tests/` (glossary, formatters, adapters, opportunities, sanitize/XSS, integration with mocks, stale-state clearing).

**Note:** the folder is named `ui/gradio/` per layout requirement. Tests/conftest strip `.../ui` from `sys.path` so `import gradio` resolves to the third-party package, not this directory.

## Security

- No new SSRF surface — UI only calls `AEO_API_BASE_URL`
- External strings HTML-escaped before Markdown/HTML surfaces
- Raw HTML (if ever shown) only inside fenced code blocks
- XSS-style fixtures covered in `tests/test_sanitize.py`

## Known limits

- Laptop/desktop oriented; not a mobile product UI
- Demo mode always loads the full fixture site (API ignores max_pages for demo)
- `page_intelligence` on multi-page jobs is primary-page oriented; selecting another page may call `POST /content-optimization` to enrich
- Visibility metrics are sample estimates — not consumer ChatGPT/Gemini/Perplexity rankings
- No job cancel/list; poll-only progress
- Drafts default to deterministic skeleton when requested — not paid LLM prose unless the API is configured for that separately

## Visual QA artifacts

Screenshots from runtime verification (when generated) live under:

`docs/verification/artifacts/leadership-ui/`
