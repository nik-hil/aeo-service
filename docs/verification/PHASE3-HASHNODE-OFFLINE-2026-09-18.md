# Phase 3 Hashnode offline validation

**Date:** 2026-09-18
**Target:** https://nik-hil.hashnode.dev/
**Mode:** offline fixtures (`tests/fixtures/hashnode`) — no paid APIs

## Verdict
- Primary industry is **not** `project_management`: **True** (guess='ai_ml', omitted=False)
- site_genre: **personal_tech_blog**
- Tags not in products: **True**
- Paid retrieval auto-run: **false** (opt_in=False)

## Profile evidence
- org_name: Nikhil Ikhar
- topics (sample): ['Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling', 'Build an AI Agent From Scratch in Python: Step-by-Step Guide', "Nikhil Ikhar's blog", 'The agent loop', 'Our first two tools', 'Tool schemas', 'Implementing execute_code', 'The finish tool']
- products_services: []
- evidence_hash: `e00a2844991839cc`
- warnings: []

## Query discovery counts
- generated (post-dedupe candidates): 40
- accepted: 40
- rejected: 0
- selected (top_k=20, seed=18): 20
- intent_breakdown: {'informational': 5, 'problem_solving': 5, 'recommendation': 5, 'comparison': 4, 'navigational': 1}

## Examples per intent
### comparison
- How does Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling compare to other approaches?
- How does Build an AI Agent From Scratch in Python: Step compare to other approaches?
- How does Our first two tools compare to other approaches?

### informational
- What is Our first two tools?
- What is The finish tool?
- What is Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling?

### navigational
- What is Nikhil Ikhar?

### problem_solving
- How do I build an AI agent with tool calling?
- How to give an AI agent filesystem tools?
- How does an AI agent loop work?

### recommendation
- What are good resources for learning Tool schemas?
- What are good resources for learning The agent loop?
- Is Nikhil Ikhar a good resource for AI agents?

## Gate reject reason families
- {}

## Artifacts
- JSON: `docs/verification/PHASE3-HASHNODE-OFFLINE-2026-09-18.json`
- Fixtures: `tests/fixtures/hashnode/`

## H1–H10 checklist
- H1 Not primarily project_management without evidence: PASS
- H2 AI/agent/tooling topic queries when headings present: PASS
- H3 No paid discovery calls: PASS
