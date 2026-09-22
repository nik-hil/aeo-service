"""Focused tests: Hashnode MD generator applies supported change-plan edit ops."""

from __future__ import annotations

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


# --- A: rewrite-intro → differs from source ---


def test_a_rewrite_intro_differs_from_source():
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
        edit_ops=EDIT_OPS_INTRO,
    )
    assert result.ok
    assert result.changed is True
    assert result.body.strip() != AGENTS_SOURCE_MD.strip()
    # Answer-first lead should surface the declarative agent definition early.
    assert "An LLM becomes an agent when it can decide to take actions" in result.body
    first_para = result.body.split("\n\n", 2)[1]
    assert "An LLM becomes an agent" in first_para
    assert first_para.strip() != "Building an AI agent sounds deceptively simple."


# --- B: preserves H1 / body sections ---


def test_b_preserves_h1_and_body_sections():
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
    )
    assert result.body.startswith(f"# {ARTICLE_H1}\n")
    assert "## What exactly are we building?" in result.body
    assert "## The agent loop" in result.body
    assert "## Our first two tools" in result.body
    assert "The project is called **Agents Zero 2 Hero**." in result.body


# --- C: no invented facts ---


def test_c_no_invented_facts_or_urls():
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
    )
    # Every non-blank content line under intro should come from source facts.
    assert "99%" not in result.body
    assert "according to" not in result.body.lower()
    assert "https://example.com/made-up" not in result.body
    # Repo link preserved, not invented.
    assert "https://github.com/nik-hil/agents-zero-2-hero" in result.body
    # Diagnostic executive_summary must not leak into body.
    assert "content gaps" not in result.body
    assert "under-covered probes" not in result.body


# --- D: metadata-only → body unchanged, changed=false ---


def test_d_metadata_only_body_unchanged():
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
    assert "metadata_only_no_body_change" in result.warnings
    # Meta alone must not drive intro rewrite.
    assert "meta_description_does_not_drive_intro_rewrite" in result.warnings


# --- E: supported op applied → changed=true ---


def test_e_supported_intro_op_sets_changed_true():
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
    )
    assert result.changed is True
    assert result.body.strip() != AGENTS_SOURCE_MD.strip()
    assert any("rewrite" in op or "introduction" in op for op in result.applied_ops) or (
        "op_1_rewrite_section" in result.applied_ops
    )


# --- F: unsupported → preserved + warning ---


def test_f_unsupported_op_preserved_with_warning():
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


# --- G: code blocks exact ---


def test_g_code_blocks_preserved_exactly():
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
    )
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


# --- H: links / images / lists preserved ---


def test_h_links_images_lists_preserved():
    md = f"""# {ARTICLE_H1}

Building an AI agent sounds deceptively simple.

An LLM becomes an agent when it can decide to take actions outside the model.

![cover](https://cdn.hashnode.com/cover.png)

See the [repo](https://github.com/nik-hil/agents-zero-2-hero) for details.

## Steps

- first item
- second item
- third item

> quoted guidance
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


# --- I: fixture deterministic ---


def test_i_fixture_deterministic():
    kwargs = dict(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
        edit_ops=EDIT_OPS_INTRO,
    )
    a = generate_recommended_markdown(**kwargs)
    b = generate_recommended_markdown(**kwargs)
    assert a.body == b.body
    assert a.changed == b.changed
    assert a.seo_description == b.seo_description
    assert a.warnings == b.warnings
    assert a.applied_ops == b.applied_ops


# --- J: idempotence on already-optimized MD ---


def test_j_idempotent_on_already_optimized():
    first = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
    )
    second = generate_recommended_markdown(
        source_markdown=first.body,
        page_intelligence=_pi(
            answerability_signals={"answer_first_heuristic": True},
            limits=[],
        ),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
    )
    assert second.body.strip() == first.body.strip()
    # Re-running on optimized body should not churn further.
    assert second.changed is False or second.body.strip() == first.body.strip()


# --- Integration regression: nonempty change_plan must not leave body==source ---


def test_integration_change_plan_nonempty_must_change_body_when_intro_op():
    """Regression: change_plan with rewrite intro must not yield CURRENT==RECOMMENDED."""
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
        content_drafts=[{"change_plan": CHANGE_PLAN_INTRO}],
    )
    assert CHANGE_PLAN_INTRO  # nonempty
    assert result.changed is True
    assert result.body.strip() != AGENTS_SOURCE_MD.strip()
    assert "<meta" not in result.body
    assert result.seo_description is not None


def test_retain_h1_recorded_without_rewriting_title():
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
    )
    assert result.body.splitlines()[0] == f"# {ARTICLE_H1}"
    assert "op_0_retain_h1" in result.applied_ops or any(
        "retain" in op for op in result.applied_ops
    )


def test_meta_not_inserted_as_html_in_body():
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
    )
    assert "<meta" not in result.body
    assert 'name="description"' not in result.body
    assert result.seo_description
    assert "Stop relying on complex frameworks" in result.seo_description
