"""Recommendation + validation tests (mocked LLM)."""

import pytest

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.llm import LLMError, reset_execution_flags
from aeo_mvp.queries import Query, QuerySet
from aeo_mvp.markdown import parse_sections
from aeo_mvp.recommendations import (
    MAX_RECOMMENDATION_ATTEMPTS,
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


def _loop_body_edited() -> str:
    return (
        "The agent loop lets a model call tools, see results, and decide whether to continue.\n"
        "In short, it is the control flow that keeps calling tools until the task is done."
    )


def _tools_body_edited() -> str:
    return (
        "Tool calling works by giving the model a schema of available functions.\n"
        "The host executes the named function and returns the observation to the model."
    )


def _loop_section_edit() -> dict:
    return {
        "target_heading": "What is an agent loop?",
        "replacement_body": _loop_body_edited(),
    }


def _tools_section_edit() -> dict:
    return {
        "target_heading": "How tool calling works",
        "replacement_body": _tools_body_edited(),
    }


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


class SequencingLLM:
    """Mock that returns/raises a scripted sequence of respond_json outcomes."""

    def __init__(self, outcomes: list):
        self.outcomes = list(outcomes)
        self.model = "mock-model"
        self.calls = 0
        self.prompts: list[str] = []

    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096):
        import aeo_mvp.llm as llm_mod

        self.prompts.append(prompt)
        self.calls += 1
        llm_mod._LLM_CALLS += 1
        if not self.outcomes:
            raise LLMError("SequencingLLM exhausted scripted outcomes")
        item = self.outcomes.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


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
        "section_edits": [_loop_section_edit()],
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
        "section_edits": [],
        "change_explanations": [],
    }
    client = ScriptedLLM(payload)
    generate_recommendations(article, qs, VisibilityReport(), client=client)
    return client.prompts[0]


def test_recommend_prompt_embeds_systematic_decision_method():
    """Prompt contract: full decision method for sufficient answerability."""
    prompt = _prompt_from_generate()
    for marker in (
        "STEP 1",
        "STEP 2",
        "STEP 3",
        "STEP 4",
        "STEP 5",
        "STEP 6",
        "STEP 7",
        "STEP 8",
        "STEP 9",
        "SUFFICIENT ANSWERABILITY WITH THE SMALLEST USEFUL CHANGE",
        "INTERNAL ANSWER SUMMARY",
        "NO GAP",
        "CLARITY GAP",
        "INFORMATION GAP",
        "BEFORE / AFTER TEST",
        "COUNTERFACTUAL TEST",
        "STOPPING RULE PER QUESTION",
        "DO NOT BECOME TOO CONSERVATIVE",
        "CALIBRATED EXAMPLES",
        "APPLIED-CHANGE CONTRACT",
        "CONSISTENCY CHECK",
        "CORE RULE",
        "SOURCE PRIORITY",
        "GROUNDING RULE",
        "SECTION EDIT OUTPUT RULE",
        "section_edits",
    ):
        assert marker in prompt, f"missing prompt marker: {marker}"
    assert "tool_call_id" in prompt
    assert "NOT EVERY QUESTION NEEDS A CHANGE" in prompt
    assert "navigation" in prompt.lower()
    assert "If I remove this edit, would an AI's answer become materially less" in prompt


def test_prompt_current_is_content_source_of_truth():
    """1. CURRENT = content source of truth."""
    prompt = _prompt_from_generate()
    assert "content source of truth" in prompt
    assert "EDITOR of the existing article" in prompt or "editor of the existing article" in prompt.lower()
    assert "not a researcher writing new content" in prompt.lower() or (
        "not a researcher" in prompt
    )


def test_prompt_questions_are_optimization_targets():
    """2. Questions = optimization targets."""
    prompt = _prompt_from_generate()
    assert "SELECTED QUESTIONS = optimization targets" in prompt or (
        "optimization targets" in prompt
    )


def test_prompt_visibility_is_diagnostic_only():
    """3. Visibility = diagnostic only (not a content source)."""
    prompt = _prompt_from_generate()
    assert "diagnostic evidence only" in prompt or "Diagnostic only" in prompt
    assert "not a content source" in prompt.lower()
    assert (
        "Search evidence tells you WHAT may be weak. CURRENT.md tells you WHAT you are"
        in prompt
    )


