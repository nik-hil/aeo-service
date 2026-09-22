"""Grounded LLM synthesis: rewrite_section + claim validation (mock LLM)."""

from __future__ import annotations

import json

from aeo_mvp.content.grounded_synth import (
    GroundedClaim,
    OpenAICompatibleChat,
    find_ws_canonical_corpus_span,
    grounded_synth_enabled,
    novelty_violations,
    quote_is_verbatim,
    repair_claim_evidence_quotes,
    synthesize_rewrite_section,
    validate_claims_against_corpus,
)
from aeo_mvp.content.models import DEFERRED_OP_KINDS, IMPLEMENTED_OP_KINDS
from aeo_mvp.content.substantive_ops import build_substantive_change_plan
from aeo_mvp.platform.hashnode.markdown_generator import generate_recommended_markdown

ARTICLE_H1 = "Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling"

SECTION_MD = f"""# {ARTICLE_H1}

Building an AI agent sounds deceptively simple.

An LLM becomes an agent when it can decide to take actions, invoke capabilities outside the model, observe the result, and continue working until the task is complete.

## The agent loop

The most important concept in the entire project is the agent loop.

The model decides what should happen. The harness controls how it happens.

Tool results are appended to the message history so the model can continue.

## Code

```python
while True:
    response = client.chat.completions.create(messages=messages, tools=TOOL_SCHEMAS)
```
"""

GAPS_SECTION = [
    {
        "gap_id": "gap_agent_loop",
        "id": "gap_agent_loop",
        "gap_type": "thin_coverage",
        "kind": "thin_section",
        "query_id": "q_agent_loop",
        "query_ids": ["q_agent_loop"],
        "page_coverage": "thin",
        "rationale": "Agent loop section is thin for probe",
        "explanation": "Agent loop section is thin for probe",
    },
]

COVERAGE_SECTION = [
    {
        "query_id": "q_agent_loop",
        "query_text": "what is the agent loop",
        "page_coverage": "thin",
    },
]

SECTION_BODY = (
    "The most important concept in the entire project is the agent loop.\n\n"
    "The model decides what should happen. The harness controls how it happens.\n\n"
    "Tool results are appended to the message history so the model can continue."
)

NEW_PROPOSED = (
    "The agent loop is the core control flow: the model decides what should "
    "happen, the harness controls how it happens, and tool results are appended "
    "to the message history so the model can continue."
)

EVIDENCE_QUOTE = (
    "The model decides what should happen. The harness controls how it happens."
)


def _mock_chat_grounded(messages, temperature=0.0):
    """Return grounded rewrite JSON, or ENTAILED for judge prompts."""
    user = ""
    for m in messages:
        if m.get("role") == "user":
            user = m.get("content") or ""
    if "Is the claim fully entailed" in user or "ENTAILED or NOT_ENTAILED" in user:
        return "ENTAILED"
    payload = {
        "proposed": NEW_PROPOSED,
        "claims": [
            {
                "claim": (
                    "The model decides what should happen and the harness "
                    "controls how it happens."
                ),
                "evidence_quote": EVIDENCE_QUOTE,
            },
            {
                "claim": (
                    "Tool results are appended to the message history so the "
                    "model can continue."
                ),
                "evidence_quote": (
                    "Tool results are appended to the message history so the "
                    "model can continue."
                ),
            },
        ],
    }
    return json.dumps(payload)


def _mock_chat_ungrounded(messages, temperature=0.0):
    user = ""
    for m in messages:
        if m.get("role") == "user":
            user = m.get("content") or ""
    if "Is the claim fully entailed" in user or "ENTAILED or NOT_ENTAILED" in user:
        return "NOT_ENTAILED"
    payload = {
        "proposed": (
            "According to a 2024 study, agents improve rankings by 47% "
            "per https://evil.example/ranking."
        ),
        "claims": [
            {
                "claim": "Agents improve rankings by 47%.",
                "evidence_quote": "not on the page at all xyzzy",
            }
        ],
    }
    return json.dumps(payload)


def test_fail_closed_without_draft_paid():
    assert grounded_synth_enabled(draft_paid=False, api_key="sk-test") is False
    assert grounded_synth_enabled(draft_paid=True, api_key="") is False
    assert grounded_synth_enabled(draft_paid=True, api_key="sk-test") is True

    result = synthesize_rewrite_section(
        client=None,
        source_markdown=SECTION_MD,
        query_text="what is the agent loop",
        h1=ARTICLE_H1,
    )
    assert result.disposition == "author_input_required"
    assert result.proposed is None
    assert result.llm_used is False


