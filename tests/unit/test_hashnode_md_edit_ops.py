"""Focused tests: Hashnode MD evidence-grounded rewrite + opt-layer boundary."""

from __future__ import annotations

import inspect
import re

from aeo_mvp.content.rewrite_proposal import (
    enrich_ops_with_rewrite_proposals,
    propose_introduction_rewrite,
    validate_proposed_rewrite,
)
from aeo_mvp.platform.hashnode import markdown_generator as md_gen
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


def _enrich_ops(
    source_md: str = AGENTS_SOURCE_MD,
    ops: list | None = None,
    pi: dict | None = None,
):
    """Content-optimization layer: attach original/proposed/evidence onto ops."""
    return enrich_ops_with_rewrite_proposals(
        list(ops if ops is not None else EDIT_OPS_INTRO),
        source_markdown=source_md,
        page_intelligence=pi or _pi(),
    )


def _run(**kwargs):
    """Apply path: opt-layer enriches proposals, then generator consumes them."""
    defaults = dict(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=CHANGE_PLAN_INTRO,
        edit_ops=EDIT_OPS_INTRO,
    )
    defaults.update(kwargs)
    md = defaults["source_markdown"]
    pi = defaults.get("page_intelligence") or _pi()
    seed = list(defaults.get("edit_ops") or defaults.get("change_plan") or [])
    # Skip enrichment when caller already supplied proposed (or empty seed).
    already = any(
        isinstance(op, dict)
        and isinstance(op.get("proposed"), str)
        and op["proposed"].strip()
        for op in seed
    )
    if seed and not already and kwargs.get("skip_enrich") is not True:
        enriched, _proposal, _warn = enrich_ops_with_rewrite_proposals(
            seed,
            source_markdown=md,
            page_intelligence=pi,
        )
        defaults["edit_ops"] = enriched
        defaults["change_plan"] = enriched
        brief = dict(defaults.get("brief") or {})
        brief["edit_ops"] = enriched
        defaults["brief"] = brief
    defaults.pop("skip_enrich", None)
    return generate_recommended_markdown(**defaults)


def _intro_text(md: str) -> str:
    return md.split("##", 1)[0]


def _first_para(md: str) -> str:
    parts = md.split("\n\n")
    # parts[0] is H1 line; parts[1] is first intro paragraph
    return parts[1].strip() if len(parts) > 1 else ""


# --- A: Opt layer produces full proposal payload ---


def test_a_opt_layer_produces_proposal_payload():
    enriched, proposal, warnings = _enrich_ops()
    assert proposal is not None
    assert proposal.action == "rewrite"
    assert proposal.target == "introduction"
    assert proposal.original
    assert proposal.proposed
    assert proposal.evidence
    assert proposal.related_gap_ids == ["gap_thin_1"]
    assert proposal.reason
    assert proposal.proposed.strip() != proposal.original.strip()
    assert "An AI agent is an LLM-based system" in proposal.proposed
    # Payload attached onto the rewrite edit op.
    rewrite_ops = [
        op
        for op in enriched
        if isinstance(op, dict) and op.get("action") == "rewrite"
    ]
    assert rewrite_ops
    op = rewrite_ops[0]
    assert op.get("original")
    assert op.get("proposed")
    assert op.get("evidence")
    assert op.get("related_gap_ids") == ["gap_thin_1"]
    assert op.get("reason") or op.get("instruction")
    assert "intro_rewrite_no_grounded_proposal" not in warnings


# --- B: Generator consumes supplied proposal; does not generate its own ---


def test_b_generator_consumes_supplied_proposal_does_not_generate():
    # Architectural boundary: generator must not import proposal generators.
    src = inspect.getsource(md_gen)
    assert "enrich_ops_with_rewrite_proposals," not in src
    assert "propose_introduction_rewrite," not in src
    assert "from aeo_mvp.content.rewrite_proposal import validate_proposed_rewrite" in src
    # No call sites that generate rewrite copy.
    assert "enrich_ops_with_rewrite_proposals(" not in src
    assert "propose_introduction_rewrite(" not in src

    enriched, proposal, _ = _enrich_ops()
    assert proposal is not None
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": enriched, "proposed_meta_description": BRIEF["proposed_meta_description"]},
        edit_ops=enriched,
        change_plan=enriched,
    )
    assert result.changed is True
    assert proposal.proposed.strip() in result.body
    assert "evidence_grounded_rewrite:introduction" in result.applied_ops
    assert "constrained_rewrite:answer_first_reorder" not in result.applied_ops


