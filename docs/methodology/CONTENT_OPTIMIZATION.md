# Content optimization methodology (`content-optimization-v1`)

See binding Evaluator methodology: [`CONTENT_OPTIMIZATION_V1.md`](./CONTENT_OPTIMIZATION_V1.md).

**Contracts:** `page-intel-v1` → `content-gap-v1` → `opt-brief-v1` → `opt-draft-v1`  
**Package:** `aeo_mvp.content` — page_intel · gaps · brief · draft

## Coverage honesty

`page_coverage` on the Query×page matrix is **not** AI visibility and **not** health-v1.

## Draft honesty

Drafts are **generated**. `unsupported_claims[]` required. Never promote to observed / QSQ-EVD.

## API example

```bash
curl -s http://127.0.0.1:8000/api/v1/content-optimization \
  -H 'content-type: application/json' \
  -d '{
    "html": "<html><body><h1>Demo</h1><p>Widgets are tools.</p></body></html>",
    "url": "https://demo.example/",
    "queryset": {"query_set_version":"query-set-v3","members":[{"query":{"query_id":"q1","text":"What are widgets?","intent":"informational"}}]},
    "generate_draft": true,
    "draft_paid": false
  }'
```

## Limitations

Null/skeleton drafts only; no CMS publish; no citation guarantees; paid LLM stub refuses live calls; formal VERIFY is Verifier-owned.