def test_hashnode_list_whitespace_quote_lock():
    """WS-canonical lock accepts Hashnode list spacing; not paraphrase."""
    corpus = (
        "The agent loop uses tools with:\n\n"
        "*   permissions\n"
        "    \n"
        "    and sandboxes.\n\n"
        "Tool results are appended to the message history.\n"
    )
    # LLM-normalized spacing (single spaces) must lock to corpus span.
    llm_quote = "The agent loop uses tools with: * permissions and sandboxes."
    assert quote_is_verbatim(llm_quote, corpus) is True
    span = find_ws_canonical_corpus_span(llm_quote, corpus)
    assert span is not None and span in corpus
    assert "*   permissions" in span

    repaired, warns = repair_claim_evidence_quotes(
        [GroundedClaim(claim="Tools use permissions and sandboxes.", evidence_quote=llm_quote)],
        corpus=corpus,
    )
    assert repaired[0].evidence_quote in corpus
    assert any("ws_repaired" in w for w in warns)

    # Paraphrase / invented span fails.
    assert quote_is_verbatim(
        "The agent loop invents magical new ranking powers now.", corpus
    ) is False
    assert find_ws_canonical_corpus_span(
        "The agent loop invents magical new ranking powers now.", corpus
    ) is None

    # Novelty bans unchanged.
    nov = novelty_violations(
        "See https://evil.example/rank and gain 47% visibility", corpus
    )
    assert any("invented_url" in v for v in nov)
    assert any("invented_number" in v for v in nov)

    errs = validate_claims_against_corpus(
        [
            GroundedClaim(
                claim="Agents gain 47% visibility.",
                evidence_quote="not present on page at all xyz",
            )
        ],
        corpus=corpus,
        proposed="Agents gain 47% visibility via https://evil.example/rank",
    )
    assert any("quote_not_verbatim" in e for e in errs)
    assert any("invented" in e for e in errs)


def test_ws_quote_repair_enables_ready_rewrite_section():
    """Section body with Hashnode list WS + LLM single-space quotes → ready."""
    body = (
        "The most important concept is the agent loop.\n\n"
        "The model decides what should happen. The harness controls how it happens.\n\n"
        "Capabilities include:\n\n"
        "*   tool calling\n"
        "    \n"
        "*   message history\n"
    )
    quote_ws = (
        "Capabilities include: * tool calling * message history"
    )
    corpus_quote_exact = find_ws_canonical_corpus_span(quote_ws, body)
    assert corpus_quote_exact is not None

    def _chat(messages, temperature=0.0):
        user = ""
        for m in messages:
            if m.get("role") == "user":
                user = m.get("content") or ""
        if "ENTAILED or NOT_ENTAILED" in user or "Is the claim fully entailed" in user:
            return "ENTAILED"
        if "Fix evidence_quote" in user:
            # Repair path: return WS-canonical quotes (still need repair to corpus span).
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": "The harness controls how it happens.",
                            "evidence_quote": (
                                "The model decides what should happen. "
                                "The harness controls how it happens."
                            ),
                        },
                        {
                            "claim": "Capabilities include tool calling and message history.",
                            "evidence_quote": quote_ws,
                        },
                    ]
                }
            )
        return json.dumps(
            {
                "proposed": (
                    "The agent loop is the core control flow. The model decides what "
                    "should happen. The harness controls how it happens. Capabilities "
                    "include tool calling and message history."
                ),
                "claims": [
                    {
                        "claim": "The harness controls how it happens.",
                        "evidence_quote": (
                            "The model decides what should happen. "
                            "The harness controls how it happens."
                        ),
                    },
                    {
                        "claim": "Capabilities include tool calling and message history.",
                        "evidence_quote": quote_ws,
                    },
                ],
            }
        )

    client = OpenAICompatibleChat(api_key="mock", chat_fn=_chat)
    result = synthesize_rewrite_section(
        client=client,
        source_markdown=f"# {ARTICLE_H1}\n\nLead.\n\n## The agent loop\n\n{body}\n",
        query_text="what is the agent loop",
        h1=ARTICLE_H1,
        section_heading="The agent loop",
        section_body=body,
    )
    assert result.disposition == "actionable", result.to_dict()
    assert result.status == "ready"
    assert all(c.evidence_quote in body for c in result.claims)


