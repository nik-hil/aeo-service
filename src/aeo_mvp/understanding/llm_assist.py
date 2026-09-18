"""Optional LLM assist for SiteProfile (opt-in only; never silent overwrite)."""

from __future__ import annotations

from aeo_mvp.understanding.profile import (
    SiteProfileField,
    StructuredSiteProfile,
    merge_llm_field,
)


def apply_llm_assist(
    profile: StructuredSiteProfile,
    *,
    enabled: bool,
    api_key: str | None,
    provider: str = "openai_compatible",
    model: str | None = None,
    prompt_version: str = "site-profile-llm-v0",
) -> StructuredSiteProfile:
    """No-op stub: records opt-in without calling paid APIs.

    When implemented, LLM fields must go through merge_llm_field so
    deterministic conf≥0.70 cannot be overwritten without justification.
    """
    if not enabled or not api_key:
        return profile
    profile.warnings.append(
        f"llm_assist_opt_in_unimplemented:provider={provider}:prompt={prompt_version}"
    )
    profile.method = f"{profile.method}+llm_flag_acknowledged_unimplemented"
    # Demonstrate merge guard is available for future wiring
    _ = merge_llm_field
    _ = SiteProfileField
    _ = model
    return profile
