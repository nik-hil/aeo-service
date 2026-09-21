"""KPI card HTML builders — real cards, not Markdown soup."""

from __future__ import annotations

from glossary import executive_tip
from services.adapters import OverviewVM
from services.sanitize import escape_text


def _card(label: str, value: str, tip: str, *, accent: bool = False) -> str:
    cls = "aeo-kpi-card aeo-kpi-card--accent" if accent else "aeo-kpi-card"
    return (
        f'<div class="{cls}" title="{escape_text(tip)}">'
        f'<div class="aeo-kpi-label">{escape_text(label)}'
        f'<span class="aeo-info" aria-label="{escape_text(tip)}">ⓘ</span></div>'
        f'<div class="aeo-kpi-value">{escape_text(value)}</div>'
        f'<div class="aeo-kpi-tip">{escape_text(tip)}</div>'
        f"</div>"
    )


def kpi_cards_html(vm: OverviewVM | None) -> str:
    if vm is None:
        return (
            '<div class="aeo-kpi-grid aeo-kpi-empty">'
            "<p>Run an analysis to see AEO Health, Entity Clarity, Visibility, Gaps, and Opportunities.</p>"
            "</div>"
        )

    entity = next((c for c in vm.components if c.key == "entity"), None)
    gap_n = vm.gap_count
    opp_n = vm.opportunity_count
    vis = vm.visibility_summary or "—"
    health_band = ""
    if "—" in vm.health.label:
        health_band = f" · {vm.health.label.split('—', 1)[-1].strip()}"

    cards = [
        _card(
            "AEO Health",
            f"{vm.health.value}{health_band}",
            executive_tip("aeo_health"),
            accent=True,
        ),
        _card(
            "Entity Clarity",
            entity.value if entity else "—",
            executive_tip("entity_score"),
        ),
        _card(
            "AI / LLM Visibility",
            vis,
            executive_tip("ai_llm_visibility"),
        ),
        _card(
            "Content Gaps",
            str(gap_n),
            executive_tip("content_gap"),
        ),
        _card(
            "Opportunities",
            str(opp_n),
            executive_tip("optimization_opportunity"),
        ),
    ]
    return '<div class="aeo-kpi-grid">' + "".join(cards) + "</div>"


def kpi_lines(vm: OverviewVM) -> list[str]:
    """Legacy plain-text lines (tests / fallbacks)."""
    lines = [f"AEO Health: {vm.health.value} ({vm.health.provenance})"]
    for c in vm.components:
        lines.append(f"{c.label}: {c.value}")
    return lines


def format_component_row(label: str, obj) -> str:
    from services.formatters import format_score

    return f"{label}: {format_score(obj)}"
