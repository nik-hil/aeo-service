"""Contrast / light-lock checks for Gradio leadership theme.

Guards against Soft dark-mode tokens flipping body text to near-white while
``.aeo-panel`` still paints light translucent fills (white-on-grey).
"""

from __future__ import annotations

from styles.theme import (
    AEO_BODY_BG,
    AEO_INK,
    AEO_MUTED,
    AEO_PANEL,
    CUSTOM_CSS,
    build_theme,
)


def test_custom_css_locks_light_color_scheme_and_ink():
    assert "color-scheme: light" in CUSTOM_CSS
    assert "--aeo-ink:" in CUSTOM_CSS
    assert AEO_INK in CUSTOM_CSS
    # Panel + markdown must set explicit ink (not inherit dark-mode white).
    assert ".aeo-panel" in CUSTOM_CSS
    assert "color: var(--aeo-ink) !important" in CUSTOM_CSS
    assert ".gradio-container .md" in CUSTOM_CSS
    # Dark-class CSS variables remapped to light fills / dark ink.
    assert "--body-text-color: #0f1c2e !important" in CUSTOM_CSS
    assert "--body-background-fill: #eef3f7 !important" in CUSTOM_CSS


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
    # Near-white Soft default must not survive.
    assert theme._get_computed_value("body_text_color_dark").lower() not in {
        "#f1f5f9",
        "#ffffff",
        "white",
    }
    assert theme._get_computed_value("body_background_fill_dark").lower() not in {
        "#0a0f1e",
        "#000000",
    }
