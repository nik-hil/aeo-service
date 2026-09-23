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
from aeo_mvp.visibility import measure_visibility, target_page_in_urls


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


# --- Exact target-page visibility (POC) ---

TARGET_ARTICLE = "https://engineering.hashnode.dev/article-7"


def _article_with_target(
    *,
    target_url: str | None = TARGET_ARTICLE,
    target_domain: str = "engineering.hashnode.dev",
):
    return load_hashnode_markdown(
        text="# Article 7\n\n## Intro\n\nBody.\n",
        target_domain=target_domain,
        target_url=target_url,
        brand_tokens=["Article"],
    )


def _measure(article, source_urls, citations=None):
    qs = QuerySet(selected=[Query(text="What is article 7 about?")])
    fake = FakeLLM(
        LLMResult(
            text="Some answer.",
            source_urls=source_urls,
            citations=citations or [],
            had_web_search_call=True,
        )
    )
    return measure_visibility(article, qs, client=fake)


def test_exact_page_found_both_true():
    report = _measure(
        _article_with_target(),
        source_urls=[TARGET_ARTICLE],
        citations=[{"url": TARGET_ARTICLE, "type": "url_citation"}],
    )
    obs = report.observations[0]
    assert obs.target_page_in_sources is True
    assert obs.target_page_cited is True


def test_same_domain_different_page_both_false():
    """Critical: article-12 on same Hashnode domain is not article-7."""
    report = _measure(
        _article_with_target(),
        source_urls=["https://engineering.hashnode.dev/article-12"],
        citations=[
            {
                "url": "https://engineering.hashnode.dev/article-12",
                "type": "url_citation",
            }
        ],
    )
    obs = report.observations[0]
    assert obs.target_domain_in_sources is True
    assert obs.target_page_in_sources is False
    assert obs.target_page_cited is False


def test_exact_page_only_in_sources():
    report = _measure(
        _article_with_target(),
        source_urls=[TARGET_ARTICLE],
        citations=[{"url": "https://other.example.com/post", "type": "url_citation"}],
    )
    obs = report.observations[0]
    assert obs.target_page_in_sources is True
    assert obs.target_page_cited is False


def test_exact_page_only_as_citation_both_true():
    report = _measure(
        _article_with_target(),
        source_urls=["https://other.example.com/post"],
        citations=[{"url": TARGET_ARTICLE, "type": "url_citation"}],
    )
    obs = report.observations[0]
    assert obs.target_page_in_sources is True
    assert obs.target_page_cited is True


def test_url_normalization_matches_variants():
    target = "https://example.com/article"
    variants = [
        "https://example.com/article",
        "https://EXAMPLE.com/article/",
        "https://example.com/article#section",
        "https://example.com:443/article",
    ]
    for v in variants:
        assert target_page_in_urls(target, [v]) is True, v


def test_different_path_does_not_match():
    assert target_page_in_urls(
        "https://example.com/article",
        ["https://example.com/article-2"],
    ) is False


def test_no_target_url_exact_page_fields_none():
    article = load_hashnode_markdown(
        text="# Hello\n\n## S\n\nBody.\n",
        target_domain="blog.example.com",
    )
    assert article.target_url is None
    report = _measure(
        article,
        source_urls=["https://blog.example.com/x"],
        citations=[{"url": "https://blog.example.com/x", "type": "url_citation"}],
    )
    obs = report.observations[0]
    assert obs.target_page_in_sources is None
    assert obs.target_page_cited is None
    assert obs.target_domain_in_sources is True
    assert report.target_page_in_sources_rate == 0.0
    assert report.target_page_citation_rate == 0.0


def test_target_url_from_front_matter_canonical():
    md = (
        "---\n"
        "canonical_url: https://engineering.hashnode.dev/article-7\n"
        "---\n"
        "# Title\n\n## S\n\nBody.\n"
    )
    article = load_hashnode_markdown(text=md)
    assert article.target_url == "https://engineering.hashnode.dev/article-7"
    assert article.target_domain == "engineering.hashnode.dev"


def test_domain_true_page_false_e2e_hashnode_sibling():
    """Mocked e2e: sibling Hashnode article → domain hit, exact page miss."""
    reset_execution_flags()
    article = load_hashnode_markdown(
        text=(
            "---\n"
            "canonical_url: https://engineering.hashnode.dev/article-7\n"
            "---\n"
            "# Agent loops\n\n## Intro\n\nBody.\n"
        ),
        brand_tokens=["Agent"],
    )
    assert article.target_domain == "engineering.hashnode.dev"
    assert article.target_url == "https://engineering.hashnode.dev/article-7"

    sibling = "https://engineering.hashnode.dev/article-12"
    report = _measure(
        article,
        source_urls=[sibling],
        citations=[{"url": sibling, "type": "url_citation"}],
    )
    obs = report.observations[0]
    assert obs.target_domain_in_sources is True
    assert obs.target_page_in_sources is False
    assert obs.target_page_cited is False
    assert report.target_page_in_sources_rate == 0.0
    assert report.target_page_citation_rate == 0.0
    assert report.target_in_sources_rate == 1.0
    payload = report.to_dict()
    assert "target_page_in_sources" in payload["observations"][0]
    assert "target_page_cited" in payload["observations"][0]
    assert "target_page_in_sources_rate" in payload
    assert "target_page_citation_rate" in payload