def test_prompt_rejects_search_only_fact():
    """4. Search-only fact (e.g. OpenRouter) → reject."""
    prompt = _prompt_from_generate()
    assert "BAD search-only import" in prompt
    assert "OpenRouter" in prompt
    assert "OPENROUTER_API_KEY" in prompt
    assert "Search finding it does NOT authorize it" in prompt or (
        "Search evidence ≠ content license" in prompt
    )


def test_prompt_accepts_existing_relationship_made_explicit():
    """5. Existing relationship made explicit → accept."""
    prompt = _prompt_from_generate()
    assert "GOOD missing relationship" in prompt
    assert "tool_call_id" in prompt
    assert "associates" in prompt or "association" in prompt


def test_prompt_accepts_existing_facts_connected_causally():
    """6. Existing facts connected causally → accept."""
    prompt = _prompt_from_generate()
    assert "GOOD connecting existing facts" in prompt
    assert "revise and retry" in prompt or "failed result" in prompt


def test_prompt_rejects_general_knowledge_not_in_current():
    """7. General knowledge not in CURRENT → reject."""
    prompt = _prompt_from_generate()
    assert "BAD general-knowledge expansion" in prompt
    assert "file/network" in prompt or "general knowledge" in prompt.lower()


def test_strong_already_sufficient_allows_empty_opportunities():
    """NO GAP → no opportunity / no edit (empty ops + CURRENT ok)."""
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(
        selected=[
            Query(text="What is an agent loop in tool-calling systems?"),
            Query(text="How do tool schemas drive function calls?"),
        ]
    )
    payload = {
        "opportunities": [],
        "section_edits": [],
        "change_explanations": [],
    }
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=ScriptedLLM(payload)
    )
    assert bundle.opportunities == []
    assert bundle.recommended_markdown.strip() == ARTICLE.strip()
    prompt = _prompt_from_generate()
    assert "NO GAP" in prompt
    assert "no opportunity, no edit" in prompt


def test_prompt_clarity_gap_allows_meaningful_clarification():
    """CLARITY GAP → meaningful clarification allowed (prompt + weak opp path)."""
    prompt = _prompt_from_generate()
    assert "CLARITY GAP" in prompt
    assert "local clarification allowed" in prompt
    assert "weak" in prompt


def test_prompt_information_gap_allows_grounded_addition():
    """INFORMATION GAP → CURRENT-grounded addition allowed; search-only → no invent."""
    prompt = _prompt_from_generate()
    assert "INFORMATION GAP" in prompt
    assert "do not invent" in prompt
    assert "missing entirely from CURRENT" in prompt or "not in CURRENT" in prompt
    assert "GROUNDING RULE" in prompt


def test_prompt_rejects_visible_code_narration():
    """Visible-code narration → reject."""
    prompt = _prompt_from_generate()
    assert "BAD visible-code narration" in prompt
    assert "append tool result" in prompt or "appends tool" in prompt
    assert "no meaningful answer value" in prompt


def test_prompt_rejects_paraphrase():
    """Paraphrase → reject."""
    prompt = _prompt_from_generate()
    assert "BAD paraphrase" in prompt
    assert "LLM makes decisions" in prompt or "same meaning" in prompt
    assert "COUNTERFACTUAL TEST" in prompt
    assert "BEFORE / AFTER TEST" in prompt
    assert "sounds better" in prompt or "more SEO" in prompt


def test_prompt_keeps_missing_relationship():
    """Missing relationship → keep."""
    prompt = _prompt_from_generate()
    assert "GOOD missing relationship" in prompt
    assert "tool_call_id" in prompt
    assert "associates" in prompt or "association" in prompt or "specific tool request" in prompt


def test_prompt_keeps_connecting_existing_facts():
    """Connecting existing facts → keep."""
    prompt = _prompt_from_generate()
    assert "GOOD connecting existing facts" in prompt
    assert "revise and retry" in prompt or "failed result" in prompt


def test_prompt_stop_after_sufficiency():
    """Stop after sufficiency."""
    prompt = _prompt_from_generate()
    assert "STOPPING RULE PER QUESTION" in prompt
    assert "sufficiently complete and unambiguous → STOP" in prompt
    assert "internal answer summary" in prompt.lower() or "INTERNAL ANSWER SUMMARY" in prompt
    assert "Do not edit merely because search has more information" in prompt


