# Content Optimization — examples & limitations

## Offline example (fixture HTML)

```bash
curl -s http://127.0.0.1:8000/api/v1/content-optimization \
  -H 'content-type: application/json' \
  -d '{
    "html": "<html><head><title>Demo</title></head><body><h1>Demo</h1><p>Answer first text about widgets.</p></body></html>",
    "url": "https://demo.example/",
    "queryset": {
      "query_set_version": "query-set-v3",
      "members": [
        {"query": {"query_id": "q1", "text": "What are widgets?", "intent": "informational"}}
      ]
    },
    "paid_llm_opt_in": false
  }'
```

Response sections: `page_intelligence`, `gap_report`, `brief`, `draft`.

## From an existing job

```bash
curl -s http://127.0.0.1:8000/api/v1/content-optimization \
  -H 'content-type: application/json' \
  -d '{"job_id":"<JOB_UUID>","page_id":"<PAGE_UUID>","paid_llm_opt_in":false}'
```

Uses crawled HTML; loads discovered queryset from the job when present.

## Rejected shapes

```json
{"topic": "best crm software"}
```

→ `422` (not a grounded page optimization request).

```json
{"source_url": "http://127.0.0.1/admin"}
```

→ `400` SSRF rejection.

## Limitations (honest)

| Limitation | Detail |
| --- | --- |
| Not a writer SaaS | Heuristic draft is structured placeholders + outline, not polished marketing copy |
| No CMS publish | Draft JSON/markdown only |
| Paid LLM | Opt-in stub refuses live calls until implemented |
| Coverage ≠ visibility | `direct/partial/mention/none` is lexical/topic overlap on the page |
| No health fold-in | Gaps never mutate `health-v1` |
| Evidence honesty | Draft/generated text is not stamped `observed` |

## Related

- Architecture: `docs/architecture/PHASE5_CONTENT_OPTIMIZATION.md`
- Provenance lock: `docs/architecture/PHASE4_1_1_PROVENANCE_LOCK.md`
- Query sets: `query-set-v3` / `query-quality-v1`
