# SUPERSEDED / ABORTED

This acceptance ran **without** paid DO web search (`AEO_PAID_RETRIEVAL_OPT_IN=false`)
and without a live paid LLM key (selection proof + mock apply only).

**User correction (override):** all live testing on PR #45 must enable **paid LLM and
paid DO web search together** against the Hashnode `.md` seed URL only.

Do not treat this folder as the H1-fix live acceptance. Re-run via:

```bash
export AEO_PAID_RETRIEVAL_OPT_IN=true
export DO_MODEL_ACCESS_KEY=...   # required
python3 scripts/run_p45_h1_paid_md_acceptance.py
```