# --- C: original present + proposed absent → skip, no reorder ---


def test_c_generator_skips_when_proposed_absent_preserves_md():
    ops_no_proposed = [
        {
            "op_id": "op_1_rewrite_section",
            "action": "rewrite",
            "target_locator": f"section:{ARTICLE_H1}",
            "instruction": "Answer-first introduction grounded in page topic.",
            "original": "Building an AI agent sounds deceptively simple.",
            "related_gap_ids": ["gap_thin_1"],
            # proposed intentionally absent
        }
    ]
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": ops_no_proposed},
        edit_ops=ops_no_proposed,
        change_plan=ops_no_proposed,
    )
    assert result.body.strip() == AGENTS_SOURCE_MD.strip()
    assert result.changed is False
    assert "intro_rewrite_skipped_no_proposed" in result.warnings
    assert "constrained_rewrite:answer_first_reorder" not in result.applied_ops
    assert "evidence_grounded_rewrite:introduction" not in result.applied_ops
    # Unrelated MD preserved.
    assert "## What exactly are we building?" in result.body
    assert "```python" in result.body
    assert "https://github.com/nik-hil/agents-zero-2-hero" in result.body


# --- D: Invalid proposals still rejected ---


def test_d_invalid_proposals_rejected():
    invented = {
        "op_id": "op_bad",
        "action": "rewrite",
        "target_locator": "introduction",
        "instruction": "Bad rewrite",
        "original": "Building an AI agent sounds deceptively simple.",
        "proposed": (
            "According to a 2024 study, 99% of agents use https://evil.example/x."
        ),
        "evidence": ["Building an AI agent sounds deceptively simple."],
        "related_gap_ids": ["gap_1"],
    }
    result = generate_recommended_markdown(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        brief={"edit_ops": [invented]},
        edit_ops=[invented],
    )
    assert result.body.strip() == AGENTS_SOURCE_MD.strip()
    assert result.changed is False
    assert "intro_rewrite_rejected_validation" in result.warnings
    assert any(
        w in result.warnings
        or w.startswith("proposed_ungrounded_tokens:")
        or w
        in {
            "proposed_invented_fact",
            "proposed_invented_url",
        }
        for w in result.warnings
    )


# --- E: Genericity — no production special-case on Agents article text ---


def test_e_no_production_agents_article_hardcoding():
    prod_files = [
        inspect.getsource(
            __import__(
                "aeo_mvp.content.rewrite_proposal", fromlist=["*"]
            )
        ),
        inspect.getsource(md_gen),
    ]
    banned = [
        "call an llm. give it a prompt. get an answer.",
        "but that is not really an agent.",
        "Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling",
        "agents-zero-to-hero-1-building-an-ai-agent",
    ]
    for src in prod_files:
        lower = src.lower()
        for phrase in banned:
            assert phrase.lower() not in lower, f"found hardcoded {phrase!r}"

    # Same rewrite quality on a different article (no Agents strings).
    other_md = """# Widget Orchestration Guide

Widget orchestration sounds deceptively simple.

An LLM becomes an orchestrator when it can decide to take actions, invoke capabilities outside the model, observe the result, and continue working until the task is complete.

## Details

More on widgets.
"""
    ops = [
        {
            "action": "rewrite",
            "target_locator": "introduction",
            "instruction": "Answer-first introduction grounded in page topic.",
            "related_gap_ids": ["gap_x"],
        }
    ]
    enriched, proposal, _ = enrich_ops_with_rewrite_proposals(
        ops,
        source_markdown=other_md,
        page_intelligence={
            "title": "Widget Orchestration Guide",
            "h1": "Widget Orchestration Guide",
            "answerability_signals": {"answer_first_heuristic": False},
            "limits": ["no_answer_first"],
        },
    )
    assert proposal is not None
    assert "orchestrator" in proposal.proposed.lower()
    assert "LLM-based system" in proposal.proposed
    result = generate_recommended_markdown(
        source_markdown=other_md,
        page_intelligence={
            "title": "Widget Orchestration Guide",
            "h1": "Widget Orchestration Guide",
            "answerability_signals": {"answer_first_heuristic": False},
            "limits": ["no_answer_first"],
        },
        edit_ops=enriched,
    )
    assert result.changed is True
    assert "evidence_grounded_rewrite:introduction" in result.applied_ops
    assert _first_para(result.body) != (
        "An LLM becomes an orchestrator when it can decide to take actions, "
        "invoke capabilities outside the model, observe the result, and "
        "continue working until the task is complete."
    )


