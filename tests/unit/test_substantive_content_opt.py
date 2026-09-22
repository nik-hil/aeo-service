"""Tests A–K: substantive evidence-grounded content optimization (post PR #44)."""

from __future__ import annotations

import inspect

from aeo_mvp.content.models import DEFERRED_OP_KINDS, IMPLEMENTED_OP_KINDS
from aeo_mvp.content.rewrite_proposal import (
    enrich_ops_with_rewrite_proposals,
    propose_introduction_rewrite,
)
from aeo_mvp.content.substantive_ops import (
    build_substantive_change_plan,
    propose_add_definition,
    propose_clarify_relationship,
    propose_process_summary,
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

The idea is deliberately incremental.

```text
v0.1 → basic tool calling
v0.2 → filesystem tools
v0.3 → shell execution
```

The project is called Agents Zero 2 Hero.

The LLM supplies the intelligence.

The harness provides the mechanism through which that intelligence can interact with the outside world.

## The agent loop

The most important concept in the entire project is the agent loop.

At a high level the loop calls the model and tools repeatedly.

> The model decides what should happen. The harness controls how it happens.

That distinction becomes extremely important as an agent becomes more capable.

## Our first two tools

At v0.1 the harness exposes execute_code and finish.

```python
while True:
    response = client.chat.completions.create(messages=messages, tools=TOOL_SCHEMAS)
```
"""

AGENTS_DEF_SOURCE = (
    "An LLM becomes an agent when it can decide to take actions, invoke "
    "capabilities outside the model, observe the result, and continue working "
    "until the task is complete."
)

GAPS_THIN = [
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
    {
        "gap_id": "gap_thin_building",
        "id": "gap_thin_building",
        "gap_type": "thin_coverage",
        "kind": "thin_passage",
        "query_id": "q_what_building",
        "query_ids": ["q_what_building"],
        "page_coverage": "thin",
        "rationale": "Query under-covered in building section",
        "explanation": "Query under-covered in building section",
        "evidence": [{"snippet": "incremental idea"}],
    },
    {
        "gap_id": "gap_howto_loop",
        "id": "gap_howto_loop",
        "gap_type": "no_answer_block",
        "kind": "missing_steps",
        "query_id": "q_agent_loop",
        "query_ids": ["q_agent_loop"],
        "page_coverage": "thin",
        "rationale": "Agent loop process not scannable",
        "explanation": "Agent loop process not scannable",
        "evidence": [{"snippet": "loop"}],
    },
]

COVERAGE = [
    {
        "query_id": "q_what_is_agent",
        "query_text": "what is an AI agent",
        "page_coverage": "thin",
    },
    {
        "query_id": "q_what_building",
        "query_text": "what exactly are we building in Agents Zero to Hero",
        "page_coverage": "thin",
    },
    {
        "query_id": "q_agent_loop",
        "query_text": "how does the agent loop work",
        "page_coverage": "thin",
    },
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
]


def _pi(**extra):
    base = {
        "h1": ARTICLE_H1,
        "title": ARTICLE_H1,
        "answerability_signals": {"answer_first_heuristic": False},
        "limits": ["no_answer_first"],
        "url": (
            "https://nik-hil.hashnode.dev/"
            "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling"
        ),
    }
    base.update(extra)
    return base


def _enrich(**kwargs):
    return enrich_ops_with_rewrite_proposals(
        list(EDIT_OPS_INTRO),
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        h1=ARTICLE_H1,
        gaps=GAPS_THIN,
        coverage_by_query=COVERAGE,
        **kwargs,
    )


def _first_para(md: str) -> str:
    parts = md.split("\n\n")
    return parts[1].strip() if len(parts) > 1 else ""


# --- A: Query→gap mapping ---


def test_a_query_gap_mapping():
    plan = build_substantive_change_plan(
        source_markdown=AGENTS_SOURCE_MD,
        gaps=GAPS_THIN,
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
    gap_qids = {g["query_id"] for g in GAPS_THIN}
    cov_qids = {c["query_id"] for c in COVERAGE}
    assert gap_qids == cov_qids


# --- B: Evidence association on every actionable change ---


def test_b_evidence_on_every_actionable_change():
    plan = build_substantive_change_plan(
        source_markdown=AGENTS_SOURCE_MD,
        gaps=GAPS_THIN,
        coverage_by_query=COVERAGE,
        page_intelligence=_pi(),
        existing_ops=EDIT_OPS_INTRO,
        h1=ARTICLE_H1,
    )
    actionable = [i for i in plan.items if i.disposition == "actionable"]
    assert actionable
    for item in actionable:
        assert item.evidence, f"missing evidence for {item.op_kind}"
        assert item.proposed_content
        assert item.related_gap_ids or item.op_kind == "rewrite_introduction"
        assert item.expected_aeo_benefit
        assert "chatgpt" not in item.expected_aeo_benefit.lower()
        assert "gemini" not in item.expected_aeo_benefit.lower()


# --- C: Substantive change (not paragraph reorder) ---


def test_c_substantive_not_reorder_only():
    enriched, proposal, _ = _enrich()
    assert proposal is not None
    assert proposal.proposed.strip() != proposal.original.strip()
    assert "An AI agent is an LLM-based system" in proposal.proposed
    orig_paras = [p.strip() for p in proposal.original.split("\n\n") if p.strip()]
    assert proposal.proposed.strip() not in orig_paras


# --- D: Unsupported gap → no invent ---


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
        }
    ]
    coverage = [
        {
            "query_id": "q_widget",
            "query_text": "what are quantum blockchain widgets",
            "page_coverage": "absent",
        }
    ]
    plan = build_substantive_change_plan(
        source_markdown=thin_md,
        gaps=gaps,
        coverage_by_query=coverage,
        page_intelligence={
            "h1": ARTICLE_H1,
            "answerability_signals": {"answer_first_heuristic": True},
        },
        h1=ARTICLE_H1,
    )
    actionable = [i for i in plan.items if i.disposition == "actionable"]
    for item in actionable:
        assert "widget" not in (item.proposed_content or "").lower()
    author = [i for i in plan.items if i.disposition == "author_input_required"]
    assert author
    assert all(i.proposed_content is None for i in author)


# --- E: Multiple changes when article supports them ---


def test_e_multiple_changes_when_supported():
    plan = build_substantive_change_plan(
        source_markdown=AGENTS_SOURCE_MD,
        gaps=GAPS_THIN,
        coverage_by_query=COVERAGE,
        page_intelligence=_pi(),
        existing_ops=EDIT_OPS_INTRO,
        h1=ARTICLE_H1,
    )
    actionable = [i for i in plan.items if i.disposition == "actionable"]
    kinds = {i.op_kind for i in actionable}
    assert "rewrite_introduction" in kinds
    non_intro = [i for i in actionable if i.op_kind != "rewrite_introduction"]
    assert non_intro, f"expected multi-op plan, got only {kinds}"
    targets = {i.target for i in actionable}
    assert len(targets) >= 2


# --- F: No forced changes when none justified ---


def test_f_no_forced_changes_when_none_justified():
    good_md = f"""# {ARTICLE_H1}

An AI agent is an LLM-based system that can decide when to take actions, use capabilities outside the model, observe their results, and continue working toward a task.

## What exactly are we building?

An AI agent harness is a system that connects model decisions to tools. The project is called Agents Zero 2 Hero.

## Done

All probes covered with answer-first leads already present.
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
    actionable = [i for i in plan.items if i.disposition == "actionable"]
    assert actionable == []


# --- G: Generator apply/validate-only ---


def test_g_generator_apply_validate_only():
    src = inspect.getsource(md_gen)
    assert "enrich_ops_with_rewrite_proposals(" not in src
    assert "propose_introduction_rewrite(" not in src
    assert "build_substantive_change_plan(" not in src
    assert "from aeo_mvp.content.rewrite_proposal import validate_proposed_rewrite" in src

    enriched, proposal, _ = _enrich()
    assert proposal is not None
    ops = []
    for op in enriched:
        if str(op.get("op_kind") or "") == "_substantive_change_plan":
            continue
        row = dict(op)
        if row.get("op_kind") not in {None, "rewrite_introduction"} and row.get(
            "proposed"
        ):
            row["proposed"] = None
            row["disposition"] = "author_input_required"
        ops.append(row)
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": ops},
        edit_ops=ops,
    )
    assert proposal.proposed.strip() in result.body


