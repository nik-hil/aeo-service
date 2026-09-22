"""Focused tests: Hashnode MD evidence-grounded rewrite (tests A–N)."""

from __future__ import annotations

from aeo_mvp.content.rewrite_proposal import (
    propose_introduction_rewrite,
    validate_proposed_rewrite,
)
from aeo_mvp.platform.hashnode.markdown_generator import (
    generate_recommended_markdown,
)

ARTICLE_H1 = (
    "Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling"
)

AGENTS_SOURCE_MD = f"""# {ARTICLE_H1}

Building an AI agent sounds deceptively simple.

Call an LLM. Give it a prompt. Get an answer.

But that is not really an agent.

An LLM becomes an agent when it can decide to take actions, invoke capabilities outside the model, observe the result, and continue working until the task is complete.

That sounds complicated when described using terms like agentic workflows.

So instead of starting with a framework, I decided to build one myself.

This repository is my attempt to understand the mechanics of an AI agent harness from first principles.

Repository:

https://github.com/nik-hil/agents-zero-2-hero

## What exactly are we building?

The project is called **Agents Zero 2 Hero**.

The idea is deliberately incremental.

## The agent loop

```python
while True:
    response = client.chat.completions.create(
        messages=messages,
        tools=TOOL_SCHEMAS,
    )
```

## Our first two tools

- list tools carefully
- read the docs
- write tests

> The model decides what should happen.

| Tool | Purpose |
| --- | --- |
| execute_code | run python |
"""

# Definitional source sentence used as evidence for the Agents fixture.
AGENTS_DEF_SOURCE = (
    "An LLM becomes an agent when it can decide to take actions, invoke "
    "capabilities outside the model, observe the result, and continue working "
    "until the task is complete."
)

CHANGE_PLAN_INTRO = [
    {
        "action": "retain",
        "target": "h1",
        "reason": f"Existing H1 present ({ARTICLE_H1!r}); keep single H1",
        "related_gap_ids": ["gap_thin_1"],
    },
    {
        "action": "rewrite",
        "target": f"section:{ARTICLE_H1}",
        "reason": "Answer-first introduction grounded in page topic.",
        "related_gap_ids": ["gap_thin_1"],
    },
    {
        "action": "expand",
        "target": "meta_description",
        "reason": "Tighten meta description to answer-first summary",
        "related_gap_ids": ["gap_thin_1"],
    },
]

EDIT_OPS_INTRO = [
    {
        "op_id": "op_0_retain_h1",
        "action": "retain",
        "target_locator": "h1",
        "instruction": f"Existing H1 present ({ARTICLE_H1!r}); keep single H1",
        "related_gap_ids": ["gap_thin_1"],
    },
    {
        "op_id": "op_1_rewrite_section",
        "action": "rewrite",
        "target_locator": f"section:{ARTICLE_H1}",
        "instruction": "Answer-first introduction grounded in page topic.",
        "related_gap_ids": ["gap_thin_1"],
    },
    {
        "op_id": "op_2_expand_meta_description",
        "action": "expand",
        "target_locator": "meta_description",
        "instruction": "Tighten meta description to answer-first summary",
        "related_gap_ids": ["gap_thin_1"],
    },
]

BRIEF = {
    "proposed_h1": ARTICLE_H1,
    "proposed_title": ARTICLE_H1,
    "proposed_meta_description": (
        "Stop relying on complex frameworks! Learn how to build an AI agent "
        "from first principles using plain Python, LLM tool calling, and an agent loop."
    ),
    "executive_summary": (
        f"Page '{ARTICLE_H1}' has 3 content gaps (1 under-covered probes). "
        "Page intelligence = extractable answer units."
    ),
    "edit_ops": EDIT_OPS_INTRO,
    "work_queue": CHANGE_PLAN_INTRO,
}


def _pi(**overrides):
    base = {
        "title": ARTICLE_H1,
        "h1": ARTICLE_H1,
        "meta_description": BRIEF["proposed_meta_description"],
        "word_count": 400,
        "answerability_signals": {"answer_first_heuristic": False},
        "limits": ["no_answer_first"],
        "answer_blocks": [],
    }
    base.update(overrides)
    return base


def _run(**kwargs):
    defaults = dict(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
        edit_ops=EDIT_OPS_INTRO,
    )
    defaults.update(kwargs)
    return generate_recommended_markdown(**defaults)