def test_rewrite_section_new_wording_with_claims():
    client = OpenAICompatibleChat(
        api_key="mock",
        chat_fn=_mock_chat_grounded,
    )
    result = synthesize_rewrite_section(
        client=client,
        source_markdown=SECTION_MD,
        query_text="what is the agent loop",
        h1=ARTICLE_H1,
        section_heading="The agent loop",
        section_body=SECTION_BODY,
        related_gap_ids=["gap_agent_loop"],
        related_query_ids=["q_agent_loop"],
    )
    assert result.disposition == "actionable"
    assert result.status == "ready"
    assert result.op_kind == "rewrite_section"
    assert result.proposed is not None
    assert result.proposed.strip() != SECTION_BODY.strip()
    assert "agent loop is the core control flow" in result.proposed
    assert len(result.claims) >= 1
    for cl in result.claims:
        assert cl.evidence_quote in SECTION_BODY
    assert result.original == SECTION_BODY
    assert result.llm_used is True


def test_reject_ungrounded_claims():
    client = OpenAICompatibleChat(api_key="mock", chat_fn=_mock_chat_ungrounded)
    result = synthesize_rewrite_section(
        client=client,
        source_markdown=SECTION_MD,
        query_text="what is the agent loop",
        h1=ARTICLE_H1,
        section_heading="The agent loop",
        section_body=SECTION_BODY,
    )
    assert result.disposition in {"author_input_required", "research_required"}
    assert result.proposed is None
    assert result.status == "needs_author_input"

    errs = validate_claims_against_corpus(
        [
            GroundedClaim(
                claim="Agents improve rankings by 47%.",
                evidence_quote="not on the page",
            )
        ],
        corpus=SECTION_BODY,
        proposed="Agents improve rankings by 47% https://evil.example/x",
    )
    assert errs
    assert any("quote_not_verbatim" in e or "invented" in e for e in errs)


def test_plan_emits_ready_rewrite_section_with_mock_client():
    client = OpenAICompatibleChat(api_key="mock", chat_fn=_mock_chat_grounded)
    plan = build_substantive_change_plan(
        source_markdown=SECTION_MD,
        gaps=GAPS_SECTION,
        coverage_by_query=COVERAGE_SECTION,
        page_intelligence={
            "h1": ARTICLE_H1,
            "title": ARTICLE_H1,
            "answerability_signals": {"answer_first_heuristic": True},
            "limits": [],
        },
        h1=ARTICLE_H1,
        draft_paid=True,
        llm_api_key="mock",
        grounded_client=client,
    )
    ready = [i for i in plan.items if i.status == "ready" and i.op_kind == "rewrite_section"]
    assert ready, f"expected ready rewrite_section, got {[i.to_dict() for i in plan.items]}"
    item = ready[0]
    assert item.proposed_content and item.proposed_content != SECTION_BODY
    assert item.claims
    assert item.disposition == "actionable"
    assert item.apply_mode == "replace_region"
    assert item.original


def test_md_generator_applies_rewrite_section_without_llm():
    """Hashnode generator is apply-only — never imports grounded_synth."""
    import aeo_mvp.platform.hashnode.markdown_generator as md_gen

    assert not hasattr(md_gen, "synthesize_rewrite_section")
    proposed = NEW_PROPOSED
    op = {
        "op_id": "op_rs_1",
        "action": "rewrite",
        "op_kind": "rewrite_section",
        "target": "section:The agent loop",
        "target_locator": "section:The agent loop",
        "status": "ready",
        "disposition": "actionable",
        "apply_mode": "replace_region",
        "original": SECTION_BODY,
        "proposed": proposed,
        "evidence": [SECTION_BODY[:200]],
        "claims": [
            {
                "claim": "The model decides what should happen.",
                "evidence_quote": EVIDENCE_QUOTE,
            }
        ],
    }
    result = generate_recommended_markdown(
        source_markdown=SECTION_MD,
        page_intelligence={"h1": ARTICLE_H1},
        edit_ops=[op],
    )
    assert result.changed is True
    assert proposed in result.body
    section_after = result.body.split("## The agent loop", 1)[-1].split("## Code", 1)[0]
    assert "The most important concept in the entire project is the agent loop." not in section_after
    assert "evidence_grounded_rewrite_section" in result.applied_ops
    assert "rewrite_section_applied_from_proposed" in result.warnings