# --- H: Markdown integrity / structural preservation ---


def test_h_markdown_integrity_structural_preservation():
    enriched, _, _ = _enrich()
    ops = [
        op
        for op in enriched
        if str(op.get("op_kind") or "") != "_substantive_change_plan"
    ]
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief={
            "edit_ops": ops,
            "proposed_meta_description": (
                "Build an AI agent from scratch with tool calling."
            ),
        },
        edit_ops=ops,
        gaps=GAPS_THIN,
    )
    assert result.body.splitlines()[0] == f"# {ARTICLE_H1}"
    assert "## What exactly are we building?" in result.body
    assert "## The agent loop" in result.body
    assert "```python" in result.body
    assert "```text" in result.body
    assert "<meta" not in result.body
    assert "https://github.com/nik-hil/agents-zero-2-hero" in result.body


# --- I: Idempotence ---


def test_i_idempotence():
    enriched, _, _ = _enrich()
    ops = [
        op
        for op in enriched
        if str(op.get("op_kind") or "") != "_substantive_change_plan"
    ]
    first = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": ops},
        edit_ops=ops,
        gaps=GAPS_THIN,
    )
    second = generate_recommended_markdown(
        source_markdown=first.body,
        page_intelligence=_pi(
            answerability_signals={"answer_first_heuristic": True}, limits=[]
        ),
        brief={"edit_ops": ops},
        edit_ops=ops,
        gaps=GAPS_THIN,
    )
    third = generate_recommended_markdown(
        source_markdown=first.body,
        page_intelligence=_pi(
            answerability_signals={"answer_first_heuristic": True}, limits=[]
        ),
        brief={"edit_ops": ops},
        edit_ops=ops,
        gaps=GAPS_THIN,
    )
    assert second.body == third.body
    assert first.body.splitlines()[0] == third.body.splitlines()[0]


