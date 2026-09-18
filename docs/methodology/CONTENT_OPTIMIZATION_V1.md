# Content optimization methodology (`content-optimization-v1`)

**Status:** Binding Evaluator methodology (Phase 5)  
**Code contracts:** `page-intel-v1` · `content-gap-v1` · `opt-brief-v1` · `opt-draft-v1`  
**Package:** `aeo_mvp.content`  
**Verifier artifact (Verifier-owned after product SHA):**  
`VERIFY-PHASE5-CONTENT-OPTIMIZATION-2026-09-18` — engineering must **not** claim formal VERIFY.

## Honesty (non-negotiable)

| Rule | Meaning |
| --- | --- |
| Diagnostics ≠ health-v1 | Gaps/briefs never mutate or fold into `health-v1` |
| Generated ≠ observed | Drafts stamp `content_provenance=generated` |
| Never feed QSQ-EVD | Draft/generated text must not count as crawl `observed` evidence |
| Never feed visibility raw | Optional visibility enrich is separate; `page_coverage` ≠ AI visibility |
| Missing provenance | Via Phase 4.1.1 `normalize_provenance` → `compatibility` only |

## Gates C1–C10

**Block merge on:** C1, C2, C4, C6, C8, C9 (and C3, C5, C7, C10 by default).

| Gate | Assert | Test |
| --- | --- | --- |
| C1 | Page intel + provenance + hostname-scope | `test_c1_page_intel_provenance_hostname_scope` |
| C2 | Provenance enum incl. `generated`; no draft→observed | `test_c2_provenance_includes_generated_no_draft_to_observed` |
| C3 | Coverage from snapshot themes (no niche hardcode) | `test_c3_coverage_from_snapshot_themes_no_niche_hardcode` |
| C4 | Evidence-backed gaps only | `test_c4_evidence_backed_gaps_only` |
| C5 | Versioned brief cites inputs | `test_c5_versioned_brief_cites_inputs` |
| C6 | Grounded draft + citations; refuse ungrounded | `test_c6_grounded_draft_citations_refuse_ungrounded` |
| C7 | Determinism/freezes (fixture/Null draft OK) | `test_c7_determinism_and_null_draft_ok` |
| C8 | SSRF held | `test_c8_ssrf_held` |
| C9 | Paid DO off | `test_c9_paid_do_off` |
| C10 | Full suite + Phase 5 tests | `test_c10_full_suite_and_phase5_tests_present` + full `pytest` |

## Related

- Architect: `docs/architecture/PHASE5_PAGE_INTELLIGENCE.md`
- Provenance lock: `docs/architecture/PHASE4_1_1_PROVENANCE_LOCK.md` (unchanged)
- Examples: `docs/methodology/CONTENT_OPTIMIZATION.md`
