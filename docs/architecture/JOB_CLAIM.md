# Job claim (P0-5) — single-owner pipeline execution

## Race

Before P0-5, `JobOrchestrator.run(job_id)` loaded the row and executed crawl /
providers with no compare-and-swap. Two workers (or a duplicate background task)
could run the same `job_id`, duplicating observations and racing status updates.

## Atomic claim

| Step | Behavior |
| --- | --- |
| Claim | `UPDATE jobs SET status='claimed', … WHERE id=? AND status IN ('pending','failed')` |
| Win | `rowcount == 1` → commit → run pipeline |
| Lose | `rowcount == 0` → `JobClaimConflict` (not a provider failure) |

API `POST /jobs` still creates `pending` and returns 202; the background task
claims before expensive work. Claim conflict leaves the winner’s status alone.

## State machine

| From | To | Who |
| --- | --- | --- |
| `pending` | `claimed` | Winner CAS |
| `failed` | `claimed` | Winner CAS (preserves programmatic re-run after failure; no separate retry API) |
| `claimed` | `crawling` → … → `completed` \| `failed` | Owner only |
| `completed` | — | No implicit re-execution |
| In-flight (`claimed`…`synthesizing`) | — | Second worker → conflict |

## Transaction boundary

Claim **commits** immediately. Crawl / OpenAI / DigitalOcean / content work run
**after** that commit in a new transaction (success commit in `_run_pipeline`;
provider failure commits `failed` inside the orchestrator). The claim transaction
is never held open across network I/O.

## Crash / stale claim

**No lease.** If the process dies after claim commit, the job remains `claimed`
(or whatever in-flight status was last committed). It does not auto-recover and
does not permanently brick the *schema* — an operator can set status back to
`pending` to allow reclaim. Aggressive timeouts were deferred to avoid dual
ownership.

## DB assumptions

See module docstring in `src/aeo_mvp/pipeline/job_claim.py`. Default engine remains
SQLite file URL; Postgres CAS is stronger under READ COMMITTED. No external lock
service. Cross-process safety applies only when workers share the **same** database.
