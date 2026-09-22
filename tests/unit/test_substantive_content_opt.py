"""Tests A–K: locked MVP slice (intro + SEO + FAQ/HowTo promote-only)."""

from __future__ import annotations

import inspect

from aeo_mvp.content.models import (
    DEFERRED_OP_KINDS,
    FAQ_MIN_EXISTING_QA_PAIRS,
    HOWTO_MIN_EXISTING_STEPS,
    IMPLEMENTED_OP_KINDS,
    ContentChangeOperation,
)
from aeo_mvp.content.rewrite_proposal import (
    enrich_ops_with_rewrite_proposals,
    propose_introduction_rewrite,
)
from aeo_mvp.content.substantive_ops import (
    build_substantive_change_plan,
    propose_faq_from_existing_qa,
    propose_howto_from_existing_steps,
)
from aeo_mvp.platform.hashnode import markdown_generator as md_gen
from aeo_mvp.platform.hashnode.markdown_generator import generate_recommended_markdown

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

The project is called Agents Zero 2 Hero.

## The agent loop

The most important concept in the entire project is the agent loop.

> The model decides what should happen. The harness controls how it happens.
"""

AGENTS_DEF_SOURCE = (
    "An LLM becomes an agent when it can decide to take actions, invoke "
    "capabilities outside the model, observe the result, and continue working "
    "until the task is complete."
)

MULTI_OP_MD = f"""# {ARTICLE_H1}

Building an AI agent sounds deceptively simple.

An LLM becomes an agent when it can decide to take actions, invoke capabilities outside the model, observe the result, and continue working until the task is complete.

## Overview

Some context.

### What is an AI agent?

An AI agent is a system that can call tools and continue until the task is complete.

### How does tool calling work?

The model selects a tool schema and the harness executes it.

### Why does the message history matter?

Prior tool results must be fed back so the model can decide the next action.

## Workflow notes

Scattered steps appear below before a dedicated Steps section exists.

1. Call the model with tool schemas
2. Execute each requested tool
3. Append tool results to messages
4. Repeat until the model finishes

## Code