def test_multi_op_intro_and_section():
    client = OpenAICompatibleChat(api_key="mock", chat_fn=_mock_chat_grounded)
    gaps = [
        {
            "gap_id": "gap_answer_first_1",
            "id": "gap_answer_first_1",
            "gap_type": "evidence_gap",
            "kind": "missing_answer",
            "query_id": "q_what_is_agent",
            "query_ids": ["q_what_is_agent"],
            "page_coverage": "thin",
            "rationale": "Introduction is not answer-first",
        },
        *GAPS_SECTION,
    ]
    coverage = [
        {
            "query_id": "q_what_is_agent",
            "query_text": "what is an AI agent",
            "page_coverage": "thin",
        },
        *COVERAGE_SECTION,
    ]
    plan = build_substantive_change_plan(
        source_markdown=SECTION_MD,
        gaps=gaps,
        coverage_by_query=coverage,
        page_intelligence={
            "h1": ARTICLE_H1,
            "title": ARTICLE_H1,
            "answerability_signals": {"answer_first_heuristic": False},
            "limits": ["no_answer_first"],
        },
        h1=ARTICLE_H1,
        draft_paid=True,
        llm_api_key="mock",
        grounded_client=client,
    )
    kinds = {i.op_kind for i in plan.items if i.status == "ready"}
    assert "rewrite_introduction" in kinds
    assert "rewrite_section" in kinds


def test_contract_includes_grounded_ops():
    assert "rewrite_section" in IMPLEMENTED_OP_KINDS
    assert "add_explanation" in IMPLEMENTED_OP_KINDS
    assert "rewrite_section" not in DEFERRED_OP_KINDS
    assert "clarify_relationship" in DEFERRED_OP_KINDS


def test_cite_miss_full_routes_to_grounded_synth():
    """Architect lock: cite_miss+full → rewrite_section/add_explanation when paid."""
    client = OpenAICompatibleChat(api_key="mock", chat_fn=_mock_chat_grounded)
    gaps = [
        {
            "gap_id": "gap_cite_miss_q1",
            "id": "gap_cite_miss_q1",
            "gap_type": "cite_miss",
            "kind": "missing_answer",
            "query_id": "q_agent_loop",
            "query_ids": ["q_agent_loop"],
            "page_coverage": "full",
            "rationale": "Mentioned or probed but not cited in visibility observations",
            "explanation": "Mentioned or probed but not cited in visibility observations",
        },
        {
            "gap_id": "gap_schema",
            "gap_type": "schema_gap",
            "kind": "thin_passage",
            "page_coverage": "full",
            "rationale": "Missing meta description",
        },
        {
            "gap_id": "gap_format",
            "gap_type": "format_gap",
            "kind": "unstructured",
            "rationale": "No JSON-LD",
        },
        {
            "gap_id": "gap_tech",
            "gap_type": "technical_extractability_gap",
            "kind": "unstructured",
            "rationale": "no main landmark",
        },
    ]
    coverage = [
        {
            "query_id": "q_agent_loop",
            "query_text": "what is the agent loop",
            "page_coverage": "full",
        },
    ]
    plan = build_substantive_change_plan(
        source_markdown=SECTION_MD,
        gaps=gaps,
        coverage_by_query=coverage,
        page_intelligence={
            "h1": ARTICLE_H1,
            "title": ARTICLE_H1,
            "answerability_signals": {"answer_first_heuristic": True},
            "limits": [],
        },
        h1=ARTICLE_H1,
        draft_paid=True,
        llm_api_key="mock",
        grounded_client=client,
    )
    ready_section = [
        i
        for i in plan.items
        if i.status == "ready"
        and i.op_kind in {"rewrite_section", "add_explanation"}
    ]
    assert ready_section, f"expected cite_miss→section op, got {[i.to_dict() for i in plan.items]}"
    item = ready_section[0]
    assert item.llm_used is True
    assert item.claims
    assert "citation guarantee" not in item.reason.lower() or "not a citation" in item.reason.lower()
    assert "Cite-readiness" in item.reason or "cite-readiness" in item.reason.lower()
    # Deferred kinds stay author_input — never routed to synth invent.
    deferred_kinds = {
        i.op_kind
        for i in plan.items
        if str(i.related_gap_ids)
        and any(x in str(i.related_gap_ids) for x in ("schema", "format", "tech"))
    }
    for it in plan.items:
        gids = " ".join(it.related_gap_ids or [])
        if "schema" in gids or "format" in gids or "tech" in gids:
            assert it.status == "needs_author_input"
            assert it.proposed_content is None


def test_cite_miss_fail_closed_without_paid():
    gaps = [
        {
            "gap_id": "gap_cite_miss_q1",
            "gap_type": "cite_miss",
            "kind": "missing_answer",
            "query_id": "q_agent_loop",
            "page_coverage": "full",
            "rationale": "not cited",
        }
    ]
    plan = build_substantive_change_plan(
        source_markdown=SECTION_MD,
        gaps=gaps,
        coverage_by_query=COVERAGE_SECTION,
        page_intelligence={"h1": ARTICLE_H1},
        h1=ARTICLE_H1,
        draft_paid=False,
    )
    section = [i for i in plan.items if i.op_kind in {"rewrite_section", "add_explanation"}]
    assert section
    assert all(i.status == "needs_author_input" for i in section)
    assert all(i.proposed_content is None for i in section)
    assert all(i.llm_used is False for i in section)


