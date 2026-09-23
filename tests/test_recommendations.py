"""Recommendation + validation tests (mocked LLM)."""

import pytest

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.llm import LLMError, reset_execution_flags
from aeo_mvp.queries import Query, QuerySet
from aeo_mvp.markdown import parse_sections
from aeo_mvp.recommendations import (
    Opportunity,
    evidence_quote_in_article,
    generate_recommendations,
    validate_recommended_markdown,
)
from aeo_mvp.visibility import VisibilityReport


ARTICLE = """# Agents Zero to Hero

Intro about agents and tool calling.

## What is an agent loop?

The agent loop lets a model call tools, see results, and decide whether to continue.

## How tool calling works

Tool calling works by giving the model a schema of available functions.

## Choosing tools for a harness

A minimal harness needs read, write, and shell tools.
"""


class ScriptedLLM:
    def __init__(self, payload: dict):
        self.payload = payload
        self.model = "mock-model"
        self.calls = 0
        self.prompts: list[str] = []

    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096):
        import aeo_mvp.llm as llm_mod

        self.prompts.append(prompt)
        self.calls += 1
        llm_mod._LLM_CALLS += 1
        return self.payload


def _good_recommended(*, edit_loop: bool = True, edit_tools: bool = False) -> str:
    loop = (
        "The agent loop lets a model call tools, see results, and decide whether to continue.\n"
        "In short, it is the control flow that keeps calling tools until the task is done."
        if edit_loop
        else "The agent loop lets a model call tools, see results, and decide whether to continue."
    )
    tools = (
        "Tool calling works by giving the model a schema of available functions.\n"
        "The host executes the named function and returns the observation to the model."
        if edit_tools
        else "Tool calling works by giving the model a schema of available functions."
    )
    return f"""# Agents Zero to Hero

Intro about agents and tool calling.

## What is an agent loop?

{loop}

## How tool calling works

{tools}

## Choosing tools for a harness

A minimal harness needs read, write, and shell tools.
"""


def test_evidence_quote_must_appear_in_article():
    article = load_hashnode_markdown(text=ARTICLE)
    real = "The agent loop lets a model call tools, see results, and decide whether to continue."
    assert evidence_quote_in_article(real, article.plain_text())
    assert evidence_quote_in_article(
        "The agent loop lets a model call tools,\nsee results, and decide whether to continue.",
        article.plain_text(),
    )
    assert not evidence_quote_in_article(
        "According to a 2024 study, agents boost SEO by 40%.",
        article.plain_text(),
    )


def test_validate_rejects_title_change_and_deleted_sections():
    article = load_hashnode_markdown(text=ARTICLE)
    with pytest.raises(LLMError, match="Title"):
        validate_recommended_markdown(
            ARTICLE,
            "# Other Title\n\n## What is an agent loop?\n\nBody\n",
            article=article,
            opportunities=[],
        )
    with pytest.raises(LLMError, match="Major sections"):
        validate_recommended_markdown(
            ARTICLE,
            "# Agents Zero to Hero\n\n## What is an agent loop?\n\nOnly one section left.\n",
            article=article,
            opportunities=[],
        )


def test_validate_rejects_frontmatter_and_trailing_rules():
    article = load_hashnode_markdown(text=ARTICLE)
    with pytest.raises(LLMError, match="frontmatter|---"):
        validate_recommended_markdown(
            ARTICLE,
            "---\ntitle: x\n---\n\n" + _good_recommended(),
            article=article,
            opportunities=[],
        )
    with pytest.raises(LLMError, match="---"):
        validate_recommended_markdown(
            ARTICLE,
            _good_recommended().rstrip() + "\n\n---\n",
            article=article,
            opportunities=[],
        )


def test_validate_rejects_duplicate_direct_answer_blocks():
    article = load_hashnode_markdown(text=ARTICLE)
    bad = """# Agents Zero to Hero

## What is an agent loop?

**Direct answer:** one
**Direct answer:** two

## How tool calling works

Body

## Choosing tools for a harness

Body
"""
    with pytest.raises(LLMError, match="Direct answer"):
        validate_recommended_markdown(ARTICLE, bad, article=article, opportunities=[])


