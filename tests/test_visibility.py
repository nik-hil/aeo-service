"""Visibility plumbing tests with mocks."""

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.llm import (
    LLMResult,
    llm_used,
    parse_responses_output,
    reset_execution_flags,
    retrieval_used,
)
from aeo_mvp.queries import Query, QuerySet
from aeo_mvp.visibility import measure_visibility


class FakeLLM:
    def __init__(self, result: LLMResult):
        self.result = result
        self.model = "mock-model"
        self.calls = 0
        self.web_search_flags: list[bool] = []

    def available(self) -> bool:
        return True

    def respond(self, prompt, *, web_search=False, require_web_search=False, max_output_tokens=4096):
        import aeo_mvp.llm as llm_mod

        self.calls += 1
        self.web_search_flags.append(web_search)
        llm_mod._LLM_CALLS += 1
        if self.result.had_web_search_call or self.result.source_urls or self.result.citations:
            llm_mod._RETRIEVAL_EVIDENCE += 1
        assert web_search is True
        return self.result


def test_parse_responses_detects_web_search_and_citations():
    data = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "queries": ["agent loop"],
                    "sources": [{"url": "https://blog.example.com/agents"}],
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Agents use tool loops.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://blog.example.com/agents",
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
    assert parsed["citations"]


def test_visibility_invokes_web_search_and_records_observation():
    reset_execution_flags()
    article = load_hashnode_markdown(
        text="# Agents\n\n## Loop\n\nTool calling loop.\n",
        target_domain="blog.example.com",
        brand_tokens=["Agents"],
    )
    qs = QuerySet(
        selected=[Query(text="What is an agent tool-calling loop?")]
    )
    fake = FakeLLM(
        LLMResult(
            text="Agents use loops.",
            source_urls=["https://blog.example.com/x"],
            citations=[{"url": "https://blog.example.com/x", "type": "url_citation"}],
            had_web_search_call=True,
        )
    )
    report = measure_visibility(article, qs, client=fake)
    assert fake.calls == 1
    assert fake.web_search_flags == [True]
    assert report.observations[0].provenance == "api_observation"
    assert report.observations[0].target_domain_in_sources is True
    assert report.observations[0].measures_consumer_ui is False
    assert llm_used() is True
    assert retrieval_used() is True


def test_dry_run_skips_without_fabricating():
    reset_execution_flags()
    article = load_hashnode_markdown(text="# Hello\n\n## S\n\nBody.\n")
    qs = QuerySet(selected=[Query(text="What is hello world tooling?")])
    report = measure_visibility(article, qs, dry_run=True)
    assert report.observations == []
    assert llm_used() is False
    assert retrieval_used() is False