def test_prompt_rejects_second_redundant_edit():
    """Second redundant edit → reject."""
    prompt = _prompt_from_generate()
    assert "BAD polish after sufficiency" in prompt
    assert "second paragraph restating" in prompt or "second, independent" in prompt
    assert "Do not keep editing because words could still be improved" in prompt


def test_prompt_article_code_contradiction_check():
    """Article/code contradiction + competing-explanation check."""
    prompt = _prompt_from_generate()
    assert "contradictions with code" in prompt
    assert "competing explanations" in prompt or "two competing explanations" in prompt
    assert "finish tool" in prompt


def test_prompt_do_not_become_too_conservative():
    """Partial answers can still need real improvement (CURRENT-authorized)."""
    prompt = _prompt_from_generate()
    assert "DO NOT BECOME TOO CONSERVATIVE" in prompt
    assert "only edit when absolutely no information exists" in prompt
    assert "tool-call message" in prompt or "subsequent tool result" in prompt


def test_implicit_gap_targets_existing_local_section():
    """CLARITY / implicit gap → targeted local improvement in owning section."""
    article = load_hashnode_markdown(text=ARTICLE)
    recommended = _good_recommended(edit_loop=False, edit_tools=True)
    warnings = validate_recommended_markdown(
        ARTICLE,
        recommended,
        article=article,
        opportunities=[_tools_opp()],
    )
    assert isinstance(warnings, list)
    assert "returns the observation" in recommended
    assert recommended.startswith("# Agents Zero to Hero\n\nIntro about agents")


def test_missing_grounded_element_allows_local_addition():
    """INFORMATION GAP → local grounded addition under correct heading."""
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
        "section_edits": [_loop_section_edit()],
        "change_explanations": ["Added loop termination cue under agent loop section."],
    }
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=ScriptedLLM(payload)
    )
    assert len(bundle.opportunities) == 1
    assert bundle.opportunities[0].answerability == "missing"
    assert bundle.opportunities[0].target_heading == "What is an agent loop?"
    assert "keeps calling tools until the task is done" in bundle.recommended_markdown


def test_partial_clarification_opportunity_maps_to_weak():
    """CLARITY GAP → weak opportunity + local section edit."""
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="How do tool schemas drive function calls?")])
    payload = {
        "opportunities": [
            {
                "question": "How do tool schemas drive function calls?",
                "gap": (
                    "Schemas are mentioned but the host observation handoff is "
                    "under-explained — partial answer needs that relationship."
                ),
                "evidence_quote": (
                    "Tool calling works by giving the model a schema of available functions."
                ),
                "target_heading": "How tool calling works",
                "recommended_change": (
                    "Clarify that the host executes the named function and returns "
                    "the observation to the model."
                ),
                "answerability": "weak",
            }
        ],
        "section_edits": [_tools_section_edit()],
        "change_explanations": ["Clarified host observation handoff under tool calling."],
    }
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=ScriptedLLM(payload)
    )
    assert len(bundle.opportunities) == 1
    assert bundle.opportunities[0].answerability == "weak"
    assert bundle.opportunities[0].target_heading == "How tool calling works"


def test_second_redundant_edit_after_sufficiency_not_required():
    """After sufficiency, no redundant second section edit required."""
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(
        selected=[
            Query(text="What is an agent loop in tool-calling systems?"),
            Query(text="How do tool schemas drive function calls?"),
        ]
    )
    payload = {
        "opportunities": [
            {
                "question": "What is an agent loop in tool-calling systems?",
                "gap": "Termination cue under-explained.",
                "evidence_quote": (
                    "The agent loop lets a model call tools, see results, "
                    "and decide whether to continue."
                ),
                "target_heading": "What is an agent loop?",
                "recommended_change": "Add loop-continues-until-done clarification.",
                "answerability": "weak",
            }
        ],
        "section_edits": [_loop_section_edit()],
        "change_explanations": ["One clarification; stopped after sufficiency."],
    }
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=ScriptedLLM(payload)
    )
    assert len(bundle.opportunities) == 1
    tools_before = next(
        s.body for s in article.sections if s.heading == "How tool calling works"
    )
    tools_after = next(
        s.body
        for s in parse_sections(bundle.recommended_markdown)
        if s.heading == "How tool calling works"
    )
    assert tools_before.strip() == tools_after.strip()


