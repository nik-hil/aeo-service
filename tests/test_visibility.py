"""Tests for visibility measurement and execution flags."""

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.llm import (
    LLMResult,
    llm_used,
    parse_responses_output,
    reset_execution_flags,
    retrieval_used,
)
from aeo_mvp.queries import discover_queries
from aeo_mvp.visibility import measure_visibility


class FakeLLM:
    def __init__(self, result: LLMResult | None = None, *, fail: bool = False):
        self.result = result
        self.fail = fail
        self.calls = 0

    def available(self) -> bool:
        return True

    def respond(self, prompt: str, *, web_search: bool = False, require_web_search: bool = False):
        from aeo_mvp.llm import LLMError
        import aeo_mvp.llm as llm_mod

        self.calls += 1
        if self.fail:
            raise LLMError("boom")
        llm_mod._LLM_CALLS += 1
        if self.result and (
            self.result.had_web_search_call
            or self.result.source_urls
            or self.result.citations
        ):
            llm_mod._RETRIEVAL_EVIDENCE += 1
        assert web_search is True
        return self.result or LLMResult(text="ok")


def test_parse_responses_detects_web_search_and_citations():
    data = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "queries": ["fastapi validation"],
                    "sources": [{"url": "https://blog.example.com/fastapi"}],
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "FastAPI validates with Pydantic.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://blog.example.com/fastapi",
                                "title": "Post",
                            }
                        ],
                    }
                ],
            },
        ]
    }
    parsed = parse_responses_output(data)
    assert parsed["had_web_search_call"] is True
    assert "fastapi validation" in parsed["search_queries"]
    assert "https://blog.example.com/fastapi" in parsed["source_urls"]
    assert parsed["citations"]


def test_dry_run_does_not_fabricate_and_flags_false():
    reset_execution_flags()
    article = load_hashnode_markdown(
        text="# Hello\n\n## Section\n\nBody about hello world tools.\n",
        target_domain="blog.example.com",
    )
    qs = discover_queries(article, top_n=8)
    report = measure_visibility(article, qs, dry_run=True)
    assert report.observations == []
    assert llm_used() is False
    assert retrieval_used() is False


def test_retrieval_used_only_with_tool_evidence():
    reset_execution_flags()
    article = load_hashnode_markdown(
        text="# FastAPI Tips\n\n## Validation\n\nPydantic validates requests.\n",
        target_domain="blog.example.com",
        brand_tokens=["FastAPI"],
    )
    qs = discover_queries(article, top_n=3)
    # Limit to 1 query for the fake.
    qs.selected = qs.selected[:1]

    fake = FakeLLM(
        LLMResult(
            text="FastAPI is great for APIs.",
            source_urls=["https://blog.example.com/x"],
            citations=[{"url": "https://blog.example.com/x", "type": "url_citation"}],
            had_web_search_call=True,
        )
    )
    report = measure_visibility(article, qs, client=fake)  # type: ignore[arg-type]
    assert len(report.observations) == 1
    assert report.observations[0].target_domain_in_sources is True
    assert llm_used() is True
    assert retrieval_used() is True


def test_llm_used_false_unless_called():
    reset_execution_flags()
    assert llm_used() is False
    assert retrieval_used() is False