def _intro_text(md: str) -> str:
    return md.split("##", 1)[0]


def _first_para(md: str) -> str:
    parts = md.split("\n\n")
    # parts[0] is H1 line; parts[1] is first intro paragraph
    return parts[1].strip() if len(parts) > 1 else ""


# --- A: Actual intro rewrite — semantic difference, not paragraph move ---


def test_a_actual_intro_rewrite_semantically_different():
    result = _run()
    assert result.ok
    assert result.changed is True
    assert result.body.strip() != AGENTS_SOURCE_MD.strip()

    first = _first_para(result.body)
    # Must NOT merely move the later definitional paragraph unchanged.
    assert first != AGENTS_DEF_SOURCE
    assert first.strip() != "Building an AI agent sounds deceptively simple."
    # Must be a genuinely optimized answer-first formulation.
    assert "AI agent" in first or "agent is" in first.lower()
    assert "LLM" in first
    assert "capabilities outside the model" in first
    # Semantic rewrite marker (not reorder).
    assert "evidence_grounded_rewrite:introduction" in result.applied_ops
    assert "constrained_rewrite:answer_first_reorder" not in result.applied_ops
    assert "intro_rewrite_applied_from_proposed" in result.warnings
    # Proposed must not equal any single source paragraph (not a move).
    src_paras = [
        p.strip()
        for p in _intro_text(AGENTS_SOURCE_MD).split("\n\n")
        if p.strip() and not p.strip().startswith("#")
    ]
    assert first not in src_paras


# --- B: Proposed replacement actually applied ---


def test_b_proposed_replacement_actually_applied():
    result = _run()
    assert result.rewrite_provenance is not None
    proposed = result.rewrite_provenance["proposed"]
    assert proposed
    assert proposed.strip() in result.body
    assert result.body.startswith(f"# {ARTICLE_H1}\n")
    # Body intro equals proposed (H1 preserved separately).
    intro = _intro_text(result.body)
    assert proposed.strip() in intro
    assert "op_1_rewrite_section" in result.applied_ops


# --- C: Rewrite uses only supported evidence ---


def test_c_rewrite_uses_only_supported_evidence():
    result = _run()
    prov = result.rewrite_provenance
    assert prov is not None
    evidence = prov["evidence"]
    assert evidence
    assert any("LLM becomes an agent" in e for e in evidence)
    # Every evidence string must appear in source.
    for e in evidence:
        assert e in AGENTS_SOURCE_MD
    # Proposed validated against evidence.
    hard = [
        w
        for w in validate_proposed_rewrite(
            proposed=prov["proposed"],
            original=prov["original"],
            evidence=evidence,
            source_markdown=AGENTS_SOURCE_MD,
            h1=ARTICLE_H1,
        )
        if w
        in {
            "proposed_invented_url",
            "proposed_invented_fact",
            "proposed_html_injection",
            "proposed_diagnostic_leak",
        }
        or w.startswith("proposed_ungrounded_tokens:")
    ]
    assert hard == []


# --- D: No invented facts ---


def test_d_no_invented_facts():
    result = _run()
    assert "99%" not in result.body
    assert "according to" not in result.body.lower()
    assert "research shows" not in result.body.lower()
    assert "2024 study" not in result.body.lower()
    assert "content gaps" not in result.body
    assert "under-covered probes" not in result.body


# --- E: No invented URLs / citations ---


def test_e_no_invented_urls_or_citations():
    result = _run()
    assert "https://example.com/made-up" not in result.body
    assert "https://github.com/nik-hil/agents-zero-2-hero" in result.body
    # No new URL hosts vs source.
    import re

    src_urls = set(re.findall(r"https?://[^\s)>\]]+", AGENTS_SOURCE_MD))
    out_urls = set(re.findall(r"https?://[^\s)>\]]+", result.body))
    assert out_urls <= src_urls


# --- F: H1 preserved ---


def test_f_h1_preserved():
    result = _run()
    assert result.body.splitlines()[0] == f"# {ARTICLE_H1}"
    assert result.body.count(f"# {ARTICLE_H1}") == 1
    assert not result.body.lstrip().startswith("# #")


# --- G: Headings preserved ---


def test_g_headings_preserved():
    result = _run()
    assert "## What exactly are we building?" in result.body
    assert "## The agent loop" in result.body
    assert "## Our first two tools" in result.body
    assert "invariant_headings_altered" not in result.warnings


# --- H: Code blocks preserved exactly ---