def test_meaningful_ops_can_modify_multiple_sections():
    """11. Multiple genuine gaps can still modify multiple sections."""
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
        # No valid opportunities survive parsing → no section_edits.
        "section_edits": [],
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


def _valid_loop_payload() -> dict:
    return {
        "opportunities": [
            {
                "question": "What is an agent loop in tool-calling systems?",
                "gap": "Termination cue under-explained.",
                "evidence_quote": (
                    "The agent loop lets a model call tools, see results, "
                    "and decide whether to continue."
                ),
                "target_heading": "What is an agent loop?",
                "recommended_change": "Add loop-continues-until-done clarification.",
                "answerability": "weak",
            }
        ],
        "section_edits": [_loop_section_edit()],
        "change_explanations": ["Clarified agent loop."],
    }


def _invalid_unchanged_target_payload() -> dict:
    """Opportunity claims a section edit but no section_edit is returned."""
    return {
        "opportunities": [
            {
                "question": "What is an agent loop in tool-calling systems?",
                "gap": "Needs clarification.",
                "evidence_quote": (
                    "The agent loop lets a model call tools, see results, "
                    "and decide whether to continue."
                ),
                "target_heading": "What is an agent loop?",
                "recommended_change": "Clarify lead.",
                "answerability": "weak",
            }
        ],
        "section_edits": [],
        "change_explanations": ["noop"],
    }


def _article_block_from_prompt(prompt: str) -> str:
    start = prompt.find("<<<ARTICLE\n")
    end = prompt.find("\nARTICLE>>>")
    assert start >= 0 and end > start
    return prompt[start + len("<<<ARTICLE\n") : end]


def test_recommend_success_first_attempt_is_single_llm_call():
    """Successful first attempt → exactly one recommendation LLM call."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    client = SequencingLLM([_valid_loop_payload()])
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=client
    )
    assert client.calls == 1
    assert "REPAIR FEEDBACK" not in client.prompts[0]
    assert bundle.opportunities[0].target_heading == "What is an agent loop?"
    assert "SECTION EDIT OUTPUT RULE" in client.prompts[0]


def test_transient_llm_error_retries_original_prompt_without_repair():
    """Transient LLM/API error → retry with original prompt, no repair feedback."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    client = SequencingLLM(
        [
            LLMError("LLM request failed: connection reset"),
            _valid_loop_payload(),
        ]
    )
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=client
    )
    assert client.calls == 2
    assert "REPAIR FEEDBACK" not in client.prompts[0]
    assert "REPAIR FEEDBACK" not in client.prompts[1]
    assert _article_block_from_prompt(client.prompts[0]) == _article_block_from_prompt(
        client.prompts[1]
    )
    assert bundle.opportunities


def test_validator_failure_retry_includes_exact_error():
    """Deterministic validator failure → next prompt contains exact error."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    client = SequencingLLM(
        [
            _invalid_unchanged_target_payload(),
            _valid_loop_payload(),
        ]
    )
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=client
    )
    assert client.calls == 2
    repair = client.prompts[1]
    assert "REPAIR FEEDBACK" in repair
    assert "missing section_edit" in repair or "section_edits" in repair.lower()
    assert "Validator error:" in repair
    assert "Do not regenerate the complete article." in repair
    assert "section_edits" in repair
    assert bundle.opportunities[0].target_heading == "What is an agent loop?"


def test_repair_prompt_still_contains_pr49_recommendation_instructions():
    """Retry prompt still contains original PR #49 recommendation instructions."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    client = SequencingLLM(
        [
            _invalid_unchanged_target_payload(),
            _valid_loop_payload(),
        ]
    )
    generate_recommendations(article, qs, VisibilityReport(), client=client)
    repair = client.prompts[1]
    for marker in (
        "CORE RULE",
        "SOURCE PRIORITY",
        "GROUNDING RULE",
        "COUNTERFACTUAL TEST",
        "APPLIED-CHANGE CONTRACT",
        "SECTION EDIT OUTPUT RULE",
        "content source of truth",
    ):
        assert marker in repair, f"missing in repair prompt: {marker}"


