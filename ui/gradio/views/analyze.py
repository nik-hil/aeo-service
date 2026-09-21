"""Analyze form helpers."""

from __future__ import annotations

from typing import Any


def build_job_options(*, mode: str, use_demo: bool, include_draft: bool) -> dict[str, Any]:
    options: dict[str, Any] = {
        "provider": "demo" if use_demo else "auto",
        "content_optimization": True,
        "content_draft": bool(include_draft or use_demo),
    }
    if mode == "single":
        options["max_pages"] = 1
        options["max_depth"] = 0
    else:
        options["max_pages"] = 10
        options["max_depth"] = 2
    return options