def test_h_code_blocks_preserved_exactly():
    result = _run()
    expected_fence = (
        "```python\n"
        "while True:\n"
        "    response = client.chat.completions.create(\n"
        "        messages=messages,\n"
        "        tools=TOOL_SCHEMAS,\n"
        "    )\n"
        "```"
    )
    assert expected_fence in result.body
    assert "invariant_code_fence_corrupted" not in result.warnings


# --- I: Links / images / lists / tables preserved ---


def test_i_links_images_lists_tables_preserved():
    md = f"""# {ARTICLE_H1}

Building an AI agent sounds deceptively simple.

An LLM becomes an agent when it can decide to take actions, invoke capabilities outside the model, observe the result, and continue working until the task is complete.

![cover](https://cdn.hashnode.com/cover.png)

See the [repo](https://github.com/nik-hil/agents-zero-2-hero) for details.

## Steps

- first item
- second item
- third item

> quoted guidance

| Tool | Purpose |
| --- | --- |
| execute_code | run python |
"""
    result = generate_recommended_markdown(
        source_markdown=md,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
    )
    assert "![cover](https://cdn.hashnode.com/cover.png)" in result.body
    assert "[repo](https://github.com/nik-hil/agents-zero-2-hero)" in result.body
    assert "- first item" in result.body
    assert "- second item" in result.body
    assert "> quoted guidance" in result.body
    assert "| Tool | Purpose |" in result.body
    assert "| execute_code | run python |" in result.body


# --- J: Unsupported rewrite target skipped with warning ---


def test_j_unsupported_rewrite_target_skipped_with_warning():
    source = (
        f"# {ARTICLE_H1}\n\n"
        "An LLM becomes an agent when it can decide to take actions.\n\n"
        "## Details\n\nStable section.\n"
    )
    plan = [
        {
            "action": "add",
            "target": "schema:Organization",
            "reason": "Add Organization schema",
            "related_gap_ids": ["gap_1"],
        },
        {
            "action": "add",
            "target": "cross_page_link",
            "reason": "Link off-topic probe",
            "related_gap_ids": ["gap_1"],
        },
        {
            "action": "rewrite",
            "target": "section:Details",
            "reason": "Rewrite a non-intro section without proposed",
            "related_gap_ids": ["gap_1"],
        },
    ]
    result = generate_recommended_markdown(
        source_markdown=source,
        page_intelligence=_pi(
            answerability_signals={"answer_first_heuristic": True},
            limits=[],
        ),
        brief={"edit_ops": []},
        change_plan=plan,
    )
    assert result.body.strip() == source.strip()
    assert result.changed is False
    assert any(w.startswith("unsupported_edit_op:") for w in result.warnings)
    assert any("schema:organization" in w.lower() or "schema" in w for w in result.warnings)


# --- K: Metadata-only does not alter body ---


def test_k_metadata_only_does_not_alter_body():
    meta_only_plan = [
        {
            "action": "expand",
            "target": "meta_description",
            "reason": "Tighten meta description",
            "related_gap_ids": ["gap_1"],
        }
    ]
    source = (
        f"# {ARTICLE_H1}\n\n"
        "An LLM becomes an agent when it can decide to take actions.\n\n"
        "## Details\n\nMore on tool calling.\n"
    )
    result = generate_recommended_markdown(
        source_markdown=source,
        page_intelligence=_pi(
            answerability_signals={"answer_first_heuristic": True},
            limits=[],
        ),
        brief={
            "proposed_meta_description": BRIEF["proposed_meta_description"],
            "edit_ops": [
                {
                    "op_id": "op_meta",
                    "action": "expand",
                    "target_locator": "meta_description",
                    "instruction": "Tighten meta",
                }
            ],
        },
        change_plan=meta_only_plan,
    )
    assert result.body.strip() == source.strip()
    assert result.changed is False
    assert result.seo_description
    assert "<meta" not in result.body
    assert "seo_description_for_hashnode_settings" in result.warnings
    assert "seo_description_transported_from_brief" in result.warnings
    assert "metadata_only_no_body_change" in result.warnings
    assert "meta_description_does_not_drive_intro_rewrite" in result.warnings
    assert result.seo_description == BRIEF["proposed_meta_description"]


# --- L: Idempotence ---


