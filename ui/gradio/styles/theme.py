"""Gradio theme + CSS — plain white professional dashboard.

Direction: white surfaces, near-black text, medium-gray secondary, subtle borders.
No dark-mode demo dependency; Soft ``*_dark`` tokens mirror the light palette.
Fonts: Source Sans 3 with offline system fallbacks.
"""

from __future__ import annotations

# Shared tokens (asserted by ui/gradio/tests/test_theme_contrast.py).
AEO_INK = "#1a1a1a"
AEO_MUTED = "#5c5c5c"
AEO_PANEL = "#ffffff"
AEO_BODY_BG = "#ffffff"
AEO_LINE = "#e5e5e5"
AEO_TABLE_HEADER_BG = "#f5f5f5"

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700&display=swap');

:root {
  --aeo-ink: #1a1a1a;
  --aeo-muted: #5c5c5c;
  --aeo-panel: #ffffff;
  --aeo-line: #e5e5e5;
  --aeo-accent: #0f766e;
  --aeo-accent-2: #0d9488;
  --aeo-warn: #b45309;
  --aeo-danger: #b91c1c;
  --aeo-ok: #047857;
  --aeo-table-header-bg: #f5f5f5;
  --aeo-font-sans: "Source Sans 3", "Source Sans Pro", "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
  color-scheme: light;
}

/* Force light surfaces even when Gradio adds .dark from prefers-color-scheme. */
html, html.dark, :root.dark, .dark {
  color-scheme: light !important;
  --body-background-fill: #ffffff !important;
  --body-text-color: #1a1a1a !important;
  --body-text-color-subdued: #5c5c5c !important;
  --background-fill-primary: #ffffff !important;
  --background-fill-secondary: #fafafa !important;
  --block-background-fill: #ffffff !important;
  --block-title-text-color: #1a1a1a !important;
  --block-label-text-color: #1a1a1a !important;
  --block-info-text-color: #5c5c5c !important;
  --accordion-text-color: #1a1a1a !important;
  --table-text-color: #1a1a1a !important;
  --table-even-background-fill: #ffffff !important;
  --table-odd-background-fill: #fafafa !important;
  --panel-background-fill: #ffffff !important;
  --input-background-fill: #ffffff !important;
  --input-placeholder-color: #5c5c5c !important;
  --checkbox-label-text-color: #1a1a1a !important;
  --button-secondary-text-color: #1a1a1a !important;
  --button-secondary-background-fill: #ffffff !important;
  --border-color-primary: #e5e5e5 !important;
}

html, body, .gradio-container {
  font-family: var(--aeo-font-sans) !important;
  color: var(--aeo-ink) !important;
  background: #ffffff !important;
  color-scheme: light !important;
}

.gradio-container {
  max-width: 1280px !important;
  margin: 0 auto !important;
  padding-bottom: 3rem !important;
}

#aeo-brand {
  margin: 0.5rem 0 0.75rem 0;
}

#aeo-brand h1 {
  font-family: var(--aeo-font-sans) !important;
  font-weight: 700 !important;
  font-size: clamp(1.75rem, 2.8vw, 2.25rem) !important;
  letter-spacing: -0.02em;
  color: var(--aeo-ink) !important;
  margin: 0 !important;
  line-height: 1.2 !important;
}

#aeo-brand .subtitle {
  color: var(--aeo-muted) !important;
  font-size: 1rem;
  margin-top: 0.4rem;
  max-width: 46rem;
}

#aeo-brand .eyebrow {
  display: inline-block;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--aeo-accent);
  margin-bottom: 0.3rem;
}

.aeo-panel {
  background: #ffffff !important;
  border: 1px solid var(--aeo-line) !important;
  border-radius: 8px !important;
  box-shadow: none !important;
  color: var(--aeo-ink) !important;
}

/* Markdown / HTML / form copy — never inherit dark-mode near-white ink. */
.aeo-panel,
.aeo-panel .md,
.aeo-panel .prose,
.aeo-panel p,
.aeo-panel li,
.aeo-panel h1,
.aeo-panel h2,
.aeo-panel h3,
.aeo-panel h4,
.aeo-panel span,
.aeo-panel label,
.gradio-container .md,
.gradio-container .prose,
.gradio-container .markdown,
.gradio-container [data-testid="markdown"],
.gradio-container .block .info,
.gradio-container .form .info {
  color: var(--aeo-ink) !important;
}

