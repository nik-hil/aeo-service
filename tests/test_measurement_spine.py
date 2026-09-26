"""Competitor share + accuracy pass tests (mocked)."""

from aeo_mvp.accuracy import evaluate_accuracy
from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.competitors import Competitor
from aeo_mvp.llm import LLMResult, reset_execution_flags
from aeo_mvp.queries import Query, QuerySet
from aeo_mvp.visibility import measure_visibility
from aeo_mvp.visibility_md import build_visibility_markdown


class FakeVisLLM:
    def __init__(self, result: LLMResult):
        self.result = result
        self.model = "mock-vis"
        self.calls = 0

    def available(self) -> bool:
        return True

    def respond(self, prompt, *, web_search=False, require_web_search=False, max_output_tokens=4096):
        import aeo_mvp.llm as llm_mod

        self.calls += 1
        llm_mod._LLM_CALLS += 1
        if self.result.had_web_search_call or self.result.source_urls or self.result.citations:
            llm_mod._RETRIEVAL_EVIDENCE += 1
        return self.result


class FakeAccuracyLLM:
    def __init__(self, payload):
        self.payload = payload
        self.model = "mock-acc"
        self.calls = 0

    def respond_json(self, prompt, *, max_output_tokens=4096):
        import aeo_mvp.llm as llm_mod

        self.calls += 1
        llm_mod._LLM_CALLS += 1
        return self.payload


def test_competitor_share_on_observation():
    reset_execution_flags()
    article = load_hashnode_markdown(
        text="# Agents\n\n## Loop\n\nTool calling loop.\n",
        target_domain="blog.example.com",
        brand_tokens=["Agents"],
    )
    qs = QuerySet(selected=[Query(text="What is an agent tool-calling loop?")])
    fake = FakeVisLLM(
        LLMResult(
            text="LangChain and Agents both use loops. See docs.",
            source_urls=[
                "https://blog.example.com/x",
                "https://langchain.com/docs",
            ],
            citations=[
                {"url": "https://langchain.com/docs", "type": "url_citation"},
            ],
            had_web_search_call=True,
        )
    )
    comps = [Competitor(name="LangChain", domain="langchain.com")]
    report = measure_visibility(article, qs, client=fake, competitors=comps)
    obs = report.observations[0]
    assert obs.competitors[0].mentioned is True
    assert obs.competitors[0].cited is True
    assert obs.competitors[0].domain_in_sources is True
    assert report.competitor_share[0].mention_rate == 1.0
    assert report.competitor_share[0].citation_rate == 1.0
    payload = report.to_dict()
    assert payload["competitor_share"][0]["name"] == "LangChain"
    assert payload["observations"][0]["competitors"][0]["cited"] is True


def test_accuracy_flags_conflict_with_evidence():
    reset_execution_flags()
    current = (
        "# Agents\n\n## Loop\n\n"
        "The agent loop keeps invoking tools until the task is finished.\n"
    )
    article = load_hashnode_markdown(text=current, brand_tokens=["Agents"])
    qs = QuerySet(
        selected=[
            Query(
                text="What is an agent loop for tool calling?",
                kind="factual",
                source="frozen_prompt_set",
            )
        ]
    )
    from aeo_mvp.visibility import VisibilityObservation, VisibilityReport

    answer = (
        "An agent loop runs exactly once and never continues after a tool call."
    )
    vis = VisibilityReport(
        observations=[
            VisibilityObservation(
                query=qs.selected[0].text,
                answer=answer,
                mentioned=True,
                cited=False,
                target_domain_in_sources=False,
            )
        ],
        mention_rate=1.0,
        query_coverage=1.0,
    )
    claim = "runs exactly once and never continues after a tool call"
    evidence = "keeps invoking tools until the task is finished"
    # Embed claim/evidence substrings that appear in answer/current
    assert claim in answer
    assert evidence in current

    fake = FakeAccuracyLLM(
        {
            "conflicts": [
                {
                    "claim_from_observed_answer": claim,
                    "evidence_quote_from_current": evidence,
                    "note": "OBSERVED says once; CURRENT says continues.",
                    "severity": "high",
                }
            ]
        }
    )
    acc = evaluate_accuracy(article, vis, qs, client=fake)
    assert fake.calls == 1
    assert len(acc.conflicts) == 1
    assert acc.conflicts[0].severity == "high"
    assert "LLM-GENERATED" in acc.to_dict()["label"]


def test_accuracy_skips_general_kind():
    article = load_hashnode_markdown(text="# A\n\n## S\n\nBody text here.\n")
    qs = QuerySet(
        selected=[Query(text="Which tools belong in a minimal harness?", kind="general")]
    )
    from aeo_mvp.visibility import VisibilityObservation, VisibilityReport

    vis = VisibilityReport(
        observations=[
            VisibilityObservation(
                query=qs.selected[0].text,
                answer="Use read/write/shell.",
                mentioned=False,
                cited=False,
                target_domain_in_sources=False,
            )
        ]
    )
    fake = FakeAccuracyLLM({"conflicts": []})
    acc = evaluate_accuracy(article, vis, qs, client=fake)
    assert fake.calls == 0
    assert acc.checks[0].skipped is True


def test_visibility_md_includes_competitors_and_accuracy():
    from aeo_mvp.accuracy import AccuracyConflict, AccuracyReport
    from aeo_mvp.visibility import (
        CompetitorShare,
        VisibilityObservation,
        VisibilityReport,
    )
    from types import SimpleNamespace

    vis = VisibilityReport(
        observations=[
            VisibilityObservation(
                query="What is an agent loop for tool calling?",
                answer="Agents use loops.",
                mentioned=True,
                cited=True,
                target_domain_in_sources=True,
                source_urls=["https://blog.example.com/x"],
                competitors=[],
            )
        ],
        mention_rate=1.0,
        citation_rate=1.0,
        target_in_sources_rate=1.0,
        query_coverage=1.0,
        competitors_configured=[Competitor(name="LangChain", domain="langchain.com")],
        competitor_share=[
            CompetitorShare(
                name="LangChain",
                domain="langchain.com",
                mention_rate=0.5,
                citation_rate=0.0,
                domain_in_sources_rate=0.0,
            )
        ],
    )
    acc = AccuracyReport(
        conflicts=[
            AccuracyConflict(
                query="What is an agent loop for tool calling?",
                claim_from_observed_answer="Agents use loops.",
                evidence_quote_from_current="The agent loop is the control flow",
                note="example",
            )
        ]
    )
    report = SimpleNamespace(
        visibility=vis,
        accuracy=acc,
        article=SimpleNamespace(title="Agents"),
        model="m",
        llm_used=True,
        retrieval_used=True,
    )
    md = build_visibility_markdown(report)  # type: ignore[arg-type]
    assert "Competitor share" in md
    assert "LangChain" in md
    assert "Brand-fact / accuracy" in md
    assert "OBSERVED" in md
    assert "not** consumer" in md or "not consumer" in md.lower() or "This is **not**" in md
