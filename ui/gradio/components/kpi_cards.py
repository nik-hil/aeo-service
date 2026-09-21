"""KPI display helpers — formatting only."""

from __future__ import annotations

from services.adapters import OverviewVM
from services.formatters import format_score


def kpi_lines(vm: OverviewVM) -> list[str]:
    lines = [f"AEO Health: {vm.health.value} ({vm.health.provenance})"]
    for c in vm.components:
        lines.append(f"{c.label}: {c.value}")
    return lines


def format_component_row(label: str, obj) -> str:
    return f"{label}: {format_score(obj)}"