def test_resolve_draft_generator_skips_stub_by_default():
    from aeo_mvp.content.draft import (
        DeterministicSkeletonDraftGenerator,
        PaidLLMDraftGenerator,
        resolve_draft_generator,
    )

    gen = resolve_draft_generator(
        generate_draft=True, draft_paid=True, content_draft=True, api_key="sk-x"
    )
    assert isinstance(gen, DeterministicSkeletonDraftGenerator)
    stub = resolve_draft_generator(
        generate_draft=True,
        draft_paid=True,
        content_draft=True,
        content_draft_provider="paid_llm_stub",
        api_key="sk-x",
    )
    assert isinstance(stub, PaidLLMDraftGenerator)


def test_intro_related_gaps_do_not_cover_cite_miss():
    """Intro must not consume cite_miss ids via related_gap_ids / covered set."""
    client = OpenAICompatibleChat(api_key="mock", chat_fn=_mock_chat_grounded)
    cite_gid = "gap_cite_miss_q_agent_loop"
    gaps = [
        {
            "gap_id": "gap_answer_first_1",
            "gap_type": "evidence_gap",
            "kind": "missing_answer",
            "query_id": "q_what_is_agent",
            "page_coverage": "thin",
            "rationale": "Introduction is not answer-first",
        },
        {
            "gap_id": cite_gid,
            "gap_type": "cite_miss",
            "kind": "missing_answer",
            "query_id": "q_agent_loop",
            "page_coverage": "full",
            "rationale": "probed but not cited",
        },
    ]
    coverage = [
        {"query_id": "q_what_is_agent", "query_text": "what is an AI agent", "page_coverage": "thin"},
        {"query_id": "q_agent_loop", "query_text": "what is the agent loop", "page_coverage": "full"},
    ]
    # Seed intro op that wrongly lists cite_miss in related_gap_ids (live bug shape).
    existing = [
        {
            "action": "rewrite",
            "target": "introduction",
            "instruction": "Answer-first introduction",
            "related_gap_ids": ["gap_answer_first_1", cite_gid],
        }
    ]
    plan = build_substantive_change_plan(
        source_markdown=SECTION_MD,
        gaps=gaps,
        coverage_by_query=coverage,
        page_intelligence={
            "h1": ARTICLE_H1,
            "answerability_signals": {"answer_first_heuristic": False},
            "limits": ["no_answer_first"],
        },
        existing_ops=existing,
        h1=ARTICLE_H1,
        draft_paid=True,
        llm_api_key="mock",
        grounded_client=client,
    )
    intro = next(i for i in plan.items if i.op_kind == "rewrite_introduction")
    assert cite_gid not in (intro.related_gap_ids or [])
    section = [
        i
        for i in plan.items
        if i.op_kind in {"rewrite_section", "add_explanation"} and i.status == "ready"
    ]
    assert section, f"cite_miss blocked by intro cover: {[i.to_dict() for i in plan.items]}"
    assert any(cite_gid in (i.related_gap_ids or []) for i in section)


def test_llm_used_preserved_on_grounded_edit_ops():
    client = OpenAICompatibleChat(api_key="mock", chat_fn=_mock_chat_grounded)
    plan = build_substantive_change_plan(
        source_markdown=SECTION_MD,
        gaps=[
            {
                "gap_id": "gap_cite_miss_q1",
                "gap_type": "cite_miss",
                "kind": "missing_answer",
                "query_id": "q_agent_loop",
                "page_coverage": "full",
                "rationale": "not cited",
            }
        ],
        coverage_by_query=COVERAGE_SECTION,
        page_intelligence={"h1": ARTICLE_H1},
        h1=ARTICLE_H1,
        draft_paid=True,
        llm_api_key="mock",
        grounded_client=client,
    )
    ready = [
        i for i in plan.items if i.status == "ready" and i.op_kind == "rewrite_section"
    ]
    assert ready
    assert ready[0].llm_used is True
    wire = ready[0].to_edit_op_dict()
    assert wire.get("llm_used") is True
    from aeo_mvp.content.substantive_ops import merge_plan_into_ops

    merged = merge_plan_into_ops([], plan)
    section_ops = [
        o
        for o in merged
        if str(o.get("op_kind") or "") == "rewrite_section" and o.get("status") == "ready"
    ]
    assert section_ops
    assert section_ops[0].get("llm_used") is True
