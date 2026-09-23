"""Fence-aware Markdown parsing (deterministic plumbing)."""

from aeo_mvp.markdown import (
    extract_intro,
    extract_title,
    parse_sections,
    replace_section_body,
)


SAMPLE = """# Title Here

Intro paragraph about the topic.

## First Section

Body of first.

```bash
# ## Not A Heading
echo hi
```

## Second Section

Body of second.

### Nested

Nested body.

## Third Section

Body of third.
"""


def test_fence_ignores_headings_inside_code_blocks():
    sections = parse_sections(SAMPLE)
    headings = [s.heading for s in sections]
    assert "Not A Heading" not in headings
    assert headings == [
        "Title Here",
        "First Section",
        "Second Section",
        "Nested",
        "Third Section",
    ]


def test_h1_is_not_mega_section_when_h2_exist():
    sections = parse_sections(SAMPLE)
    h1 = next(s for s in sections if s.level == 1)
    assert "First Section" not in h1.body
    assert "Intro paragraph" in h1.body
    intro = extract_intro(SAMPLE, sections)
    assert "Intro paragraph" in intro
    assert "Body of first" not in intro


def test_section_boundaries_same_or_higher_level():
    sections = parse_sections(SAMPLE)
    second = next(s for s in sections if s.heading == "Second Section")
    assert "Nested body" in second.body
    assert "Body of third" not in second.body


def test_title_from_h1():
    assert extract_title(SAMPLE) == "Title Here"


def test_replace_section_preserves_siblings():
    updated = replace_section_body(SAMPLE, "Second Section", "Replaced body only.\n")
    assert "Replaced body only." in updated
    assert "Body of first." in updated
    assert "Body of third." in updated


def test_replace_section_exact_does_not_apply_substring_to_h1():
    """exact=True avoids applying an H2-named edit onto an H1 that contains that text."""
    md = """# Agents Zero to Hero #12: Building AI Subagents with Context Isolation

Intro about the series episode.

## Building AI Subagents with Context Isolation

H2 body about isolation.

## Other Section

Other body.
"""
    # Fuzzy (default) may match H1 because the H2 text is a substring of the H1.
    fuzzy = replace_section_body(
        md, "Building AI Subagents with Context Isolation", "FUZZY_BODY\n"
    )
    # Exact must only touch the H2, leaving the H1 intro intact.
    exact = replace_section_body(
        md,
        "Building AI Subagents with Context Isolation",
        "EXACT_H2_BODY\n",
        exact=True,
    )
    sections_exact = parse_sections(exact)
    h1 = next(s for s in sections_exact if s.level == 1)
    h2 = next(
        s
        for s in sections_exact
        if s.heading == "Building AI Subagents with Context Isolation"
    )
    assert "Intro about the series episode." in h1.body
    assert "EXACT_H2_BODY" in h2.body
    assert "EXACT_H2_BODY" not in h1.body
    # Document that fuzzy behaviour can differ (regression guard for exact path).
    assert "FUZZY_BODY" in fuzzy
