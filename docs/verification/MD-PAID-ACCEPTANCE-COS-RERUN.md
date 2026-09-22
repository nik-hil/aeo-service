# CoS re-run — paid MD acceptance

This cloud VM **did not** have `DO_MODEL_ACCESS_KEY` / `MODEL_ACCESS_KEY`, and
`AEO_PAID_RETRIEVAL_OPT_IN` was `false`. Paid DigitalOcean web_search therefore
fail-closed (ADR-026).

## To re-run with paid retrieval + MD URI

```bash
# 1) Secrets + master switch (same process that runs uvicorn)
export AEO_PAID_RETRIEVAL_OPT_IN=true
export DO_MODEL_ACCESS_KEY=...          # or MODEL_ACCESS_KEY
export AEO_API_KEY=...
export AEO_API_BASE_URL=http://127.0.0.1:8000
# optional:
# export AEO_VISIBILITY_PROVIDER=digitalocean_web_search
# export OPENAI_API_KEY=...             # only if testing openai_compatible path

# 2) Start API with those env vars
uvicorn aeo_mvp.api.app:app --host 127.0.0.1 --port 8000

# 3) Paid acceptance (exits 2 if keys/switch missing)
unset ALLOW_UNPAID_FALLBACK
python3 scripts/run_md_paid_acceptance.py
```

Seed URL is hard-coded to the Hashnode **`.md`** twin (not HTML).

Artifacts land in `/opt/cursor/artifacts/md-paid-acceptance/` (override with `ARTIFACT_DIR`).

## This VM’s unpaid fallback (already captured)

```bash
export ALLOW_UNPAID_FALLBACK=1
export AEO_API_KEY=dev-local-key-change-me
export AEO_API_BASE_URL=http://127.0.0.1:8000
python3 scripts/run_md_paid_acceptance.py
```

Status: `OK_UNPAID_FALLBACK` — MD CURRENT/RECOMMENDED/Q&O captured; visibility=demo.