def test_validate_rejects_intro_only_opportunity_concentration():
    article = load_hashnode_markdown(text=ARTICLE)
    opps = [
        Opportunity(
            question=f"Q{i} about agents broadly?",
            gap="unclear",
            target_heading="Agents Zero to Hero",
            recommended_change="expand intro",
            evidence_quote="Intro about agents and tool calling.",
        )
        for i in range(3)
    ]
    # Edit only the intro/H1 body so applied-change contract passes; concentration still fails.
    intro_edited = ARTICLE.replace(
        "Intro about agents and tool calling.",
        "Intro about agents and tool calling. Expanded for answer engines.",
        1,
    )
    with pytest.raises(LLMError, match="concentrated|introduction"):
        validate_recommended_markdown(
            ARTICLE,
            intro_edited,
            article=article,
            opportunities=opps,
        )


def _loop_opp() -> Opportunity:
    return Opportunity(
        question="What is an agent loop in tool-calling systems?",
        gap="Needs clearer extractable definition.",
        target_heading="What is an agent loop?",
        recommended_change="Clarify lead.",
        evidence_quote=(
            "The agent loop lets a model call tools, see results, and decide whether to continue."
        ),
    )


def _tools_opp() -> Opportunity:
    return Opportunity(
        question="How do tool schemas drive function calls?",
        gap="Host observation step is understated.",
        target_heading="How tool calling works",
        recommended_change="Mention host returns observation.",
        evidence_quote="Tool calling works by giving the model a schema of available functions.",
    )


def test_opportunity_accepted_when_target_section_modified():
    article = load_hashnode_markdown(text=ARTICLE)
    warnings = validate_recommended_markdown(
        ARTICLE,
        _good_recommended(edit_loop=True, edit_tools=False),
        article=article,
        opportunities=[_loop_opp()],
    )
    assert isinstance(warnings, list)


def test_opportunity_rejected_when_target_section_unchanged():
    article = load_hashnode_markdown(text=ARTICLE)
    with pytest.raises(LLMError, match="unchanged|applied"):
        validate_recommended_markdown(
            ARTICLE,
            ARTICLE,  # no edits
            article=article,
            opportunities=[_loop_opp()],
        )


def test_multiple_opportunities_different_sections_ok():
    article = load_hashnode_markdown(text=ARTICLE)
    warnings = validate_recommended_markdown(
        ARTICLE,
        _good_recommended(edit_loop=True, edit_tools=True),
        article=article,
        opportunities=[_loop_opp(), _tools_opp()],
    )
    assert isinstance(warnings, list)


def test_no_substantive_ops_do_not_invent_opportunity_records():
    """Empty opportunities + unchanged (or whitespace-only) RECOMMENDED is valid."""
    article = load_hashnode_markdown(text=ARTICLE)
    warnings = validate_recommended_markdown(
        ARTICLE, ARTICLE, article=article, opportunities=[]
    )
    assert warnings == []
    # Whitespace-only normalization is not substantive → still no invented ops needed
    ws_only = ARTICLE.replace("\n\n", "\n\n\n")
    warnings2 = validate_recommended_markdown(
        ARTICLE, ws_only, article=article, opportunities=[]
    )
    assert isinstance(warnings2, list)


def test_substantive_edit_without_matching_opportunity_rejected():
    article = load_hashnode_markdown(text=ARTICLE)
    with pytest.raises(LLMError, match="without matching opportunities"):
        validate_recommended_markdown(
            ARTICLE,
            _good_recommended(edit_loop=True, edit_tools=False),
            article=article,
            opportunities=[],
        )


def test_validate_requires_all_claimed_targets_changed():
    article = load_hashnode_markdown(text=ARTICLE)
    opps = [_loop_opp(), _tools_opp()]
    # RECOMMENDED only edits the loop section — tools body unchanged → hard fail
    with pytest.raises(LLMError, match="unchanged|applied"):
        validate_recommended_markdown(
            ARTICLE,
            _good_recommended(edit_loop=True, edit_tools=False),
            article=article,
            opportunities=opps,
        )
    # Both sections edited → ok
    warnings = validate_recommended_markdown(
        ARTICLE,
        _good_recommended(edit_loop=True, edit_tools=True),
        article=article,
        opportunities=opps,
    )
    assert isinstance(warnings, list)