.aeo-panel .md em,
.aeo-panel .prose em,
.gradio-container .md em,
.gradio-container .prose em,
.gradio-container .block .info,
.gradio-container .form .info {
  color: var(--aeo-muted) !important;
}

.gradio-container .label-wrap,
.gradio-container .accordion,
.gradio-container .accordion .md,
.gradio-container .accordion .prose {
  color: var(--aeo-ink) !important;
}

.aeo-cta button, #analyze-btn button, #demo-btn button {
  background: var(--aeo-accent) !important;
  border: 1px solid var(--aeo-accent) !important;
  color: #fff !important;
  font-weight: 600 !important;
  border-radius: 6px !important;
  box-shadow: none !important;
}

.aeo-cta button:hover, #analyze-btn button:hover, #demo-btn button:hover {
  background: var(--aeo-accent-2) !important;
}

#guide-btn button, #clear-btn button {
  background: #ffffff !important;
  color: var(--aeo-ink) !important;
  border: 1px solid var(--aeo-line) !important;
  border-radius: 6px !important;
  font-weight: 600 !important;
}

.aeo-kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0.25rem 0 1rem 0;
}

.aeo-kpi-empty {
  grid-template-columns: 1fr;
  color: var(--aeo-muted) !important;
  padding: 0.75rem 0;
}

.aeo-kpi-empty p {
  color: var(--aeo-muted) !important;
}

.aeo-kpi-card {
  background: #ffffff;
  border: 1px solid var(--aeo-line);
  border-radius: 8px;
  padding: 0.85rem 1rem;
  min-height: 5.5rem;
  color: var(--aeo-ink);
}

.aeo-kpi-card--accent {
  border-color: rgba(15, 118, 110, 0.35);
  background: #ffffff;
}

.aeo-kpi-label {
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--aeo-muted) !important;
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.aeo-info {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.1rem;
  height: 1.1rem;
  border-radius: 999px;
  border: 1px solid var(--aeo-line);
  color: var(--aeo-muted);
  font-size: 0.72rem;
  cursor: help;
  flex-shrink: 0;
}

.aeo-kpi-value {
  font-family: var(--aeo-font-sans) !important;
  font-size: 1.65rem !important;
  font-weight: 700 !important;
  color: var(--aeo-ink) !important;
  margin-top: 0.25rem;
  line-height: 1.2;
}

.aeo-kpi-tip {
  font-size: 0.78rem;
  color: var(--aeo-muted) !important;
  margin-top: 0.35rem;
  line-height: 1.35;
}

.aeo-page-header {
  margin: 0 0 0.75rem 0;
  padding: 0.65rem 0.85rem;
  border-left: 3px solid var(--aeo-accent);
  background: #fafafa;
  border-radius: 0 6px 6px 0;
  color: var(--aeo-ink) !important;
}

.aeo-page-title {
  font-family: var(--aeo-font-sans) !important;
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--aeo-ink) !important;
}

.aeo-page-url {
  font-size: 0.9rem;
  color: var(--aeo-muted) !important;
  word-break: break-all;
  margin-top: 0.15rem;
}

.aeo-page-url-link {
  color: var(--aeo-accent) !important;
  text-decoration: underline;
  text-underline-offset: 2px;
  word-break: break-all;
}

.aeo-page-url-link:hover {
  color: var(--aeo-accent-2) !important;
}

/* Full-width page workspace: table → compact selector → detail (no side column). */
#aeo-page-workspace {
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0 !important;
}

#aeo-pages-table {
  width: 100% !important;
}

#aeo-selected-page {
  max-width: 28rem;
  width: 100%;
}

#aeo-page-detail {
  width: 100% !important;
  min-width: 0 !important;
  margin-top: 0.75rem;
}

@media (max-width: 900px) {
  #aeo-selected-page {
    max-width: 100%;
  }
}

.aeo-page-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 0.4rem;
  font-size: 0.9rem;
  color: var(--aeo-ink) !important;
}

.aeo-status-ok { color: var(--aeo-ok) !important; font-weight: 600; }
.aeo-status-err { color: var(--aeo-danger) !important; font-weight: 600; }
.aeo-status-busy { color: var(--aeo-warn) !important; font-weight: 600; }

