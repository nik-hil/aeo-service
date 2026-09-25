---
name: aeo-gradio-ui
description: Use when changing Gradio under ui/gradio/ or demo UX for aeo-service.
---
# Gradio UI changes

## Do
- Wire to existing pipeline outputs only (`ui/gradio/app.py`).
- Keep OBSERVED vs LLM-GENERATED labeling.
- Preserve scrollable CURRENT / RECOMMENDED / DIFF when showing packs.
- Add/adjust Gradio tests when behavior changes.

## Don't
- Embed crawl/score/optimize logic in the UI.
- Inject untrusted HTML.
- Claim visual done from code review alone.

## Acceptance
PR description must say: **User must run `python ui/gradio/app.py` locally and visually accept before merge.**