```python
while True:
    response = client.chat.completions.create(messages=messages, tools=TOOL_SCHEMAS)
```
"""

GAPS_INTRO = [
    {
        "gap_id": "gap_answer_first_1",
        "id": "gap_answer_first_1",
        "gap_type": "evidence_gap",
        "kind": "missing_answer",
        "query_id": "q_what_is_agent",
        "query_ids": ["q_what_is_agent"],
        "page_coverage": "thin",
        "rationale": "Introduction is not answer-first for agent definition probe",
        "explanation": "Introduction is not answer-first for agent definition probe",
        "evidence": [{"snippet": "teaser lead"}],
    },
]

GAPS_MULTI = GAPS_INTRO + [
    {
        "gap_id": "gap_faq",
        "id": "gap_faq",
        "gap_type": "no_answer_block",
        "kind": "missing_faq",
        "query_id": "q_faq",
        "query_ids": ["q_faq"],
        "page_coverage": "thin",
        "rationale": "FAQ not assembled",
        "explanation": "FAQ not assembled",
    },
    {
        "gap_id": "gap_howto",
        "id": "gap_howto",
        "gap_type": "no_answer_block",
        "kind": "missing_steps",
        "query_id": "q_howto",
        "query_ids": ["q_howto"],
        "page_coverage": "thin",
        "rationale": "HowTo steps not assembled",
        "explanation": "HowTo steps not assembled",
    },
]

COVERAGE = [
    {"query_id": "q_what_is_agent", "query_text": "what is an AI agent", "page_coverage": "thin"},
    {"query_id": "q_faq", "query_text": "AI agent FAQ", "page_coverage": "thin"},
    {"query_id": "q_howto", "query_text": "how to run an agent loop", "page_coverage": "thin"},
]

EDIT_OPS_INTRO = [
    {
        "op_id": "op_0_retain_h1",
        "action": "retain",
        "target_locator": "h1",
        "instruction": f"Existing H1 present ({ARTICLE_H1!r}); keep single H1",
        "related_gap_ids": ["gap_answer_first_1"],
    },
    {
        "op_id": "op_1_rewrite_section",
        "action": "rewrite",
        "target_locator": f"section:{ARTICLE_H1}",
        "instruction": "Answer-first introduction grounded in page topic.",
        "related_gap_ids": ["gap_answer_first_1"],
        "related_query_ids": ["q_what_is_agent"],
    },
    {
        "op_id": "op_2_meta",
        "action": "expand",
        "target_locator": "meta_description",
        "instruction": "Tighten meta description",
        "related_gap_ids": ["gap_answer_first_1"],
    },
]


def _pi(**extra):
    base = {
        "h1": ARTICLE_H1,
        "title": ARTICLE_H1,
        "answerability_signals": {"answer_first_heuristic": False},
        "limits": ["no_answer_first"],
        "meta_description": "Build an AI agent from scratch with tool calling.",
        "url": (
            "https://nik-hil.hashnode.dev/"
            "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling"
        ),
    }
    base.update(extra)
    return base


def _first_para(md: str) -> str:
    parts = md.split("\n\n")
    return parts[1].strip() if len(parts) > 1 else ""


def _enrich(source=AGENTS_SOURCE_MD, gaps=None, ops=None, brief=None):
    return enrich_ops_with_rewrite_proposals(
        list(ops if ops is not None else EDIT_OPS_INTRO),
        source_markdown=source,
        page_intelligence=_pi(),
        h1=ARTICLE_H1,
        gaps=gaps if gaps is not None else GAPS_INTRO,
        coverage_by_query=COVERAGE,
        brief=brief
        or {"proposed_meta_description": "Build an AI agent from scratch with tool calling."},
    )


def test_a_query_gap_mapping():
    plan = build_substantive_change_plan(
        source_markdown=AGENTS_SOURCE_MD,
        gaps=GAPS_INTRO,
        coverage_by_query=COVERAGE,
        page_intelligence=_pi(),
        existing_ops=EDIT_OPS_INTRO,
        h1=ARTICLE_H1,
    )
    assert plan.items
    query_tied = [i for i in plan.items if i.related_query_ids or i.query_text]
    assert query_tied
    for item in query_tied:
        assert item.content_gap
        assert item.related_gap_ids or item.query_text


def test_b_evidence_on_every_actionable_change():
    plan = build_substantive_change_plan(
        source_markdown=MULTI_OP_MD,
        gaps=GAPS_MULTI,
        coverage_by_query=COVERAGE,
        page_intelligence=_pi(),
        existing_ops=EDIT_OPS_INTRO,
        h1=ARTICLE_H1,
        brief={"proposed_meta_description": "Build an AI agent from scratch."},
    )
    ready = [i for i in plan.items if i.status == "ready"]
    assert ready
    for item in ready:
        assert item.evidence, f"missing evidence for {item.op_kind}"
        assert item.proposed_content
        assert item.apply_mode in {"replace_region", "insert_after", "metadata_only"}
        assert "chatgpt" not in item.expected_aeo_benefit.lower()
        assert "gemini" not in item.expected_aeo_benefit.lower()


def test_c_substantive_not_reorder_only():
    enriched, proposal, _ = _enrich()
    assert proposal is not None
    assert proposal.proposed.strip() != proposal.original.strip()
    assert "An AI agent is an LLM-based system" in proposal.proposed
    orig_paras = [p.strip() for p in proposal.original.split("\n\n") if p.strip()]
    assert proposal.proposed.strip() not in orig_paras


def test_d_unsupported_gap_author_input_no_invent():
    thin_md = f"""# {ARTICLE_H1}

Only a teaser with no definitional substance at all.

## Later

Still nothing about quantum blockchain widgets.
"""
    gaps = [
        {
            "gap_id": "gap_absent_widget",
            "gap_type": "missing_page",
            "kind": "missing_answer",
            "query_id": "q_widget",
            "query_ids": ["q_widget"],
            "page_coverage": "absent",
            "rationale": "Query about quantum blockchain widgets absent",
            "explanation": "Query about quantum blockchain widgets absent",
        },
        {
            "gap_id": "gap_schema",
            "gap_type": "schema_gap",
            "kind": "unstructured",
            "query_id": "q_schema",
            "query_ids": ["q_schema"],
            "rationale": "Schema invent deferred",
            "explanation": "Schema invent deferred",
        },
    ]
    plan = build_substantive_change_plan(
        source_markdown=thin_md,
        gaps=gaps,
        coverage_by_query=[
            {
                "query_id": "q_widget",
                "query_text": "what are quantum blockchain widgets",
                "page_coverage": "absent",
            }
        ],
        page_intelligence={
            "h1": ARTICLE_H1,
            "answerability_signals": {"answer_first_heuristic": True},
        },
        h1=ARTICLE_H1,
    )
    ready = [i for i in plan.items if i.status == "ready"]
    for item in ready:
        assert "widget" not in (item.proposed_content or "").lower()
    author = [i for i in plan.items if i.status == "needs_author_input"]
    assert author
    assert all(i.proposed_content is None for i in author)


def test_e_multiple_changes_when_faq_and_howto_supported():
    plan = build_substantive_change_plan(
        source_markdown=MULTI_OP_MD,
        gaps=GAPS_MULTI,
        coverage_by_query=COVERAGE,
        page_intelligence=_pi(),
        existing_ops=EDIT_OPS_INTRO,
        h1=ARTICLE_H1,
        brief={"proposed_meta_description": "Build an AI agent from scratch."},
    )
    ready = [i for i in plan.items if i.status == "ready"]
    kinds = {i.op_kind for i in ready}
    assert "rewrite_introduction" in kinds
    assert "add_faq_from_existing_qa" in kinds
    assert "add_howto_from_existing_steps" in kinds
    assert len(ready) >= 3


def test_f_no_forced_changes_when_none_justified():
    good_md = f"""# {ARTICLE_H1}

