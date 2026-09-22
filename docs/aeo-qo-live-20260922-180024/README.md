# AEO Q&O live capture (20260922-180024 UTC)

## Run identity
- Seed URL (.md only): `https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md`
- Job id: `0b578cdc-4c02-4554-a65c-37a05a30ca47` · status `completed`
- Tip SHA at run: `5cdee14ecc59b68134ef4b9bbb7205cccb9d8eaa`
- Elapsed: 341.4s
- Visibility provider: `digitalocean_web_search` · retrieval_enabled: True · observations: 33
- Report paid_retrieval flag: `False` (see caveats)
- Draft method: `opt-draft-v1+paid_llm_stub_v0` · llm_used: False · paid_llm: False
- CURRENT chars: 12095 · RECOMMENDED chars: 11754
- Q&O questions: 10 · provider=deterministic

## Files
- `20260922-180024_current.md`
- `20260922-180024_recommended.md`
- `20260922-180024_current_vs_recommended.diff`
- `20260922-180024_questions_opportunities.md`
- `20260922-180024_questions_opportunities.json`
- `20260922-180024_page_meta.json`
- `20260922-180024_report_slim.json`
- `20260922-180024_credential_probe.json`
- `20260922-180024_git_sha.txt`

## Caveats
1. CoS re-run with paid DO web_search credentials (ADR-026 opt-in). Observations use digitalocean_web_search (n=33), not demo.
2. Content draft on this tip used paid_llm_stub_v0 (llm_used=false) — intro rewrite only, not grounded section synthesis from PR #45.
3. Q&O is deterministic heading-to-FAQ scaffolding; all 10 marked strong/low importance — not publish-ready.
4. Earlier cloud folder docs/aeo-qo-live-20260922-175648/ was unpaid/demo. Prefer this folder for visibility analysis.
5. Do not publish to Hashnode / do not merge without review.
