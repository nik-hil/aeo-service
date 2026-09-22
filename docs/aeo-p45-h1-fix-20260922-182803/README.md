# P45 H1 section-selection / mega-corpus fix — acceptance

- **Tip SHA:** `02d986d750858ec7ff90422b68fe4c53ad82e4fb`
- **PR:** #45 (`cursor/substantive-content-opt-e95e`)
- **URL:** https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md
- **Source:** live Hashnode `.md` was Cloudflare 403 here; corpus = MD rebuilt from checked-in live HTML fixture `tests/fixtures/phase6/article_agent1_baseline.html` (Agents Zero→Hero #1; H1 body sections).
- **paid_llm (live):** false (credentials missing)
- **stub:** false
- **web search:** OFF (`AEO_PAID_RETRIEVAL_OPT_IN=false`)
- **Selection VERDICT:** PASS (complete flow → `# The complete flow`, not H3; 5 distinct headings; all bodies <4K)
- **Live paid LLM VERDICT:** FAIL_credentials_missing (secrets requested)
- **Structural mock apply:** ready targets ['section:The complete flow', 'section:The finish tool']; changed ['The finish tool', 'The complete flow']; later-section dumping=False

## Sections selected per query

| Query | Heading | Body chars |
|-------|---------|------------|
| What is The complete flow? | The complete flow | 501 |
| How does the finish tool work? | The finish tool | 465 |
| Why does message history matter? | Why the message history matters | 536 |
| What is the agent loop? | The agent loop | 884 |
| Is there a security problem? | There is already a security problem | 685 |

## Files
- `agents-z2h_current.md`
- `agents-z2h_recommended.md` (mock LLM apply; not live paid)
- `agents-z2h_current_vs_recommended.diff`
- `acceptance_report.json`
