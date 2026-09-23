"""Recommendation + validation tests (mocked LLM)."""

import pytest

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.llm import LLMError, reset_execution_flags
from aeo_mvp.queries import Query, QuerySet
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
    with pytest.raises(LLMError, match="concentrated|introduction"):
        validate_recommended_markdown(
            ARTICLE,
            _good_recommended(),
            article=article,
            opportunities=opps,
        )


def test_validate_requires_non_intro_bodies_changed_when_claimed():
    article = load_hashnode_markdown(text=ARTICLE)
    quote_loop = (
        "The agent loop lets a model call tools, see results, and decide whether to continue."
    )
    quote_tools = "Tool calling works by giving the model a schema of available functions."
    opps = [
        Opportunity(
            question="What is an agent loop in tool-calling systems?",
            gap="Needs clearer extractable definition.",
            target_heading="What is an agent loop?",
            recommended_change="Clarify lead.",
            evidence_quote=quote_loop,
        ),
        Opportunity(
            question="How do tool schemas drive function calls?",
            gap="Host observation step is understated.",
            target_heading="How tool calling works",
            recommended_change="Mention host returns observation.",
            evidence_quote=quote_tools,
        ),
    ]
    # RECOMMENDED only edits the loop section — tools body unchanged → hard fail
    with pytest.raises(LLMError, match="unchanged|Full-document"):
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
    assert "**Direct answer:**" not in bundle.recommended_markdown
    assert bundle.opportunities[0].gap
    assert bundle.opportunities[0].target_heading == "What is an agent loop?"
    assert bundle.source == "llm_generated"


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
        "recommended_markdown": _good_recommended(),
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
