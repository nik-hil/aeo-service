"""Runtime timing proof: Stage A immediate vs Stage B enrichment (mocked delay)."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

# Unshadow gradio package if needed
_ui = ROOT.parent
sys.path[:] = [p for p in sys.path if Path(p).resolve() != _ui.resolve()]

from app import on_select_page
from fixture_report import OPT_PAYLOAD_ABOUT, PAGES_PAYLOAD, SAMPLE_REPORT
from services.adapters import AnalysisState
from services.enrichment import EnrichmentEntry, EnrichmentStatus


async def main() -> None:
    state = AnalysisState(
        job_id="job-demo-1",
        report=SAMPLE_REPORT,
        pages=PAGES_PAYLOAD,
    )
    delay = 0.35

    async def slow_fetch(client, *, job_id, page_id, content_draft=True):
        await asyncio.sleep(delay)
        return EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload=OPT_PAYLOAD_ABOUT)

    import app as app_mod

    app_mod.fetch_content_optimization = slow_fetch  # type: ignore[assignment]

    t0 = time.perf_counter()
    gen = on_select_page("https://demo.example/about", state)
    first = await gen.__anext__()
    t_stage_a = time.perf_counter() - t0
    assert "loading" in first[3].lower() or "Additional" in first[3]
    second = await gen.__anext__()
    t_stage_b = time.perf_counter() - t0
    assert "About" in second[2]
    print(
        f"RUNTIME_PROOF stage_a_ms={t_stage_a * 1000:.1f} "
        f"stage_b_ms={t_stage_b * 1000:.1f} "
        f"enrich_delay_ms={delay * 1000:.0f} "
        f"non_blocking={t_stage_a < delay * 0.5}"
    )


if __name__ == "__main__":
    asyncio.run(main())
