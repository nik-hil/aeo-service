"""Contrast / light-lock checks for Gradio plain-white theme.

Guards against Soft dark-mode tokens flipping body/table text to near-white
or painting dark dataframe headers (invisible Signal column).
"""

from __future__ import annotations

from styles.theme import (
    AEO_BODY_BG,
    AEO_INK,
    AEO_MUTED,
    AEO_PANEL,
    AEO_TABLE_HEADER_BG,
    CUSTOM_CSS,
    build_theme,
)


def test_custom_css_locks_light_color_scheme_and_ink():
    assert "color-scheme: light" in CUSTOM_CSS
    assert "--aeo-ink:" in CUSTOM_CSS
    assert AEO_INK in CUSTOM_CSS
    assert AEO_BODY_BG == "#ffffff"
    assert ".aeo-panel" in CUSTOM_CSS
    assert "color: var(--aeo-ink) !important" in CUSTOM_CSS
    assert ".gradio-container .md" in CUSTOM_CSS
    assert "--body-text-color: #1a1a1a !important" in CUSTOM_CSS
    assert "--body-background-fill: #ffffff !important" in CUSTOM_CSS


def test_custom_css_light_table_headers_and_no_dark_header_rule():
    """Table headers must be light with dark text; no conflicting dark thead paint."""
    assert "--table-even-background-fill: #ffffff !important" in CUSTOM_CSS
    assert AEO_TABLE_HEADER_BG in CUSTOM_CSS
    assert "thead" in CUSTOM_CSS
    assert "background: var(--aeo-table-header-bg) !important" in CUSTOM_CSS
    # No dark/near-black header backgrounds in our overrides.
    assert "#0b0f19" not in CUSTOM_CSS
    assert "#0a0f1e" not in CUSTOM_CSS
    # Signal / body cells stay dark ink, readable size, wrap allowed.
    assert "white-space: normal !important" in CUSTOM_CSS
    assert "font-size: 0.9rem" in CUSTOM_CSS
    assert "td:last-child" in CUSTOM_CSS


def test_custom_css_no_decorative_motion_or_blur():
    assert "backdrop-filter" not in CUSTOM_CSS
    assert "@keyframes" not in CUSTOM_CSS
    assert "aeo-fade-up" not in CUSTOM_CSS
    assert "radial-gradient" not in CUSTOM_CSS
    assert "translateY(-" not in CUSTOM_CSS


def test_custom_css_light_code_and_compare_panes():
    """Inline code / pre must stay white/light with dark ink — no dark pills."""
    assert ".aeo-panel code" in CUSTOM_CSS
    assert ".aeo-panel pre" in CUSTOM_CSS
    assert "background: #ffffff !important" in CUSTOM_CSS
    assert "aeo-md-compare" in CUSTOM_CSS
    assert "aeo-md-scroll" in CUSTOM_CSS
    assert "overflow-y: auto !important" in CUSTOM_CSS
    # Guard against near-black code chrome sneaking back in.
    assert "#0b0f19" not in CUSTOM_CSS
    assert "#111827" not in CUSTOM_CSS


def test_build_theme_mirrors_light_into_dark_tokens():
    theme = build_theme()
    assert theme._get_computed_value("body_text_color") == AEO_INK
    assert theme._get_computed_value("body_text_color_dark") == AEO_INK
    assert theme._get_computed_value("body_background_fill") == AEO_BODY_BG
    assert theme._get_computed_value("body_background_fill_dark") == AEO_BODY_BG
    assert theme._get_computed_value("block_background_fill_dark") == AEO_PANEL
    assert theme._get_computed_value("body_text_color_subdued_dark") == AEO_MUTED
    assert theme._get_computed_value("accordion_text_color_dark") == AEO_INK
    assert theme._get_computed_value("table_text_color_dark") == AEO_INK
    assert theme._get_computed_value("table_even_background_fill_dark") == "#ffffff"
    assert theme._get_computed_value("table_odd_background_fill_dark") == "#fafafa"
    # Near-white Soft default must not survive.
    assert theme._get_computed_value("body_text_color_dark").lower() not in {
        "#f1f5f9",
        "#ffffff",
        "white",
        "#f3f4f6",
    }
    assert theme._get_computed_value("body_background_fill_dark").lower() not in {
        "#0a0f1e",
        "#000000",
        "#0b0f19",
    }
    assert theme._get_computed_value("table_even_background_fill_dark").lower() not in {
        "#0b0f19",
        "#000000",
    }