def test_second_validation_failure_uses_latest_error_on_third_attempt():
    """Second validation failure → further repair with latest error only."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    # Attempt1: missing section_edit; Attempt2: empty replacement; Attempt3: ok
    bad_empty_body = {
        "opportunities": [
            {
                "question": "What is an agent loop in tool-calling systems?",
                "gap": "Needs clarification.",
                "evidence_quote": (
                    "The agent loop lets a model call tools, see results, "
                    "and decide whether to continue."
                ),
                "target_heading": "What is an agent loop?",
                "recommended_change": "Clarify lead.",
                "answerability": "weak",
            }
        ],
        "section_edits": [
            {
                "target_heading": "What is an agent loop?",
                "replacement_body": "   ",
            }
        ],
        "change_explanations": [],
    }
    client = SequencingLLM(
        [
            _invalid_unchanged_target_payload(),
            bad_empty_body,
            _valid_loop_payload(),
        ]
    )
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=client
    )
    assert client.calls == 3
    assert "REPAIR FEEDBACK" in client.prompts[1]
    assert "REPAIR FEEDBACK" in client.prompts[2]
    assert "This is a second repair attempt" in client.prompts[2]
    assert "replacement_body is empty" in client.prompts[2]
    assert bundle.opportunities


def test_recommendation_attempts_capped_at_three():
    """No more than 3 recommendation attempts."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    client = SequencingLLM(
        [
            _invalid_unchanged_target_payload(),
            _invalid_unchanged_target_payload(),
            _invalid_unchanged_target_payload(),
            _valid_loop_payload(),  # must never be consumed
        ]
    )
    with pytest.raises(LLMError, match="missing section_edit|section_edits"):
        generate_recommendations(article, qs, VisibilityReport(), client=client)
    assert client.calls == MAX_RECOMMENDATION_ATTEMPTS == 3
    assert len(client.outcomes) == 1  # fourth payload unused


def test_failed_recommended_never_becomes_current_on_retry():
    """Failed response is never used as CURRENT for the next attempt."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    failed = {
        "opportunities": [
            {
                "question": "What is an agent loop in tool-calling systems?",
                "gap": "Needs clarification.",
                "evidence_quote": (
                    "The agent loop lets a model call tools, see results, "
                    "and decide whether to continue."
                ),
                "target_heading": "What is an agent loop?",
                "recommended_change": "Clarify lead.",
                "answerability": "weak",
            }
        ],
        "section_edits": [
            {
                "target_heading": "What is an agent loop?",
                "replacement_body": (
                    "UNIQUE_FAILED_RECOMMENDED_MARKER_XYZ\n"
                    "The agent loop lets a model call tools."
                ),
            }
        ],
        "change_explanations": ["bad"],
    }
    # This fails evidence/validation or succeeds assembly - make it fail via
    # also returning forbidden recommended_markdown so parse raises before apply.
    failed["recommended_markdown"] = (
        "# Spoofed Full Article\n\nUNIQUE_FAILED_RECOMMENDED_MARKER_XYZ\n"
    )
    client = SequencingLLM([failed, _valid_loop_payload()])
    generate_recommendations(article, qs, VisibilityReport(), client=client)
    assert client.calls == 2
    assert "UNIQUE_FAILED_RECOMMENDED_MARKER_XYZ" not in _article_block_from_prompt(
        client.prompts[1]
    )
    assert _article_block_from_prompt(client.prompts[0]) == article.markdown
    assert _article_block_from_prompt(client.prompts[1]) == article.markdown


def test_repaired_response_that_passes_is_returned():
    """Repaired response that passes validation is returned normally."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    client = SequencingLLM(
        [
            LLMError("Could not parse JSON from LLM response: ['Expecting value']"),
            _valid_loop_payload(),
        ]
    )
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=client
    )
    assert client.calls == 2
    assert "REPAIR FEEDBACK" in client.prompts[1]
    assert "Could not parse JSON" in client.prompts[1]
    assert bundle.source == "llm_generated"
    assert "keeps calling tools until the task is done" in bundle.recommended_markdown


