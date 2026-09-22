# PR #45 — MD quote-lock path (NO MERGE)

Repo: https://github.com/nik-hil/aeo-service
Branch tip start: 880cb8b on cursor/substantive-content-opt-e95e
Draft PR: https://github.com/nik-hil/aeo-service/pull/45

## Architect FAIL (agreed)
HTML paid live HARD PASS with real rewrite_section. MD paid live lost at claim_entailment_validation (quote-lock/novelty → needs_author_input). Dual FAIL until MD ready section op. Do not weaken invent bans.

## Diagnosis
HTML and MD source corpora are byte-identical for Agents article. Section has Hashnode list quirks (`*   permissions\n    \n`). HTML LLM quotes passed strict `q in corpus`; MD run failed quote-lock/novelty nondeterministically. Not missing wiring.

## Required fix (narrow)
1. Whitespace-canonical verbatim check in quote_is_verbatim: collapse whitespace runs for containment only; still require real contiguous span; NO paraphrase/fuzzy/edit-distance.
2. Optional quote repair fail-closed: remap quote_not_verbatim to WS-canonical corpus span; else keep author_input. Never invent quotes.
3. Optional one repair LLM call with validation errors; still full validate+entailment.
4. Unit tests: Hashnode list WS locks; invented/paraphrase fails; novelty bans unchanged; HTML rewrite_section regression.
5. Do NOT change gap taxonomy, FAQ/HowTo, schema/format/technical deferrals, ADR-026, stub rules, invent bans, entailment strictness.

## Prove
Focused + full unit (AEO_PAID_RETRIEVAL_OPT_IN=false). Paid dual HTML+.md Agents with real key. Both need llm_used=true, paid_llm=true, stub=no, ≥1 rewrite_section|add_explanation beyond intro. NO MERGE.
