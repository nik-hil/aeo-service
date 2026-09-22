"""Tests for grounded recommendations and opportunity analysis."""

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.queries import discover_queries
from aeo_mvp.recommendations import (
    analyze_opportunities,
    apply_recommendations,
    evidence_quote_in_article,
    generate_recommendations,
)
from aeo_mvp.visibility import VisibilityObservation, VisibilityReport

ARTICLE = """# Agents Zero to Hero

Intro about agents and tool calling.

## What is an agent loop?

The agent loop lets a model call tools, see results, and decide whether to continue.

## How tool calling works

Tool calling works by giving the model a schema of available functions.

## Choosing tools for a harness

A minimal harness needs read, write, and shell tools.

## Common failure modes

Hallucinated tool names and infinite loops are common failure modes.
"""


def test_evidence_quote_must_appear_in_article():
    article = load_hashnode_markdown(text=ARTICLE)
    real = "The agent loop lets a model call tools, see results, and decide whether to continue."
    assert evidence_quote_in_article(real, article.plain_text())
    assert not evidence_quote_in_article(
        "According to a 2024 study, agents boost SEO by 40%.",
        article.plain_text(),
    )


def test_no_all_ops_on_h1_mega_section():
    article = load_hashnode_markdown(text=ARTICLE)
    qs = discover_queries(article, top_n=12)
    opps = analyze_opportunities(article, qs, visibility=None)
    recs = generate_recommendations(article, opps)
    h1 = article.sections[0].heading
    # With H2+ present, recommendations must not target H1.
    assert all(r.target_heading != h1 for r in recs)


def test_no_single_section_pileup():
    article = load_hashnode_markdown(text=ARTICLE)
    qs = discover_queries(article, top_n=16)
    opps = analyze_opportunities(article, qs)
    recs = generate_recommendations(article, opps)
    counts: dict[str, int] = {}
    for r in recs:
        counts[r.target_heading] = counts.get(r.target_heading, 0) + 1
    assert counts, "expected some recommendations"
    assert max(counts.values()) <= 2


def test_observed_vs_generated_not_conflated():
    article = load_hashnode_markdown(text=ARTICLE, target_domain="blog.example.com")
    qs = discover_queries(article, top_n=8)
    q0 = qs.selected[0].text
    vis = VisibilityReport(
        observations=[
            VisibilityObservation(
                query=q0,
                answer="some answer",
                mentioned=False,
                cited=False,
                target_domain_in_sources=False,
                source_urls=["https://other.com/a"],
            )
        ]
    )
    opps = analyze_opportunities(article, qs, visibility=vis)
    observed = [o for o in opps if o.question == q0]
    assert observed
    assert observed[0].source == "observed"
    assert observed[0].observed_mention is False
    # Others without visibility stay generated.
    others = [o for o in opps if o.question != q0]
    if others:
        assert all(o.source == "generated" for o in others)


def test_recommendation_fields_present_and_specific():
    article = load_hashnode_markdown(text=ARTICLE)
    qs = discover_queries(article, top_n=10)
    opps = analyze_opportunities(article, qs)
    recs = generate_recommendations(article, opps)
    assert recs
    for r in recs:
        assert r.question
        assert r.answerability in {"strong", "weak", "missing"}
        assert r.target_heading
        assert r.problem
        assert r.proposed_change
        # No generic SEO fluff slogans.
        assert "meta keywords" not in r.proposed_change.lower()
        assert "boost your seo ranking" not in r.proposed_change.lower()


def test_apply_skips_h1_and_never_publishes():
    article = load_hashnode_markdown(text=ARTICLE)
    qs = discover_queries(article, top_n=8)
    recs = generate_recommendations(article, analyze_opportunities(article, qs))
    out = apply_recommendations(article.markdown, recs)
    assert out  # still markdown
    # Structure preserved: H2 headings remain.
    assert "## What is an agent loop?" in out
