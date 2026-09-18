"""Genre-conditioned quality policies (Phase 4.1).

Generic quality dimensions live in ``quality.py``. Genre-specific leak /
forbidden-template rules live here so personal_tech_blog protections stay
explicit and other genres (saas_product, ecommerce, documentation, default)
can diverge without mixing policy into the dimension evaluators.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from aeo_mvp.queries.generate import CandidateQuery
from aeo_mvp.understanding.site import SiteUnderstanding

PM_LEAK_RE = re.compile(
    r"\bproject management\b|\btask board\b|\bbest .{0,40}\btool for teams\b",
    re.I,
)
FORBIDDEN_PERSONAL_BLOG_RE = re.compile(
    r"how much does .+ cost\?|alternatives to .+|what products or services does .+ offer\?",
    re.I,
)
INDUSTRY_TOOL_RE = re.compile(r"\bother \w+ tools\b|\bbest \w+ tool\b", re.I)


@dataclass(frozen=True)
class GenreQualityPolicy:
    """Policy knobs for a site_genre."""

    genre_key: str
    forbid_commercial_templates: bool = False
    forbid_pm_without_industry: bool = True
    forbid_pm_on_personal_blog: bool = False
    forbid_industry_tool_when_omitted: bool = True


_POLICIES: dict[str, GenreQualityPolicy] = {
    "personal_tech_blog": GenreQualityPolicy(
        genre_key="personal_tech_blog",
        forbid_commercial_templates=True,
        forbid_pm_without_industry=True,
        forbid_pm_on_personal_blog=True,
        forbid_industry_tool_when_omitted=True,
    ),
    "saas_product": GenreQualityPolicy(
        genre_key="saas_product",
        forbid_commercial_templates=False,
        forbid_pm_without_industry=True,
        forbid_pm_on_personal_blog=False,
        forbid_industry_tool_when_omitted=True,
    ),
    "ecommerce": GenreQualityPolicy(
        genre_key="ecommerce",
        forbid_commercial_templates=False,
        forbid_pm_without_industry=True,
        forbid_pm_on_personal_blog=False,
        forbid_industry_tool_when_omitted=True,
    ),
    "documentation": GenreQualityPolicy(
        genre_key="documentation",
        forbid_commercial_templates=False,
        forbid_pm_without_industry=True,
        forbid_pm_on_personal_blog=False,
        forbid_industry_tool_when_omitted=True,
    ),
    "default": GenreQualityPolicy(
        genre_key="default",
        forbid_commercial_templates=False,
        forbid_pm_without_industry=True,
        forbid_pm_on_personal_blog=False,
        forbid_industry_tool_when_omitted=True,
    ),
}


def resolve_genre_policy(site_genre: str | None) -> GenreQualityPolicy:
    g = (site_genre or "").strip().lower()
    if g in _POLICIES:
        return _POLICIES[g]
    if g in ("personal_blog", "blog", "personal_tech_blog"):
        return _POLICIES["personal_tech_blog"]
    if g in ("saas", "saas_product", "b2b_saas"):
        return _POLICIES["saas_product"]
    if g in ("docs", "documentation", "developer_docs"):
        return _POLICIES["documentation"]
    if g in ("ecommerce", "e-commerce", "shop"):
        return _POLICIES["ecommerce"]
    return _POLICIES["default"]


def industry_leak_detail(
    q: CandidateQuery,
    understanding: SiteUnderstanding,
) -> tuple[str, str] | None:
    """Return (status, detail) if WEAK_INDUSTRY_LEAK fails; else None."""
    policy = resolve_genre_policy(understanding.site_genre)
    text = q.text
    industry = understanding.industry_category_guess

    if policy.forbid_commercial_templates and FORBIDDEN_PERSONAL_BLOG_RE.search(text):
        return (
            "fail",
            "forbidden commercial/alternatives template for personal_tech_blog",
        )

    if PM_LEAK_RE.search(text):
        if policy.forbid_pm_without_industry and industry != "project_management":
            return (
                "fail",
                "project_management language without assertive industry evidence",
            )
        if policy.forbid_pm_on_personal_blog:
            return (
                "fail",
                "PM language incompatible with personal_tech_blog genre",
            )

    if (
        policy.forbid_industry_tool_when_omitted
        and industry is None
        and INDUSTRY_TOOL_RE.search(text)
    ):
        return (
            "fail",
            "industry tool template while industry_category omitted",
        )
    return None


def policy_snapshot(site_genre: str | None) -> dict[str, Any]:
    p = resolve_genre_policy(site_genre)
    return {
        "genre_key": p.genre_key,
        "forbid_commercial_templates": p.forbid_commercial_templates,
        "forbid_pm_without_industry": p.forbid_pm_without_industry,
        "forbid_pm_on_personal_blog": p.forbid_pm_on_personal_blog,
        "forbid_industry_tool_when_omitted": p.forbid_industry_tool_when_omitted,
    }
