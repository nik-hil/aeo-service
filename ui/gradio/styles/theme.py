"""Gradio theme + CSS for a polished B2B SaaS leadership aesthetic.

Direction: cool slate + teal accent, soft grid atmosphere, expressive type.
Avoid purple-on-white / cream-serif / broadsheet clichés.
"""

from __future__ import annotations

CUSTOM_CSS = """
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
}

html, body, .gradio-container {
  font-family: "Source Sans 3", "Segoe UI", sans-serif !important;
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
  font-family: "Fraunces", Georgia, serif !important;
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

.aeo-kpi {
  font-family: "Fraunces", Georgia, serif !important;
  font-size: 2rem !important;
  color: var(--aeo-accent) !important;
}

.aeo-status-ok { color: var(--aeo-ok) !important; font-weight: 600; }
.aeo-status-err { color: var(--aeo-danger) !important; font-weight: 600; }
.aeo-status-busy { color: var(--aeo-warn) !important; font-weight: 600; }

footer, .footer { display: none !important; }

@keyframes aeo-fade-up {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 1100px) {
  .gradio-container { padding-left: 1rem !important; padding-right: 1rem !important; }
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
        font=gr.themes.GoogleFont("Source Sans 3"),
        font_mono=gr.themes.GoogleFont("IBM Plex Mono"),
    ).set(
        body_background_fill="#eef3f7",
        block_background_fill="rgba(255,255,255,0.82)",
        block_border_width="1px",
        block_radius="14px",
        button_primary_background_fill="#0f766e",
        button_primary_text_color="#ffffff",
        border_color_primary="rgba(15,28,46,0.10)",
    )
