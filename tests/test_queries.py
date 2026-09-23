"""LLM question discovery — mocks only; no heading heuristics."""

import json

import pytest

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.llm import LLMError, reset_execution_flags
from aeo_mvp.queries import (
    MAX_QUESTIONS,
    MIN_QUESTIONS,
    discover_queries,
    validate_question_records,
)


ARTICLE = """# Building Agents with Tool Calling

An agent loop lets a model call tools, observe results, and continue until done.

## The agent loop

The harness executes tool calls and appends observations to the message history.

## Tool schemas

Schemas describe function names and arguments the model may invoke.

## Security boundaries

Untrusted code execution needs sandboxing and permission gates.
"""


class ScriptedLLM:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls = 0
        self.model = "mock-model"
        self.prompts: list[str] = []

    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096):
        import aeo_mvp.llm as llm_mod

        self.prompts.append(prompt)
        self.calls += 1
        llm_mod._LLM_CALLS += 1
        if not self.responses:
            raise LLMError("no scripted response left")
        return self.responses.pop(0)


def _five_questions():
    return {
        "questions": [
            {
                "question": "What is an agent loop in tool-calling systems?",
                "importance": "high",
                "reason": "core concept",
                "article_topics_or_evidence": "The agent loop section",
            },
            {
                "question": "How do tool schemas constrain model function calls?",
                "importance": "high",
                "reason": "mechanism",
                "article_topics_or_evidence": "Tool schemas",
            },
            {
                "question": "Why sandbox untrusted code execution for agents?",
                "importance": "medium",
                "reason": "security",
                "article_topics_or_evidence": "Security boundaries",
            },
            {
                "question": "How are tool results fed back into the model?",
                "importance": "medium",
                "reason": "workflow",
                "article_topics_or_evidence": "message history",
            },
            {
                "question": "What separates a chatbot from a tool-using agent?",
                "importance": "high",
                "reason": "definition",
                "article_topics_or_evidence": "intro",
            },
        ]
    }


def test_validate_rejects_malformed_and_dedupes():
    raw = {
        "questions": [
            {"question": "What is an agent loop in practice?"},
            {"question": "What is an agent loop in practice?"},  # dup
            {"question": "Hi"},  # too short
            "How do tool schemas work for agents?",
            {"question": "x" * 300},  # too long
        ]
    }
    qs = validate_question_records(raw)
    texts = [q.text for q in qs]
    assert texts.count("What is an agent loop in practice?") == 1
    assert all(12 <= len(t) <= 220 for t in texts)


def test_discover_queries_uses_llm_twice_and_returns_5_to_10():
    reset_execution_flags()
    article = load_hashnode_markdown(text=ARTICLE)
    client = ScriptedLLM([_five_questions(), _five_questions()])
    qs = discover_queries(article, client=client)
    assert client.calls == 2
    assert MIN_QUESTIONS <= len(qs.selected) <= MAX_QUESTIONS
    assert len(qs.candidates) >= MIN_QUESTIONS
    # Full article present in first prompt — not heading templates.
    assert "Building Agents with Tool Calling" in client.prompts[0]
    assert "How does Security boundaries work?" not in " ".join(qs.texts)
    joined = " ".join(q.text.lower() for q in qs.selected)
    assert "agent" in joined or "tool" in joined


def test_discover_rejects_too_few_after_validation():
    article = load_hashnode_markdown(text=ARTICLE)
    few = {"questions": [{"question": "What is an agent loop really?"}]}
    client = ScriptedLLM([_five_questions(), few])
    with pytest.raises(LLMError, match="5"):
        discover_queries(article, client=client)


def test_no_key_fails_closed_without_heuristics():
    reset_execution_flags()
    from aeo_mvp.llm import LLMClient
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()
    article = load_hashnode_markdown(text=ARTICLE)
    with pytest.raises(LLMError, match="AEO_LLM_API_KEY"):
        discover_queries(article, client=LLMClient(api_key=None))