def test_bidirectional_consistency_still_enforced_after_retry_path():
    """PR #48 bidirectional opp ↔ RECOMMENDED consistency still enforced."""
    article = load_hashnode_markdown(text=ARTICLE)
    with pytest.raises(LLMError, match="unchanged|applied"):
        validate_recommended_markdown(
            ARTICLE,
            ARTICLE,
            article=article,
            opportunities=[_loop_opp()],
        )
    with pytest.raises(LLMError, match="without matching opportunities"):
        validate_recommended_markdown(
            ARTICLE,
            _good_recommended(edit_loop=True, edit_tools=False),
            article=article,
            opportunities=[],
        )


def test_section_edits_assemble_complete_recommended_markdown():
    """1. LLM returns section edits → bundle.recommended_markdown is Python-complete."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    client = ScriptedLLM(_valid_loop_payload())
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=client
    )
    assert "# Agents Zero to Hero" in bundle.recommended_markdown
    assert "## Choosing tools for a harness" in bundle.recommended_markdown
    assert "keeps calling tools until the task is done" in bundle.recommended_markdown
    assert len(bundle.section_edits) == 1


def test_untouched_sections_unchanged_when_editing_one():
    """2. Untouched sections unchanged (edit only section #2)."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="How do tool schemas drive function calls?")])
    payload = {
        "opportunities": [
            {
                "question": "How do tool schemas drive function calls?",
                "gap": "Host observation understated.",
                "evidence_quote": (
                    "Tool calling works by giving the model a schema of available functions."
                ),
                "target_heading": "How tool calling works",
                "recommended_change": "Mention host observation.",
                "answerability": "weak",
            }
        ],
        "section_edits": [_tools_section_edit()],
        "change_explanations": ["tools only"],
    }
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=ScriptedLLM(payload)
    )
    secs = {s.heading: s.body for s in parse_sections(bundle.recommended_markdown)}
    orig = {s.heading: s.body for s in article.sections}
    assert secs["What is an agent loop?"] == orig["What is an agent loop?"]
    assert secs["Choosing tools for a harness"] == orig["Choosing tools for a harness"]
    assert secs["How tool calling works"] != orig["How tool calling works"]


def test_section_deletion_impossible_through_assembly():
    """3. Section deletion impossible through assembly (preservation by construction)."""
    from aeo_mvp.recommendations import SectionEdit, _apply_section_edits

    article = load_hashnode_markdown(text=ARTICLE)
    edited = _apply_section_edits(
        article.markdown,
        [
            SectionEdit(
                target_heading="What is an agent loop?",
                replacement_body=_loop_body_edited(),
            )
        ],
    )
    orig_heads = [s.heading for s in parse_sections(article.markdown)]
    new_heads = [s.heading for s in parse_sections(edited)]
    assert orig_heads == new_heads


