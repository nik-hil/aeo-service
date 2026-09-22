"""Tests for fence-aware Markdown section parsing."""

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
    """Regression: H1 body must end at the first H2, not swallow the article."""
    sections = parse_sections(SAMPLE)
    h1 = next(s for s in sections if s.level == 1)
    assert "First Section" not in h1.body
    assert "Second Section" not in h1.body
    assert "Intro paragraph" in h1.body
    # Intro helper uses H1 body only.
    intro = extract_intro(SAMPLE, sections)
    assert "Intro paragraph" in intro
    assert "## First Section" not in intro
    assert "Body of first" not in intro


def test_section_boundaries_same_or_higher_level():
    sections = parse_sections(SAMPLE)
    second = next(s for s in sections if s.heading == "Second Section")
    assert "Nested body" in second.body
    assert "Body of third" not in second.body
    nested = next(s for s in sections if s.heading == "Nested")
    assert nested.level == 3
    assert "Body of third" not in nested.body


def test_title_from_h1():
    assert extract_title(SAMPLE) == "Title Here"


def test_replace_section_preserves_siblings():
    updated = replace_section_body(SAMPLE, "Second Section", "Replaced body only.\n")
    assert "Replaced body only." in updated
    assert "Body of first." in updated
    assert "Body of third." in updated
    # Nested was inside Second Section — replaced with section body end at next H2.
    sections = parse_sections(updated)
    second = next(s for s in sections if s.heading == "Second Section")
    assert "Replaced body only." in second.body