An AI agent is an LLM-based system that can decide when to take actions, use capabilities outside the model, observe their results, and continue working toward a task.

## Done

All probes covered.
"""
    plan = build_substantive_change_plan(
        source_markdown=good_md,
        gaps=[],
        coverage_by_query=[],
        page_intelligence={
            "h1": ARTICLE_H1,
            "answerability_signals": {"answer_first_heuristic": True},
            "limits": [],
        },
        existing_ops=[],
        h1=ARTICLE_H1,
    )
    ready = [i for i in plan.items if i.status == "ready"]
    assert ready == []


def test_g_generator_apply_validate_only():
    src = inspect.getsource(md_gen)
    assert "enrich_ops_with_rewrite_proposals(" not in src
    assert "propose_introduction_rewrite(" not in src
    assert "build_substantive_change_plan(" not in src
    assert "propose_faq_from_existing_qa(" not in src
    assert "propose_howto_from_existing_steps(" not in src
    assert "from aeo_mvp.content.rewrite_proposal import validate_proposed_rewrite" in src

    enriched, proposal, _ = _enrich(source=MULTI_OP_MD, gaps=GAPS_MULTI)
    assert proposal is not None
    ops = [op for op in enriched if str(op.get("op_kind") or "") != "_substantive_change_plan"]
    result = generate_recommended_markdown(
        source_markdown=MULTI_OP_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": ops, "proposed_meta_description": "Build an AI agent from scratch."},
        edit_ops=ops,
    )
    assert proposal.proposed.strip() in result.body
    assert "quantum" not in result.body.lower()


def test_h_markdown_integrity_structural_preservation():
    enriched, _, _ = _enrich(source=MULTI_OP_MD, gaps=GAPS_MULTI)
    ops = [op for op in enriched if str(op.get("op_kind") or "") != "_substantive_change_plan"]
    result = generate_recommended_markdown(
        source_markdown=MULTI_OP_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": ops, "proposed_meta_description": "Build an AI agent from scratch."},
        edit_ops=ops,
        gaps=GAPS_MULTI,
    )
    assert result.body.splitlines()[0] == f"# {ARTICLE_H1}"
    assert "```python" in result.body
    assert "<meta" not in result.body
    assert result.seo_description


def test_i_idempotence():
    enriched, _, _ = _enrich(source=MULTI_OP_MD, gaps=GAPS_MULTI)
    ops = [op for op in enriched if str(op.get("op_kind") or "") != "_substantive_change_plan"]
    first = generate_recommended_markdown(
        source_markdown=MULTI_OP_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": ops, "proposed_meta_description": "Build an AI agent."},
        edit_ops=ops,
        gaps=GAPS_MULTI,
    )
    second = generate_recommended_markdown(
        source_markdown=first.body,
        page_intelligence=_pi(answerability_signals={"answer_first_heuristic": True}, limits=[]),
        brief={"edit_ops": ops, "proposed_meta_description": "Build an AI agent."},
        edit_ops=ops,
        gaps=GAPS_MULTI,
    )
    third = generate_recommended_markdown(
        source_markdown=first.body,
        page_intelligence=_pi(answerability_signals={"answer_first_heuristic": True}, limits=[]),
        brief={"edit_ops": ops, "proposed_meta_description": "Build an AI agent."},
        edit_ops=ops,
        gaps=GAPS_MULTI,
    )
    assert second.body == third.body


def test_j_hashnode_html_path_recommended_md():
    from aeo_mvp.content.service import _attach_hashnode_recommended_markdown

    wire = {
        "page_intelligence": _pi(),
        "content_gaps": [{"gaps": GAPS_INTRO, "coverage_by_query": COVERAGE}],
        "optimization_briefs": [
            {
                "edit_ops": EDIT_OPS_INTRO,
                "proposed_meta_description": "Build an AI agent from scratch with tool calling.",
            }
        ],
        "content_drafts": [],
    }
    out = _attach_hashnode_recommended_markdown(
        wire,
        page_url=(
            "https://nik-hil.hashnode.dev/"
            "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling"
        ),
        title=ARTICLE_H1,
        source_markdown=AGENTS_SOURCE_MD,
        content_representation="markdown",
        source_url=(
            "https://nik-hil.hashnode.dev/"
            "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md"
        ),
        canonical_url=(
            "https://nik-hil.hashnode.dev/"
            "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling"
        ),
    )
    draft = (out.get("content_drafts") or [None])[0]
    assert draft is not None
    assert draft.get("body_markdown")
    assert draft["body_markdown"].startswith(f"# {ARTICLE_H1}")
    assert draft.get("changed") is True
    assert out.get("page_intelligence", {}).get("recommended_markdown")
    assert out.get("substantive_change_plan") or (out.get("brief") or {}).get(
        "substantive_change_plan"
    )


def test_k_pr44_agents_intro_rewrite_regression():
    proposal = propose_introduction_rewrite(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        related_gap_ids=["gap_answer_first_1"],
    )
    assert proposal is not None
    assert "An AI agent is an LLM-based system" in proposal.proposed
    assert proposal.proposed.strip() != AGENTS_DEF_SOURCE

    enriched, prop2, _ = _enrich()
    assert prop2 is not None
    ops = [op for op in enriched if str(op.get("op_kind") or "") != "_substantive_change_plan"]
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": ops, "proposed_meta_description": "Build an AI agent from scratch."},
        edit_ops=ops,
        gaps=GAPS_INTRO,
    )
    assert result.changed is True
    first = _first_para(result.body)
    assert "Building an AI agent sounds deceptively simple" not in first
    assert "agent" in first.lower() and "llm" in first.lower()
    assert proposal.proposed.strip() in result.body
    assert "evidence_grounded_rewrite:introduction" in result.applied_ops
    assert result.seo_description
    assert "<meta" not in result.body


def test_contract_mvp_op_kinds():
    assert IMPLEMENTED_OP_KINDS == frozenset(
        {
            "rewrite_introduction",
            "metadata_seo_description",
            "add_faq_from_existing_qa",
            "add_howto_from_existing_steps",
        }
    )
    assert "rewrite_section" in DEFERRED_OP_KINDS
    assert "clarify_relationship" in DEFERRED_OP_KINDS
    assert FAQ_MIN_EXISTING_QA_PAIRS >= 2
    assert HOWTO_MIN_EXISTING_STEPS >= 3
    op = ContentChangeOperation(
        action="add",
        target_kind="faq",
        target_locator="section:FAQ",
        apply_mode="insert_after",
        status="ready",
        op_kind="add_faq_from_existing_qa",
        proposed="## FAQ\n",
        evidence=["Q"],
    )
    wire = op.to_edit_op_dict()
    assert wire["status"] == "ready"
    assert wire["apply_mode"] == "insert_after"


def test_faq_howto_promote_or_author_input():
    faq_ok = propose_faq_from_existing_qa(source_markdown=MULTI_OP_MD)
    assert faq_ok.status == "ready"
    assert faq_ok.proposed_content and "## FAQ" in faq_ok.proposed_content
    assert "What is an AI agent?" in faq_ok.proposed_content

    faq_no = propose_faq_from_existing_qa(source_markdown=AGENTS_SOURCE_MD)
    assert faq_no.status == "needs_author_input"
    assert faq_no.proposed_content is None

    howto_ok = propose_howto_from_existing_steps(source_markdown=MULTI_OP_MD)
    assert howto_ok.status == "ready"
    assert howto_ok.proposed_content and "## Steps" in howto_ok.proposed_content

    howto_no = propose_howto_from_existing_steps(source_markdown=AGENTS_SOURCE_MD)
    assert howto_no.status == "needs_author_input"
    assert howto_no.proposed_content is None


def test_no_proposed_intro_skips_without_reorder():
    source = f"""# {ARTICLE_H1}

Building an AI agent sounds deceptively simple.

Totally unrelated fluff with no definitional content at all.

## Later

Body stays.
"""
    enriched, proposal, _ = enrich_ops_with_rewrite_proposals(
        list(EDIT_OPS_INTRO),
        source_markdown=source,
        page_intelligence=_pi(),
        gaps=GAPS_INTRO,
    )
    assert proposal is None
    ops = [op for op in enriched if str(op.get("op_kind") or "") != "_substantive_change_plan"]
    result = generate_recommended_markdown(
        source_markdown=source,
        page_intelligence=_pi(),
        brief={"edit_ops": ops},
        edit_ops=ops,
    )
    assert result.body.strip() == source.strip()
    assert result.changed is False