# --- F: Idempotence ---


def test_f_idempotent_on_already_optimized():
    first = _run()
    assert first.changed is True
    # Second pass: re-enrich against already-optimized body → no new proposal.
    enriched2, proposal2, _ = enrich_ops_with_rewrite_proposals(
        list(EDIT_OPS_INTRO),
        source_markdown=first.body,
        page_intelligence=_pi(
            answerability_signals={"answer_first_heuristic": True},
            limits=[],
        ),
    )
    assert proposal2 is None
    second = generate_recommended_markdown(
        source_markdown=first.body,
        page_intelligence=_pi(
            answerability_signals={"answer_first_heuristic": True},
            limits=[],
        ),
        brief={"edit_ops": enriched2},
        change_plan=enriched2,
        edit_ops=enriched2,
    )
    assert second.body.strip() == first.body.strip()
    assert second.changed is False


# --- G: HTML Hashnode path still resolves to MD optimization (contract) ---


def test_g_html_hashnode_path_resolves_to_md_optimization():
    """Alternate + attach path: HTML Hashnode URL context + source MD → rewrite."""
    from aeo_mvp.content.service import _attach_hashnode_recommended_markdown
    from aeo_mvp.crawler.alternate import get_supported_alternate_url

    html_url = (
        "https://nik-hil.hashnode.dev/"
        "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling"
    )
    alt = get_supported_alternate_url(html_url)
    assert alt is not None
    assert alt.url.endswith(".md")
    assert alt.representation == "markdown"

    wire = {
        "page_intelligence": _pi(url=html_url),
        "content_gaps": [
            {
                "gaps": [
                    {
                        "gap_id": "gap_thin_1",
                        "gap_type": "thin_coverage",
                        "kind": "no_answer_first",
                    }
                ]
            }
        ],
        "optimization_briefs": [
            {
                "edit_ops": EDIT_OPS_INTRO,
                "work_queue": CHANGE_PLAN_INTRO,
                "proposed_meta_description": BRIEF["proposed_meta_description"],
            }
        ],
        "content_drafts": [{"change_plan": CHANGE_PLAN_INTRO}],
    }
    out = _attach_hashnode_recommended_markdown(
        wire,
        page_url=html_url,
        title=ARTICLE_H1,
        source_markdown=AGENTS_SOURCE_MD,
        content_representation="markdown",
        source_url=alt.url,
        canonical_url=html_url,
    )
    draft = (out.get("content_drafts") or [None])[0]
    assert draft is not None
    assert draft.get("changed") is True
    body = draft.get("body_markdown") or ""
    assert body.strip() != AGENTS_SOURCE_MD.strip()
    first = _first_para(body)
    assert first != AGENTS_DEF_SOURCE
    assert "Building an AI agent sounds deceptively simple" not in first
    assert "AI agent" in first or "agent is" in first.lower()
    assert "evidence_grounded_rewrite:introduction" in (draft.get("applied_ops") or [])
    # Opt layer wrote proposal onto brief edit ops.
    brief = out.get("brief") or (out.get("optimization_briefs") or [{}])[0]
    rewrite_ops = [
        e
        for e in (brief.get("edit_ops") or [])
        if isinstance(e, dict) and e.get("action") == "rewrite" and e.get("proposed")
    ]
    assert rewrite_ops
    assert rewrite_ops[0].get("original")
    assert rewrite_ops[0].get("evidence")


# --- Semantic rewrite quality (retained) ---


def test_semantic_intro_rewrite_not_paragraph_move():
    result = _run()
    assert result.ok
    assert result.changed is True
    assert result.body.strip() != AGENTS_SOURCE_MD.strip()

    first = _first_para(result.body)
    assert first != AGENTS_DEF_SOURCE
    assert first.strip() != "Building an AI agent sounds deceptively simple."
    assert "AI agent" in first or "agent is" in first.lower()
    assert "LLM" in first
    assert "capabilities outside the model" in first
    assert "evidence_grounded_rewrite:introduction" in result.applied_ops
    assert "constrained_rewrite:answer_first_reorder" not in result.applied_ops
    assert "intro_rewrite_applied_from_proposed" in result.warnings
    src_paras = [
        p.strip()
        for p in _intro_text(AGENTS_SOURCE_MD).split("\n\n")
        if p.strip() and not p.strip().startswith("#")
    ]
    assert first not in src_paras


