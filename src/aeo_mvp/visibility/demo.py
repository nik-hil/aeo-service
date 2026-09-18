"""Deterministic DemoProvider using fixture observations."""

from __future__ import annotations

from datetime import datetime, timezone

from aeo_mvp.demo.loader import load_visibility_fixture
from aeo_mvp.visibility.base import VisibilityContext, VisibilityObservation
from aeo_mvp.visibility.metrics import EXTRACTION_METHODOLOGY


class DemoProvider:
    name = "demo"

    def __init__(self) -> None:
        data = load_visibility_fixture()
        self._by_key: dict[tuple[str, int], dict] = {}
        for row in data.get("observations", []):
            self._by_key[(row["prompt_id"], int(row["run_index"]))] = row

    async def run_query(self, query: str, *, context: VisibilityContext) -> VisibilityObservation:
        row = self._by_key.get((context.prompt_id, context.run_index))
        if row is None:
            # Deterministic fallback empty
            return VisibilityObservation(
                provider_name=self.name,
                engine_label="demo-engine",
                query=query,
                prompt_id=context.prompt_id,
                run_index=context.run_index,
                observed_at=datetime(2026, 9, 18, 0, 0, 0, tzinfo=timezone.utc),
                raw_response="No seeded observation for this prompt/run.",
                raw_storage_permitted=True,
                detected_mention=False,
                detected_citation=False,
                cited_urls=[],
                extraction_methodology=EXTRACTION_METHODOLOGY,
                provenance="synthetic_demo",
                meta={"missing_seed": True},
            )
        return VisibilityObservation(
            provider_name=self.name,
            engine_label=row.get("engine_label", "demo-engine"),
            query=row.get("query", query),
            prompt_id=context.prompt_id,
            run_index=context.run_index,
            observed_at=datetime(2026, 9, 18, 0, 0, context.run_index, tzinfo=timezone.utc),
            raw_response=row.get("raw_response"),
            raw_storage_permitted=True,
            detected_mention=bool(row.get("detected_mention")),
            detected_citation=bool(row.get("detected_citation")),
            cited_urls=list(row.get("cited_urls") or []),
            extraction_methodology=row.get("extraction_methodology", EXTRACTION_METHODOLOGY),
            provenance="synthetic_demo",
            meta=dict(row.get("meta") or {}),
        )
