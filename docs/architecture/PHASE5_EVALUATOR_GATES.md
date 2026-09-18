# Engineering gate map — Phase 5 C1–C10

**Methodology:** `content-optimization-v1`  
**Not** the formal Verifier artifact. Verifier writes  
`VERIFY-PHASE5-CONTENT-OPTIMIZATION-2026-09-18` after final product SHA.

## Blocking gates

| Gate | Status owner | pytest |
| --- | --- | --- |
| C1 | Eng | `tests/unit/test_content_optimization_phase5.py::test_c1_*` |
| C2 | Eng | `::test_c2_*` |
| C4 | Eng | `::test_c4_*` |
| C6 | Eng | `::test_c6_*` |
| C8 | Eng | `::test_c8_*` |
| C9 | Eng | `::test_c9_*` |

## Default blocking

C3 · C5 · C7 · C10 — same file; C10 also requires full suite green.

## Honesty checklist

- [ ] diagnostics ≠ health-v1  
- [ ] drafts `content_provenance=generated`  
- [ ] draft never fed to QSQ-EVD / crawl observed / visibility raw  
- [ ] paid DO / draft_paid default OFF  
- [ ] SSRF held on `source_url`  

## Run

```bash
pytest -q tests/unit/test_content_optimization_phase5.py -k 'test_c'
pytest -q
```
