"""Overview rendering helpers."""

from __future__ import annotations

from typing import Any

from services.adapters import adapt_overview, overview_markdown
from services.opportunities import build_opportunities, opportunities_table


def render_overview(report: dict[str, Any], *, mode: str) -> tuple[str, list[list[str]]]:
    vm = adapt_overview(report, mode=mode)
    opps = build_opportunities(report)
    return overview_markdown(vm), opportunities_table(opps)
