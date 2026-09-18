# VERIFY-COMPLETE-DRAFT

**Generated:** 2026-09-18 05:38 UTC
**Harness:** `scripts/run_independent_verification.py`
**Note:** Draft only — full Verifier sign-off comes later.

**Overall:** PASS

## Results

### PASS: import_app

```
create_app ok; routes=6
```

### PASS: demo_job

```
status=completed experiment_kind=llm_mention retrieval_enabled=False keys=['experiment_kind', 'llm_mention_rate', 'llm_url_mention_rate', 'model_id', 'observations_count', 'protocol_version', 'provider_capabilities_notes', 'provider_name', 'query_coverage', 'retrieval_enabled']
```

### PASS: p1_report_sections

```
missing=[] agents=10 brand=AcmeFlow dq=10 exec_keys=['data_provenance', 'major_caveats', 'overall_health', 'strongest_areas', 'top_3_actions', 'weakest_areas']
```

### PASS: health_recompute

```
stored=87.875 recomputed=87.875
```

### PASS: observation_flags

```
n=15 ok=True
```

### PASS: no_false_ai_search_claims

```
banned_checked=['ChatGPT ranking', 'official AI share of voice', 'ai_mention_rate']
```

### PASS: pytest_ssrf_scoring_p1

```
.........................                                                [100%]
=============================== warnings summary ===============================
.venv/lib/python3.13/site-packages/fastapi/testclient.py:1
  /workspace/aeo-mvp/.venv/lib/python3.13/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

.venv/lib/python3.13/site-packages/starlette/testclient.py:53
  /workspace/aeo-mvp/.venv/lib/python3.13/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
25 passed, 2 warnings in 0.12s
```

