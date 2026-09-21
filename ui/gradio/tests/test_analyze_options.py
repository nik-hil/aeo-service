"""Job-options helper stays aligned with UI_MULTI_MAX_PAGES."""

from __future__ import annotations

from services.adapters import BACKEND_MAX_PAGES_CEILING, UI_MULTI_MAX_PAGES
from views.analyze import build_job_options


def test_build_job_options_multi_uses_shared_cap():
    opts = build_job_options(mode="multi", use_demo=False, include_draft=True)
    assert opts["max_pages"] == UI_MULTI_MAX_PAGES
    assert opts["max_pages"] >= 20
    assert opts["max_pages"] <= BACKEND_MAX_PAGES_CEILING
    assert BACKEND_MAX_PAGES_CEILING == 25
    assert opts["max_depth"] == 2
    assert opts["provider"] == "auto"
    assert opts["content_draft"] is True


def test_build_job_options_single_is_one_page():
    opts = build_job_options(mode="single", use_demo=True, include_draft=False)
    assert opts["max_pages"] == 1
    assert opts["max_depth"] == 0
    assert opts["provider"] == "demo"
    # demo forces draft request
    assert opts["content_draft"] is True


def test_ui_multi_cap_cannot_exceed_backend_ceiling():
    assert 20 <= UI_MULTI_MAX_PAGES <= BACKEND_MAX_PAGES_CEILING
