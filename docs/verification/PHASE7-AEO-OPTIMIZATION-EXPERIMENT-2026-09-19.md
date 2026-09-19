# Phase 7 — Real-world AEO optimization experiment (2026-09-19)

**Experiment status: `BLOCKED_PENDING_PUBLISH`**  
**Base main tip verified:** `043b21e` (Phase 6 PARTIALLY VALIDATED merged)  
**Live CMS publish:** **NO** — Hashnode credentials not present in this environment  
**Paid DigitalOcean web_search:** **NO** (ADR-026 closed; default remeasure keeps gate closed)  
**Causal impact:** **NOT_ESTABLISHED**

---

## Executive summary

Phase 7 prepares a real-world before→after experiment on `https://nik-hil.hashnode.dev/` using the Phase 6 authoritative baseline and the three selected catalog recommendations.  

**Done in this PR:**

1. Baseline fully recorded under `docs/verification/artifacts/phase7/`
2. Exact ready-to-publish homepage content specs for R1–R3
3. Post-publish measurement helper locked to the same seed / query-set / llm_mention path
4. Honest publish status: **NOT PUBLISHED**

**Not done:**

- Live Hashnode CMS publish (blocked pending authorized token from CoS)
- Post-change llm-mention remeasure
- Any claim that edits improved AI visibility

---

## Baseline (confirmed from Phase 6 artifacts)

| Field | Value |
| --- | --- |
| Site | `https://nik-hil.hashnode.dev/` |
| Job | `e26c5919-0ac5-4aab-86f4-36def39ec882` |
| Query-set | `query-set-v3` / `qs_fc087f4f5ebf` |
| Fingerprint | `2d79e25bd6f4513556c97f41b7d40851b74887573df594b206b1b221952175ec` |
| `selection_seed` | **3236362228** |
| Provider | `openai_compatible` (`openai-gpt-4o-mini`) |
| Experiment | `llm_mention` / `llm-mention-v1` |
| Retrieval | **false**; `paid_do_calls=0` |
| `aeo_health` | **76.4** |
| `entity` | **52.5** |
| `llm_mention_rate` | **≈ 0.133** (8/60 estimate) |
| Homepage | title `Nikhil Ikhar's blog`, **h1=null**, schema `Blog` |

Confirmation artifact: `docs/verification/artifacts/phase7/PHASE7_BASELINE_CONFIRMED.json`  
Copied CoS evidence/snapshot/recommendation examples into `docs/verification/artifacts/phase7/`.

### Live brand verify (pre-publish)

Fetched homepage 2026-09-19: still **no H1**; publication strings still **`Nikhil Ikhar's blog`**.  
Preferred consolidation target: **`Nikhil Ikhar`** (person name).  
See `PHASE7_LIVE_BRAND_VERIFY.json`.

---

## Selected recommendations (unchanged from Phase 6)

From `PHASE6_RECOMMENDATION_EXAMPLES.json` only:

1. `REC_CONSOLIDATE_BRAND_NAME`
2. `REC_CLARIFY_BRAND_IN_COPY`
3. `REC_FIX_HEADING_HIERARCHY`

Ready-to-publish pack:

- `docs/verification/artifacts/phase7/PHASE7_READY_TO_PUBLISH.md`
- `docs/verification/artifacts/phase7/PHASE7_READY_TO_PUBLISH.json`

Includes exact before→after brand strings, H1 text, lead blurb, meta description, valid Person+Organization JSON-LD, and Hashnode UI click/edit notes.

---

## Publish status

| Item | Status |
| --- | --- |
| Experiment | **`BLOCKED_PENDING_PUBLISH`** |
| Changes prepared | **YES** |
| Changes published | **NO** |
| Post-change measurement | **NOT RUN** |
| Causal impact | **NOT_ESTABLISHED** |

Artifact: `PHASE7_PUBLISH_STATUS.json` (`published=false`).

No `HASHNODE_PAT` (or equivalent) was found in the agent environment. CoS is requesting the token separately. This PR does **not** fabricate `published=true` or post-change metrics. Phase 6 fixture simulation is **not** proof of live CMS change.

---

## Post-publish measurement plan (NOT RUN)

When CoS publishes and updates `PHASE7_PUBLISH_STATUS.json`:

```bash
python scripts/phase7_post_publish_remeasure.py
# defaults:
#   --seed 3236362228
#   --provider openai_compatible
#   --url https://nik-hil.hashnode.dev/
#   paid_retrieval_opt_in=false (ADR-026 closed)
```

Then compare against the Phase 6 baseline excerpt/snapshot with:

```bash
python scripts/compare_job_reports.py \
  docs/verification/artifacts/phase6/PHASE6_COS_BASELINE_REPORT_EXCERPT.json \
  docs/verification/artifacts/phase7/PHASE7_POST_PUBLISH_REPORT_EXCERPT.json \
  --change-source live_cms \
  --out docs/verification/artifacts/phase7/PHASE7_BEFORE_AFTER.json
```

Evidence class will remain non-causal unless methodology requirements for `causal_evidence` are met. Do **not** enable paid DO `web_search` by default.

---

## Safety

- ADR-026 stays closed unless explicitly opted in later with credentials.
- No architecture / prod-readiness redo (Phase 6 scope preserved).
- No invented live results.

---

## Testing

```bash
pytest -q tests/unit/test_phase7_experiment_pack.py tests/unit/test_phase6_measurement.py
pytest -q -rs
```

---

## Conclusion

| Claim | Status |
| --- | --- |
| Phase 6 baseline recorded into phase7/ | **done** |
| Ready-to-publish R1–R3 pack | **done** |
| Live Hashnode publish | **blocked** |
| Post-change llm-mention remeasure | **not run** |
| Causal AEO impact | **NOT_ESTABLISHED** |

**Experiment status remains `BLOCKED_PENDING_PUBLISH` until CoS provides publish proof.**