def test_proposed_replacement_actually_applied():
    result = _run()
    assert result.rewrite_provenance is not None
    proposed = result.rewrite_provenance["proposed"]
    assert proposed
    assert proposed.strip() in result.body
    assert result.body.startswith(f"# {ARTICLE_H1}\n")
    intro = _intro_text(result.body)
    assert proposed.strip() in intro
    assert "op_1_rewrite_section" in result.applied_ops


def test_rewrite_uses_only_supported_evidence():
    result = _run()
    prov = result.rewrite_provenance
    assert prov is not None
    evidence = prov["evidence"]
    assert evidence
    assert any("LLM becomes an agent" in e for e in evidence)
    for e in evidence:
        assert e in AGENTS_SOURCE_MD
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


def test_no_invented_facts():
    result = _run()
    assert "99%" not in result.body
    assert "according to" not in result.body.lower()
    assert "research shows" not in result.body.lower()
    assert "2024 study" not in result.body.lower()
    assert "content gaps" not in result.body
    assert "under-covered probes" not in result.body


def test_no_invented_urls_or_citations():
    result = _run()
    assert "https://example.com/made-up" not in result.body
    assert "https://github.com/nik-hil/agents-zero-2-hero" in result.body
    src_urls = set(re.findall(r"https?://[^\s)>\]]+", AGENTS_SOURCE_MD))
    out_urls = set(re.findall(r"https?://[^\s)>\]]+", result.body))
    assert out_urls <= src_urls


def test_h1_preserved():
    result = _run()
    assert result.body.splitlines()[0] == f"# {ARTICLE_H1}"
    assert result.body.count(f"# {ARTICLE_H1}") == 1
    assert not result.body.lstrip().startswith("# #")


def test_headings_preserved():
    result = _run()
    assert "## What exactly are we building?" in result.body
    assert "## The agent loop" in result.body
    assert "## Our first two tools" in result.body
    assert "invariant_headings_altered" not in result.warnings


def test_code_blocks_preserved_exactly():
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


def test_links_images_lists_tables_preserved():
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
    enriched, _, _ = enrich_ops_with_rewrite_proposals(
        list(CHANGE_PLAN_INTRO),
        source_markdown=md,
        page_intelligence=_pi(),
    )
    result = generate_recommended_markdown(
        source_markdown=md,
        page_intelligence=_pi(),
        brief=BRIEF,
        change_plan=enriched,
        edit_ops=enriched,
    )
    assert "![cover](https://cdn.hashnode.com/cover.png)" in result.body
    assert "[repo](https://github.com/nik-hil/agents-zero-2-hero)" in result.body
    assert "- first item" in result.body
    assert "- second item" in result.body
    assert "> quoted guidance" in result.body
    assert "| Tool | Purpose |" in result.body
    assert "| execute_code | run python |" in result.body


def test_unsupported_rewrite_target_skipped_with_warning():
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


def test_metadata_only_does_not_alter_body():
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


def test_provenance_and_evidence_retained():
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


def test_agents_fixture_optimized_answer_first_not_mere_change_flag():
    """Regression: recommended intro must be a genuine answer-first rewrite."""
    result = _run()
    assert result.changed is True

    first = _first_para(result.body)
    assert "Building an AI agent sounds deceptively simple" not in first
    assert first != AGENTS_DEF_SOURCE
    assert "agent" in first.lower()
    assert "llm" in first.lower()
    assert "capabilities outside the model" in first.lower()
    assert (
        "decide when to take actions" in first.lower()
        or "decide to take actions" in first.lower()
    )
    proposal = propose_introduction_rewrite(
        source_markdown=AGENTS_SOURCE_MD,
        page_intelligence=_pi(),
        related_gap_ids=["gap_thin_1"],
    )
    assert proposal is not None
    assert proposal.proposed.strip() in result.body
    assert proposal.proposed.strip() != AGENTS_DEF_SOURCE
    assert "An AI agent is an LLM-based system" in proposal.proposed


def test_integration_change_plan_nonempty_must_change_body_when_intro_op():
    result = _run()
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
    # Opt layer finds no grounded proposal.
    enriched, proposal, _ = enrich_ops_with_rewrite_proposals(
        list(EDIT_OPS_INTRO),
        source_markdown=source,
        page_intelligence=_pi(),
    )
    assert proposal is None
    result = generate_recommended_markdown(
        source_markdown=source,
        page_intelligence=_pi(),
        brief={"edit_ops": enriched},
        change_plan=enriched,
        edit_ops=enriched,
    )
    assert result.body.strip() == source.strip()
    assert result.changed is False
    assert "constrained_rewrite:answer_first_reorder" not in result.applied_ops
