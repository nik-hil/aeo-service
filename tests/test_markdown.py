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
