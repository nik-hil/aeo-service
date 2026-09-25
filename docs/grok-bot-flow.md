# Grok Bot flow for aeo-service

Cost- and reliability-oriented playbook for building [nik-hil/aeo-service](https://github.com/nik-hil/aeo-service) with Grok Bots + occasional ChatGPT review + Cursor cloud agents.

**Product stance:** resume + open-source Hashnode Markdown AEO craft engine. Not a Wellows clone. Not an internal replacement for a Wellows contract.

**Near-term build (8–10 days):** (1) prompt board + mention/citation log, (2) before→after publish pack, (3) one-command fixture demo without paid keys.

---

## Roster

| Bot | Role | When to use |
|---|---|---|
| **AEO Architect** | Primary day-to-day coder | Almost all features, bugs, PRs |
| **AEO UI** | Gradio only | Visual/UI changes; user must run locally before merge |
| **AEO Verifier** | Independent evidence | On-demand PASS/FAIL, not every turn |
| **AEO Researcher** | Category / methodology research | On-demand |
| **AEO AI Evaluator** | Visibility experiment design | On-demand |
| **AEO Content Optimizer** | Recommendation / content-pack quality | On-demand |
| **AEO Production Auditor** | Read-only readiness audits | Sparse |
| **AEO Chief of Staff (Cos)** | Optional coordinator | Multi-step programs only — not a chatty middleman |

Cursor **cloud agents** do heavy repo edits on GitHub. Bots coordinate; they do not clone the repo onto the Grok box for coding.

---

## One bot vs Cos

**Use Architect directly (preferred):**

- Single feature, bug, or PR
- You already know the acceptance criteria
- Cost-sensitive day-to-day work

**Use Cos only when:**

- Several specialists must sequence (e.g. research → design → implement → verify)
- You want Cos to draft a kickoff then hand you to Architect
- Cross-cutting process (playbook, skills, spend guardrails)

Cos must not relay every status ping between bots.

---

## Chat hygiene

1. **New chat per feature/bug/PR.** Do not stretch one thread across unrelated goals.
2. **Short kickoff** (see skill *New chat task kickoff*): goal, repo/branch, acceptance bullets, out of scope, constraints.
3. **Standing rules live in Bot descriptions + skills**, not chat history.
4. **UI:** you run Gradio on your laptop and look. Agent text, tests, and ChatGPT summaries alone are not UI acceptance.
5. **Merge** only on your explicit ask.
6. ChatGPT is for tightening prompts and reviewing intent — not for “it looks fine” on Gradio.

---

## Bot-to-bot rules

- Message another bot **only when it must act**.
- No acks, thanks, or progress pings.
- One summary when done (PR link / PASS-FAIL / blocker).
- No fan-out “just in case.”

Skill: *Quiet bot handoff*.

---

## Skills (Grok Bot library)

| Skill | Use when |
|---|---|
| **New chat task kickoff** | Starting a feature/bug/PR in a fresh chat |
| **Quiet bot handoff** | Messaging another bot or agent |
| **AEO PR handoff** | Opening/reviewing/handing off an aeo-service PR |

---

## Cloud agents & CI

- Launch cloud agents against `https://github.com/nik-hil/aeo-service`.
- Prefer fixture/demo mode in PR descriptions.
- Do not merge from bots/cloud agents unless the user said to merge.
- Paid keys (Astra/LLM/web_search) belong on the trusted runner / local env — never committed; Cursor cloud VMs often lack them — design PRs to work without paid calls.

---

## Approval boundaries

| Action | Who |
|---|---|
| Implement / open PR | Architect or cloud agent |
| Visually accept Gradio | **You** |
| Merge PR | **You** (explicit) |
| Paid live LLM / web_search run | **You** (explicit opt-in) |
| Message many bots at once | Avoid; Cos asks first if ever needed |
| Tight polling routines (e.g. every 5 minutes) | Avoid; keep sparse or paused |

---

## Spend guardrails (now vs later)

**Now:** fixtures default; paid behind opt-in; no silent retries; demo works without keys.

**Later:** deeper Astra cost optimization (batching, cheaper draft models, etc.) — after the top-three features are solid.

---

## Suggested kickoff template

```text
Goal: <one sentence>
Repo: https://github.com/nik-hil/aeo-service (base: main)
Acceptance:
- ...
- ...
Out of scope: ...
Constraints: fixture default; no merge; if UI — I will run Gradio locally before merge
Use standing Bot description + skills; do not wait on Cos mid-task.
```

---

## Related product notes

Wellows gap / resume stance and the 8–10 day top-three plan live in Cos chat history (2026-09-25). This doc only covers **how we work**, not the full product roadmap.