def test_l_idempotent_on_already_optimized():
    first = _run()
    assert first.changed is True
    second = generate_recommended_markdown(
        source_markdown=first.body,
        page_intelligence=_pi(
            answerability_signals={"answer_first_heuristic": True},
            limits=[],
        ),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
        edit_ops=EDIT_OPS_INTRO,
    )
    assert second.body.strip() == first.body.strip()
    assert second.changed is False


# --- M: Provenance / evidence retained ---


def test_m_provenance_and_evidence_retained():
    result = _run()
    prov = result.rewrite_provenance
    assert prov is not None
    assert prov["action"] == "rewrite"
    assert prov["target"] == "introduction"
    assert prov["what_changed"] == "introduction"
    assert prov["why"]
    assert prov["related_gap_ids"] == ["gap_thin_1"]
    assert prov["evidence"]
    assert prov["original"]
    assert prov["proposed"]
    assert prov["llm_used"] is False
    assert prov["paid_retrieval_used"] is False
    assert "evidence_grounded_rewrite:introduction" in result.applied_ops


# --- N: Agents Zero to Hero #1 fixture — strong answer-first assertion ---


def test_n_agents_fixture_optimized_answer_first_not_mere_change_flag():
    """Regression: recommended intro must be a genuine answer-first rewrite.

    Not satisfied by result.changed is True alone, and not by moving the
    definitional paragraph unchanged to the front.
    """
    result = _run()
    assert result.changed is True

    first = _first_para(result.body)
    # Strong: answer-first formulation (definitional role-first), not teaser.
    assert "Building an AI agent sounds deceptively simple" not in first
    assert first != AGENTS_DEF_SOURCE
    # Grounded answer-first shape from the Agents source evidence.
    assert "agent" in first.lower()
    assert "llm" in first.lower()
    assert "capabilities outside the model" in first.lower()
    assert (
        "decide when to take actions" in first.lower()
        or "decide to take actions" in first.lower()
    )
    # Must look like a rewritten definition, not a relocated paragraph.
    proposal = propose_introduction_rewrite(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        related_gap_ids=["gap_thin_1"],
    )
    assert proposal is not None
    assert proposal.proposed.strip() in result.body
    assert proposal.proposed.strip() != AGENTS_DEF_SOURCE
    assert "An AI agent is an LLM-based system" in proposal.proposed


# --- Extra regressions retained from PR #43 ---


def test_integration_change_plan_nonempty_must_change_body_when_intro_op():
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
        content_drafts=[{"change_plan": CHANGE_PLAN_INTRO}],
    )
    assert CHANGE_PLAN_INTRO
    assert result.changed is True
    assert result.body.strip() != AGENTS_SOURCE_MD.strip()
    assert "<meta" not in result.body
    assert result.seo_description is not None
    assert _first_para(result.body) != AGENTS_DEF_SOURCE


def test_retain_h1_recorded_without_rewriting_title():
    result = _run()
    assert result.body.splitlines()[0] == f"# {ARTICLE_H1}"
    assert "op_0_retain_h1" in result.applied_ops or any(
        "retain" in op for op in result.applied_ops
    )


def test_meta_not_inserted_as_html_in_body():
    result = _run()
    assert "<meta" not in result.body
    assert 'name="description"' not in result.body
    assert result.seo_description
    assert "Stop relying on complex frameworks" in result.seo_description
    assert "seo_description_transported_from_brief" in result.warnings


def test_fixture_deterministic():
    a = _run()
    b = _run()
    assert a.body == b.body
    assert a.changed == b.changed
    assert a.seo_description == b.seo_description
    assert a.warnings == b.warnings
    assert a.applied_ops == b.applied_ops
    assert a.rewrite_provenance == b.rewrite_provenance


def test_rewrite_without_proposed_does_not_reorder_only():
    """Absent a grounded proposal, do not silently reorder paragraphs."""
    source = f"""# {ARTICLE_H1}

Building an AI agent sounds deceptively simple.

Totally unrelated fluff with no definitional content at all.

## Later

Body stays.
"""
    result = generate_recommended_markdown(
        source_markdown=source,
        page_intelligence=_pi(),
        brief={"edit_ops": EDIT_OPS_INTRO},
        change_plan=CHANGE_PLAN_INTRO,
        edit_ops=EDIT_OPS_INTRO,
    )
    # No definitional evidence → no rewrite / no reorder.
    assert result.body.strip() == source.strip()
    assert result.changed is False
    assert "constrained_rewrite:answer_first_reorder" not in result.applied_ops