def test_multiple_section_edits_apply():
    """4. Multiple section edits."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(
        selected=[
            Query(text="What is an agent loop in tool-calling systems?"),
            Query(text="How do tool schemas drive function calls?"),
        ]
    )
    payload = {
        "opportunities": [
            {
                "question": "What is an agent loop in tool-calling systems?",
                "gap": "Termination cue.",
                "evidence_quote": (
                    "The agent loop lets a model call tools, see results, "
                    "and decide whether to continue."
                ),
                "target_heading": "What is an agent loop?",
                "recommended_change": "Clarify loop.",
                "answerability": "weak",
            },
            {
                "question": "How do tool schemas drive function calls?",
                "gap": "Host observation.",
                "evidence_quote": (
                    "Tool calling works by giving the model a schema of available functions."
                ),
                "target_heading": "How tool calling works",
                "recommended_change": "Clarify host.",
                "answerability": "weak",
            },
        ],
        "section_edits": [_loop_section_edit(), _tools_section_edit()],
        "change_explanations": ["two sections"],
    }
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=ScriptedLLM(payload)
    )
    assert len(bundle.section_edits) == 2
    assert "keeps calling tools until the task is done" in bundle.recommended_markdown
    assert "returns the observation" in bundle.recommended_markdown


def test_duplicate_section_edits_rejected():
    """5. Duplicate section_edits → LLMError."""
    from aeo_mvp.recommendations import _parse_section_edits

    article = load_hashnode_markdown(text=ARTICLE)
    raw = {
        "section_edits": [
            _loop_section_edit(),
            dict(_loop_section_edit()),
        ]
    }
    with pytest.raises(LLMError, match="Duplicate section_edit"):
        _parse_section_edits(raw, article)


def test_unknown_section_edit_heading_rejected():
    """6. Unknown heading rejected."""
    from aeo_mvp.recommendations import _parse_section_edits

    article = load_hashnode_markdown(text=ARTICLE)
    raw = {
        "section_edits": [
            {
                "target_heading": "This Heading Does Not Exist",
                "replacement_body": "Some body text that is long enough.",
            }
        ]
    }
    with pytest.raises(LLMError, match="does not exist"):
        _parse_section_edits(raw, article)


def test_empty_replacement_body_rejected():
    """7. Empty replacement rejected."""
    from aeo_mvp.recommendations import _parse_section_edits

    article = load_hashnode_markdown(text=ARTICLE)
    raw = {
        "section_edits": [
            {"target_heading": "What is an agent loop?", "replacement_body": "  \n"}
        ]
    }
    with pytest.raises(LLMError, match="replacement_body is empty"):
        _parse_section_edits(raw, article)


def test_opportunity_without_section_edit_rejected():
    """8. Opportunity without applied section edit rejected."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    with pytest.raises(LLMError, match="missing section_edit"):
        generate_recommendations(
            article,
            qs,
            VisibilityReport(),
            client=ScriptedLLM(_invalid_unchanged_target_payload()),
        )


def test_section_edit_without_opportunity_rejected():
    """9. Section edit without opportunity rejected."""
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    payload = {
        "opportunities": [],
        "section_edits": [_loop_section_edit()],
        "change_explanations": [],
    }
    with pytest.raises(LLMError, match="without matching opportunities"):
        generate_recommendations(
            article, qs, VisibilityReport(), client=ScriptedLLM(payload)
        )


def test_quality_evaluation_sees_complete_assembled_document():
    """13. Quality evaluation still sees complete document."""
    from aeo_mvp.evaluation import evaluate_quality

    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    qs = QuerySet(selected=[Query(text="What is an agent loop in tool-calling systems?")])
    bundle = generate_recommendations(
        article, qs, VisibilityReport(), client=ScriptedLLM(_valid_loop_payload())
    )

    class EvalLLM:
        model = "eval-mock"
        prompts: list[str] = []

        def respond_json(self, prompt: str, *, max_output_tokens: int = 4096):
            import aeo_mvp.llm as llm_mod

            self.prompts.append(prompt)
            llm_mod._LLM_CALLS += 1
            return {
                "passed": True,
                "summary": "ok",
                "question_feedback": [],
                "recommendation_feedback": [],
                "unsupported_claims": [],
                "unnecessary_changes": [],
                "explanations": ["pass"],
            }

    ev = EvalLLM()
    result = evaluate_quality(article, qs, bundle, client=ev)
    assert result.passed is True
    prompt = ev.prompts[0]
    assert "RECOMMENDED MARKDOWN:" in prompt
    assert "# Agents Zero to Hero" in prompt
    assert "## Choosing tools for a harness" in prompt
    assert "keeps calling tools until the task is done" in prompt


def test_response_usage_metadata_from_mocked_responses_api():
    """14. Token metadata from mocked Responses API (only real fields present)."""
    from aeo_mvp.llm import LLMResult, extract_response_usage

    data = {
        "status": "completed",
        "usage": {"input_tokens": 120, "output_tokens": 40, "total_tokens": 160},
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [],
    }
    meta = extract_response_usage(data)
    assert meta["input_tokens"] == 120
    assert meta["output_tokens"] == 40
    assert meta["status"] == "completed"
    assert meta["incomplete_reason"] == "max_output_tokens"

    sparse = extract_response_usage({"output": []})
    assert sparse["input_tokens"] is None
    assert sparse["output_tokens"] is None
    assert sparse["status"] is None
    assert sparse["incomplete_reason"] is None

    result = LLMResult(text="{}", raw=data, **{k: meta[k] for k in meta})
    assert result.input_tokens == 120
    assert result.incomplete_reason == "max_output_tokens"
