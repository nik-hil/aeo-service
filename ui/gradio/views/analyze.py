"""Analyze form helpers."""

from __future__ import annotations

from typing import Any

from services.adapters import UI_MULTI_MAX_PAGES


def build_job_options(*, mode: str, use_demo: bool, include_draft: bool) -> dict[str, Any]:
    """Build API job options. Multi-page ``max_pages`` uses ``UI_MULTI_MAX_PAGES`` (≤ backend ceiling)."""
    options: dict[str, Any] = {
        "provider": "demo" if use_demo else "auto",
        "content_optimization": True,
        "content_draft": bool(include_draft or use_demo),
    }
    if mode == "single":
        options["max_pages"] = 1
        options["max_depth"] = 0
    else:
        # Shared with app.py via UI_MULTI_MAX_PAGES (≤ BACKEND_MAX_PAGES_CEILING).
        options["max_pages"] = UI_MULTI_MAX_PAGES
        options["max_depth"] = 2
    return options
