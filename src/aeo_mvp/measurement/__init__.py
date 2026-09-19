"""Phase 6 before/after AEO measurement helpers.

Evidence classes are explicit: observed_improvement, correlation,
hypothesis, causal_evidence. Do not claim causality without support.
"""

from __future__ import annotations

from aeo_mvp.measurement.before_after import (
    EVIDENCE_CLASSES,
    MEASUREMENT_METHODOLOGY,
    BaselineSnapshot,
    OptimizationMapping,
    PostChangeSnapshot,
    compare_snapshots,
    extract_baseline_from_report,
    extract_coverage_snapshot,
    mappings_from_brief,
)

__all__ = [
    "MEASUREMENT_METHODOLOGY",
    "EVIDENCE_CLASSES",
    "BaselineSnapshot",
    "PostChangeSnapshot",
    "OptimizationMapping",
    "extract_baseline_from_report",
    "extract_coverage_snapshot",
    "compare_snapshots",
    "mappings_from_brief",
]