/*
 * Inline code / pre / language labels inside AEO UI.
 * Gradio Soft dark tokens paint code pills near-black; force light surfaces + dark ink.
 * Article Markdown content stays readable; metadata must not become dark pills.
 */
.aeo-panel code,
.aeo-panel kbd,
.aeo-panel samp,
.gradio-container .md code,
.gradio-container .prose code,
.gradio-container .markdown code,
.gradio-container [data-testid="markdown"] code,
.gradio-container .code_wrap,
.gradio-container .codeblock,
.gradio-container span.language,
.gradio-container .md span[class*="language"],
.gradio-container .prose span[class*="language"],
html.dark .aeo-panel code,
html.dark .gradio-container .md code,
.dark .aeo-panel code,
.dark .gradio-container .md code {
  background: #ffffff !important;
  background-color: #ffffff !important;
  color: #1a1a1a !important;
  border: 1px solid #e5e5e5 !important;
  border-radius: 4px !important;
  box-shadow: none !important;
}

.aeo-panel pre,
.aeo-panel pre code,
.gradio-container .md pre,
.gradio-container .md pre code,
.gradio-container .prose pre,
.gradio-container .prose pre code,
.gradio-container .markdown pre,
.gradio-container .markdown pre code,
.gradio-container [data-testid="markdown"] pre,
.gradio-container [data-testid="markdown"] pre code,
html.dark .aeo-panel pre,
html.dark .aeo-panel pre code,
.dark .gradio-container .md pre,
.dark .gradio-container .md pre code {
  background: #fafafa !important;
  background-color: #fafafa !important;
  color: #1a1a1a !important;
  border: 1px solid #e5e5e5 !important;
  border-radius: 6px !important;
  box-shadow: none !important;
}

/* Side-by-side CURRENT vs RECOMMENDED Markdown panes (independent scroll). */
.aeo-md-compare {
  color: #1a1a1a !important;
  background: #ffffff !important;
}
.aeo-compare-summary,
.aeo-compare-note {
  color: #5c5c5c !important;
  font-size: 0.9rem;
  margin: 0.35rem 0 0.75rem 0;
}
.aeo-md-compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  align-items: stretch;
}
@media (max-width: 900px) {
  .aeo-md-compare-grid {
    grid-template-columns: 1fr;
  }
}
.aeo-md-pane {
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.aeo-md-pane-header {
  font-weight: 700;
  font-size: 0.85rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 0.55rem 0.75rem;
  border-bottom: 1px solid #e5e5e5;
  background: #f5f5f5;
  color: #1a1a1a !important;
}
.aeo-md-scroll {
  margin: 0 !important;
  padding: 0.75rem !important;
  max-height: 28rem;
  height: 28rem;
  overflow-y: auto !important;
  overflow-x: auto !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace !important;
  font-size: 0.82rem !important;
  line-height: 1.45 !important;
  white-space: pre-wrap !important;
  word-break: break-word !important;
  background: #ffffff !important;
  color: #1a1a1a !important;
  border: none !important;
  border-radius: 0 !important;
}

/* Recommended Markdown Code editor — light surface + copy affordance nearby. */
#aeo-recommended-markdown-code,
#aeo-recommended-markdown-code textarea,
#aeo-recommended-markdown-code .cm-editor,
#aeo-recommended-markdown-code .cm-content {
  background: #ffffff !important;
  color: #1a1a1a !important;
  border-color: #e5e5e5 !important;
}
#aeo-copy-recommended-md button {
  background: #ffffff !important;
  color: #1a1a1a !important;
  border: 1px solid #e5e5e5 !important;
}

/*
 * Dataframe / opportunities / pages tables.
 * Gradio thead uses --table-even-background-fill; Soft dark defaults paint it
 * near-black while we force dark ink → invisible headers. Lock light header + dark text.
 */
.aeo-panel table,
.gradio-container table,
.gradio-container .dataframe table {
  border-collapse: collapse !important;
  width: 100% !important;
}

.aeo-panel table thead,
.gradio-container table thead,
.gradio-container .dataframe thead,
.gradio-container thead.svelte-zsmsrz {
  background: var(--aeo-table-header-bg) !important;
}