def test_generate_recommendations_prompt_is_full_document_and_schema():
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(
        selected=[Query(text="What is an agent loop in tool-calling systems?")]
    )
    payload = {
        "opportunities": [
            {
                "question": "What is an agent loop in tool-calling systems?",
                "gap": "Needs a clearer lead definition for answer engines.",
                "evidence_quote": (
                    "The agent loop lets a model call tools, see results, "
                    "and decide whether to continue."
                ),
                "target_heading": "What is an agent loop?",
                "recommended_change": "Add one clarifying sentence after the lead.",
                "answerability": "weak",
            }
        ],
        "recommended_markdown": _good_recommended(),
        "change_explanations": ["Clarified agent loop lead sentence."],
    }
    client = ScriptedLLM(payload)
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=client
    )
    assert client.calls == 1
    prompt = client.prompts[0]
    assert "FULL-DOCUMENT" in prompt or "entire article" in prompt.lower() or "FULL document" in prompt
    assert "QUESTION → SECTION" in prompt or "QUESTION -> SECTION" in prompt or "question" in prompt.lower()
    assert "introduction is NOT the default" in prompt.lower() or "NOT the default place" in prompt
    assert "APPLIED-CHANGE CONTRACT" in prompt
    assert "**Direct answer:**" not in bundle.recommended_markdown
    assert bundle.opportunities[0].gap
    assert bundle.opportunities[0].target_heading == "What is an agent loop?"
    assert bundle.source == "llm_generated"