# --- J: Hashnode HTML path still gets MD + recommended MD ---


def test_j_hashnode_html_path_recommended_md():
    from aeo_mvp.content.service import _attach_hashnode_recommended_markdown

    wire = {
        "page_intelligence": _pi(),
        "content_gaps": [
            {
                "gaps": GAPS_THIN,
                "coverage_by_query": COVERAGE,
            }
        ],
        "optimization_briefs": [
            {
                "edit_ops": EDIT_OPS_INTRO,
                "proposed_meta_description": (
                    "Build an AI agent from scratch with tool calling."
                ),
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


# --- K: PR #44 regression — Agents Zero-to-Hero semantic intro rewrite ---


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
    ops = [
        op
        for op in enriched
        if str(op.get("op_kind") or "") != "_substantive_change_plan"
    ]
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": ops},
        edit_ops=ops,
        gaps=GAPS_THIN,
    )
    assert result.changed is True
    first = _first_para(result.body)
    assert "Building an AI agent sounds deceptively simple" not in first
    assert "agent" in first.lower() and "llm" in first.lower()
    assert proposal.proposed.strip() in result.body
    assert "evidence_grounded_rewrite:introduction" in result.applied_ops


def test_contract_op_kinds_implemented_vs_deferred():
    assert "rewrite_introduction" in IMPLEMENTED_OP_KINDS
    assert "rewrite_section" in IMPLEMENTED_OP_KINDS
    assert "add_definition" in IMPLEMENTED_OP_KINDS
    assert "add_process_summary" in IMPLEMENTED_OP_KINDS
    assert "strengthen_example" in DEFERRED_OP_KINDS
    assert "improve_conclusion" in DEFERRED_OP_KINDS


def test_helpers_ground_definition_and_relationship():
    definition = propose_add_definition(
        source_markdown=AGENTS_SOURCE_MD,
        heading="What exactly are we building?",
        related_gap_ids=["gap_thin_building"],
    )
    assert definition is not None
    assert definition.disposition == "actionable"
    assert definition.evidence

    relation = propose_clarify_relationship(
        source_markdown=AGENTS_SOURCE_MD,
        heading="The agent loop",
        related_gap_ids=["gap_howto_loop"],
    )
    assert relation is not None
    assert "model decides" in (relation.proposed_content or "").lower()

    process = propose_process_summary(
        source_markdown=AGENTS_SOURCE_MD,
        heading="What exactly are we building?",
        related_gap_ids=["gap_thin_building"],
    )
    if process is not None:
        assert process.evidence
        assert process.proposed_content
        assert "v0.1" in process.proposed_content
