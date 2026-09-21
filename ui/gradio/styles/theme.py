"""Gradio theme + CSS for a polished B2B SaaS leadership aesthetic.

Direction: cool slate + teal accent, soft grid atmosphere, expressive type.
Avoid purple-on-white / cream-serif / broadsheet clichés.
Fonts: Fraunces + Source Sans 3 with offline system fallbacks (no hard CDN dependency).
"""

from __future__ import annotations

CUSTOM_CSS = """
/* Optional webfonts — system stacks below keep the UI readable offline/CDN-blocked. */
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,550;9..144,700&family=Source+Sans+3:wght@400;500;600;700&display=swap');

:root {
  --aeo-ink: #0f1c2e;
  --aeo-muted: #5a6b7d;
  --aeo-panel: rgba(255, 255, 255, 0.78);
  --aeo-line: rgba(15, 28, 46, 0.10);
  --aeo-accent: #0f766e;
  --aeo-accent-2: #155e75;
  --aeo-warn: #b45309;
  --aeo-danger: #b91c1c;
  --aeo-ok: #047857;
  --aeo-hero-grad: radial-gradient(1200px 500px at 10% -10%, rgba(15, 118, 110, 0.18), transparent 55%),
                   radial-gradient(900px 420px at 90% 0%, rgba(21, 94, 117, 0.16), transparent 50%),
                   linear-gradient(165deg, #e8eef4 0%, #f3f7fa 42%, #eef5f4 100%);
  --aeo-grid: linear-gradient(rgba(15, 28, 46, 0.04) 1px, transparent 1px),
              linear-gradient(90deg, rgba(15, 28, 46, 0.04) 1px, transparent 1px);
  --aeo-font-sans: "Source Sans 3", "Source Sans Pro", "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --aeo-font-display: "Fraunces", "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif;
}

html, body, .gradio-container {
  font-family: var(--aeo-font-sans) !important;
  color: var(--aeo-ink) !important;
  background: var(--aeo-hero-grad) !important;
  background-attachment: fixed !important;
}

.gradio-container {
  max-width: 1280px !important;
  margin: 0 auto !important;
  padding-bottom: 3rem !important;
}

.gradio-container::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image: var(--aeo-grid);
  background-size: 28px 28px;
  opacity: 0.55;
  z-index: 0;
}

.gradio-container > * {
  position: relative;
  z-index: 1;
}

#aeo-brand {
  margin: 0.5rem 0 0.25rem 0;
  animation: aeo-fade-up 0.55s ease-out both;
}

#aeo-brand h1 {
  font-family: var(--aeo-font-display) !important;
  font-weight: 700 !important;
  font-size: clamp(2rem, 3.2vw, 2.75rem) !important;
  letter-spacing: -0.02em;
  color: var(--aeo-ink) !important;
  margin: 0 !important;
  line-height: 1.15 !important;
}

#aeo-brand .subtitle {
  color: var(--aeo-muted);
  font-size: 1.05rem;
  margin-top: 0.45rem;
  max-width: 46rem;
  animation: aeo-fade-up 0.7s ease-out both;
}

#aeo-brand .eyebrow {
  display: inline-block;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--aeo-accent);
  margin-bottom: 0.35rem;
  animation: aeo-fade-up 0.4s ease-out both;
}

.aeo-panel {
  background: var(--aeo-panel) !important;
  border: 1px solid var(--aeo-line) !important;
  border-radius: 14px !important;
  backdrop-filter: blur(8px);
  box-shadow: 0 10px 30px rgba(15, 28, 46, 0.05) !important;
  animation: aeo-fade-up 0.65s ease-out both;
}

.aeo-cta button, #analyze-btn button, #demo-btn button {
  background: linear-gradient(135deg, var(--aeo-accent), var(--aeo-accent-2)) !important;
  border: none !important;
  color: #fff !important;
  font-weight: 600 !important;
  border-radius: 10px !important;
  transition: transform 0.18s ease, box-shadow 0.18s ease !important;
  box-shadow: 0 6px 16px rgba(15, 118, 110, 0.25) !important;
}

.aeo-cta button:hover, #analyze-btn button:hover, #demo-btn button:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(15, 118, 110, 0.32) !important;
}

#guide-btn button, #clear-btn button {
  background: transparent !important;
  color: var(--aeo-accent-2) !important;
  border: 1px solid rgba(21, 94, 117, 0.35) !important;
  border-radius: 10px !important;
  font-weight: 600 !important;
}

.aeo-kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0.25rem 0 1rem 0;
  animation: aeo-fade-up 0.5s ease-out both;
}

.aeo-kpi-empty {
  grid-template-columns: 1fr;
  color: var(--aeo-muted);
  padding: 0.75rem 0;
}

.aeo-kpi-card {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--aeo-line);
  border-radius: 12px;
  padding: 0.85rem 1rem;
  min-height: 5.5rem;
  transition: transform 0.18s ease, border-color 0.18s ease;
}

.aeo-kpi-card:hover {
  transform: translateY(-2px);
  border-color: rgba(15, 118, 110, 0.35);
}

.aeo-kpi-card--accent {
  border-color: rgba(15, 118, 110, 0.35);
  background: linear-gradient(160deg, rgba(15, 118, 110, 0.08), rgba(255, 255, 255, 0.95));
}

.aeo-kpi-label {
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--aeo-muted);
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
  border: 1px solid rgba(15, 118, 110, 0.45);
  color: var(--aeo-accent);
  font-size: 0.72rem;
  cursor: help;
  flex-shrink: 0;
}

.aeo-kpi-value {
  font-family: var(--aeo-font-display) !important;
  font-size: 1.65rem !important;
  color: var(--aeo-accent) !important;
  margin-top: 0.25rem;
  line-height: 1.2;
}

.aeo-kpi-tip {
  font-size: 0.78rem;
  color: var(--aeo-muted);
  margin-top: 0.35rem;
  line-height: 1.35;
}

.aeo-page-header {
  margin: 0 0 0.75rem 0;
  padding: 0.65rem 0.85rem;
  border-left: 3px solid var(--aeo-accent);
  background: rgba(15, 118, 110, 0.06);
  border-radius: 0 10px 10px 0;
  animation: aeo-fade-up 0.45s ease-out both;
}

.aeo-page-title {
  font-family: var(--aeo-font-display) !important;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--aeo-ink);
}

.aeo-page-url {
  font-size: 0.88rem;
  color: var(--aeo-muted);
  word-break: break-all;
  margin-top: 0.15rem;
}

.aeo-page-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 0.4rem;
  font-size: 0.85rem;
  color: var(--aeo-ink);
}

.aeo-status-ok { color: var(--aeo-ok) !important; font-weight: 600; }
.aeo-status-err { color: var(--aeo-danger) !important; font-weight: 600; }
.aeo-status-busy { color: var(--aeo-warn) !important; font-weight: 600; }

/* Readable multi-page table rows */
.aeo-panel table td {
  vertical-align: top !important;
  word-break: break-word;
  white-space: normal !important;
  font-size: 0.9rem;
}

footer, .footer { display: none !important; }

@keyframes aeo-fade-up {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

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

    return gr.themes.Soft(
        primary_hue=gr.themes.colors.teal,
        secondary_hue=gr.themes.colors.slate,
        neutral_hue=gr.themes.colors.slate,
        font=["Source Sans 3", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
        font_mono=["IBM Plex Mono", "ui-monospace", "Consolas", "monospace"],
    ).set(
        body_background_fill="#eef3f7",
        block_background_fill="rgba(255,255,255,0.82)",
        block_border_width="1px",
        block_radius="14px",
        button_primary_background_fill="#0f766e",
        button_primary_text_color="#ffffff",
        border_color_primary="rgba(15,28,46,0.10)",
    )