def _prompt_from_generate() -> str:
    """Capture the recommendation prompt via a no-op (empty-ops) mocked call."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    payload = {
        "opportunities": [],
        "recommended_markdown": ARTICLE,
        "change_explanations": [],
    }
    client = ScriptedLLM(payload)
    generate_recommendations(article, qs, VisibilityReport(), client=client)
    return client.prompts[0]


def test_recommend_prompt_embeds_eight_pass_material_procedure():
    """Prompt contract: explicit 8-pass procedure + material improvement gate."""
    prompt = _prompt_from_generate()
    for marker in (
        "PASS 1",
        "PASS 2",
        "PASS 3",
        "PASS 4",
        "PASS 5",
        "PASS 6",
        "PASS 7",
        "PASS 8",
        "MATERIAL IMPROVEMENT TEST",
        "STRONG / WEAK / MISSING",
        "SMALLEST USEFUL EDIT",
        "APPLIED-CHANGE CONTRACT",
    ):
        assert marker in prompt, f"missing prompt marker: {marker}"
    # Restatement ≠ opportunity; material relationship = opportunity
    assert "restatement" in prompt.lower() or "RESTATEMENT" in prompt
    assert "tool_call_id" in prompt
    assert "NOT EVERY QUESTION NEEDS A CHANGE" in prompt
    # Heading inventory is navigation only (semantics stay with LLM)
    assert "navigation" in prompt.lower()


def test_strong_already_sufficient_allows_empty_opportunities():
    """Strong/already-sufficient → no opportunity required (empty ops + CURRENT ok)."""
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(
        selected=[
            Query(text="What is an agent loop in tool-calling systems?"),
            Query(text="How do tool schemas drive function calls?"),
        ]
    )
    # LLM judged both STRONG: no ops, RECOMMENDED == CURRENT
    payload = {
        "opportunities": [],
        "recommended_markdown": ARTICLE,
        "change_explanations": [],
    }
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=ScriptedLLM(payload)
    )
    assert bundle.opportunities == []
    assert bundle.recommended_markdown.strip() == ARTICLE.strip()


def test_prompt_rejects_mere_restatement_as_meaningful_change():
    """Mere restatement ≠ meaningful recommendation (documented in prompt contract)."""
    prompt = _prompt_from_generate()
    assert "restatement ≠ opportunity" in prompt.lower() or "restatement" in prompt.lower()
    assert "if removing the new sentence would NOT materially reduce answerability" in prompt
    assert "paraphrasing" in prompt.lower() or "rewording without new info" in prompt.lower()


def test_implicit_gap_targets_existing_local_section():
    """Real implicit gap → targeted local improvement in the owning section."""
    article = load_hashnode_markdown(text=ARTICLE)
    # Host observation step is understated under "How tool calling works"
    recommended = _good_recommended(edit_loop=False, edit_tools=True)
    warnings = validate_recommended_markdown(
        ARTICLE,
        recommended,
        article=article,
        opportunities=[_tools_opp()],
    )
    assert isinstance(warnings, list)
    # Edit must land in the tools section, not intro-only
    assert "returns the observation" in recommended
    assert recommended.startswith("# Agents Zero to Hero\n\nIntro about agents")


def test_missing_grounded_element_allows_local_addition():
    """Genuinely missing grounded element → local addition under correct heading."""
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    payload = {
        "opportunities": [
            {
                "question": "What is an agent loop in tool-calling systems?",
                "gap": (
                    "Article never states that the loop continues until the model "
                    "stops requesting tools — answer engines miss the termination cue."
                ),
                "evidence_quote": (
                    "The agent loop lets a model call tools, see results, "
                    "and decide whether to continue."
                ),
                "target_heading": "What is an agent loop?",
                "recommended_change": (
                    "Add one sentence: the loop keeps calling tools until the task is done."
                ),
                "answerability": "missing",
            }
        ],
        "recommended_markdown": _good_recommended(edit_loop=True, edit_tools=False),
        "change_explanations": ["Added loop termination cue under agent loop section."],
    }
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=ScriptedLLM(payload)
    )
    assert len(bundle.opportunities) == 1
    assert bundle.opportunities[0].answerability == "missing"
    assert bundle.opportunities[0].target_heading == "What is an agent loop?"
    assert "keeps calling tools until the task is done" in bundle.recommended_markdown


def test_meaningful_ops_can_modify_multiple_sections():
    """Meaningful opportunities may still edit multiple non-intro sections."""
    article = load_hashnode_markdown(text=ARTICLE)
    recommended = _good_recommended(edit_loop=True, edit_tools=True)
    warnings = validate_recommended_markdown(
        ARTICLE,
        recommended,
        article=article,
        opportunities=[_loop_opp(), _tools_opp()],
    )
    assert isinstance(warnings, list)
    loop_body = next(
        s.body for s in article.sections if s.heading == "What is an agent loop?"
    )
    new_secs = {s.heading: s.body for s in parse_sections(recommended)}
    assert new_secs["What is an agent loop?"] != loop_body
    assert "returns the observation" in new_secs["How tool calling works"]


def test_ungrounded_or_invalid_opportunities_dropped():
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop really?")])
    payload = {
        "opportunities": [
            {
                "question": "What is an agent loop really?",
                "gap": "gap",
                "evidence_quote": "Invented statistic says 40% improvement.",
                "target_heading": "What is an agent loop?",
                "recommended_change": "clarify",
                "answerability": "strong",
            },
            {
                "question": "Bad heading case",
                "gap": "gap",
                "evidence_quote": (
                    "The agent loop lets a model call tools, see results, "
                    "and decide whether to continue."
                ),
                "target_heading": "This Heading Does Not Exist",
                "recommended_change": "add",
            },
        ],
        # No valid opportunities survive parsing → RECOMMENDED must stay non-substantive.
        "recommended_markdown": ARTICLE,
        "change_explanations": [],
    }
    bundle = generate_recommendations(article, qs, None, client=ScriptedLLM(payload))
    assert bundle.opportunities == []


def test_section_order_preserved():
    article = load_hashnode_markdown(text=ARTICLE)
    reordered = """# Agents Zero to Hero

Intro about agents and tool calling.

## Choosing tools for a harness

A minimal harness needs read, write, and shell tools.

## What is an agent loop?

The agent loop lets a model call tools, see results, and decide whether to continue.

## How tool calling works

Tool calling works by giving the model a schema of available functions.
"""
    with pytest.raises(LLMError, match="order"):
        validate_recommended_markdown(
            ARTICLE, reordered, article=article, opportunities=[]
        )