.aeo-panel table th,
.gradio-container table th,
.gradio-container .dataframe th,
.gradio-container thead th,
.gradio-container thead.svelte-zsmsrz th {
  background: var(--aeo-table-header-bg) !important;
  color: var(--aeo-ink) !important;
  border: 1px solid var(--aeo-line) !important;
  padding: 0.65rem 0.75rem !important;
  font-size: 0.9rem !important;
  font-weight: 600 !important;
  white-space: normal !important;
  word-break: break-word !important;
  vertical-align: top !important;
}

.aeo-panel table td,
.gradio-container table td,
.gradio-container .dataframe td {
  background: #ffffff !important;
  color: var(--aeo-ink) !important;
  border: 1px solid var(--aeo-line) !important;
  padding: 0.65rem 0.75rem !important;
  font-size: 0.9rem !important;
  vertical-align: top !important;
  word-break: break-word;
  white-space: normal !important;
  line-height: 1.4 !important;
}

/* Ensure Signal / last columns stay readable (no tiny forced single-line). */
.aeo-panel table td:last-child,
.gradio-container .dataframe td:last-child,
.aeo-panel table th:last-child,
.gradio-container .dataframe th:last-child {
  color: var(--aeo-ink) !important;
  min-width: 5rem;
}

footer, .footer { display: none !important; }

@media (max-width: 1100px) {
  .gradio-container { padding-left: 1rem !important; padding-right: 1rem !important; }
  .aeo-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 700px) {
  .aeo-kpi-grid { grid-template-columns: 1fr; }
}
"""


def build_theme():
    import sys
    from pathlib import Path

    # Same shadowing guard as app.py / conftest
    for entry in list(sys.path):
        try:
            if Path(entry).resolve().name == "ui" and (Path(entry) / "gradio").is_dir():
                if "site-packages" not in entry:
                    sys.path.remove(entry)
        except Exception:  # noqa: BLE001
            pass
    mod = sys.modules.get("gradio")
    if mod is not None and "site-packages" not in str(getattr(mod, "__file__", "") or ""):
        del sys.modules["gradio"]
        for key in list(sys.modules):
            if key.startswith("gradio."):
                del sys.modules[key]

    import gradio as gr

    light = {
        "body_background_fill": AEO_BODY_BG,
        "body_text_color": AEO_INK,
        "body_text_color_subdued": AEO_MUTED,
        "background_fill_primary": "#ffffff",
        "background_fill_secondary": "#fafafa",
        "block_background_fill": AEO_PANEL,
        "block_border_width": "1px",
        "block_radius": "8px",
        "block_title_text_color": AEO_INK,
        "block_label_text_color": AEO_INK,
        "block_info_text_color": AEO_MUTED,
        "accordion_text_color": AEO_INK,
        "table_text_color": AEO_INK,
        "table_even_background_fill": "#ffffff",
        "table_odd_background_fill": "#fafafa",
        "panel_background_fill": "#ffffff",
        "input_background_fill": "#ffffff",
        "input_placeholder_color": AEO_MUTED,
        "checkbox_label_text_color": AEO_INK,
        "button_primary_background_fill": "#0f766e",
        "button_primary_text_color": "#ffffff",
        "button_secondary_background_fill": "#ffffff",
        "button_secondary_text_color": AEO_INK,
        "border_color_primary": AEO_LINE,
    }
    dark_mirror = {f"{k}_dark": v for k, v in light.items() if not k.endswith(("_width", "_radius"))}
    dark_mirror["button_primary_background_fill_dark"] = "#0f766e"
    dark_mirror["button_primary_text_color_dark"] = "#ffffff"
    # Explicit table header fills — Soft dark defaults are near-black.
    dark_mirror["table_even_background_fill_dark"] = "#ffffff"
    dark_mirror["table_odd_background_fill_dark"] = "#fafafa"
    dark_mirror["table_text_color_dark"] = AEO_INK

    return gr.themes.Soft(
        primary_hue=gr.themes.colors.teal,
        secondary_hue=gr.themes.colors.slate,
        neutral_hue=gr.themes.colors.slate,
        font=["Source Sans 3", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
        font_mono=["IBM Plex Mono", "ui-monospace", "Consolas", "monospace"],
    ).set(**light, **dark_mirror)
