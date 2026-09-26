"""Frozen prompt set + competitor parsing tests."""

from pathlib import Path

import pytest

from aeo_mvp.competitors import Competitor, parse_competitors
from aeo_mvp.llm import LLMError
from aeo_mvp.prompt_set import load_prompt_set_json, parse_prompts_text, resolve_prompt_set

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "prompt_set_v1.json"
COMP_EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "competitors_v1.json"


def test_load_example_prompt_set():
    ps = load_prompt_set_json(EXAMPLE)
    assert ps.version == "1"
    assert len(ps.prompts) == 5
    kinds = {p.kind for p in ps.prompts}
    assert "factual" in kinds and "branded" in kinds
    qs = ps.to_queryset()
    assert all(q.source == "frozen_prompt_set" for q in qs.selected)
    assert qs.selected[0].kind == "factual"


def test_parse_prompts_text_lines():
    ps = parse_prompts_text(
        "# comment\n"
        "factual: What is an agent loop for calling tools?\n"
        "branded: Does Example cover agents?\n"
        "Which tools belong in a minimal harness today?\n"
    )
    assert len(ps.prompts) == 3
    assert ps.prompts[0].kind == "factual"
    assert ps.prompts[1].kind == "branded"
    assert ps.prompts[2].kind == "general"


def test_parse_prompts_text_json():
    ps = parse_prompts_text(
        '{"version":"2","prompts":[{"text":"What is tool calling schema design?","kind":"factual"}]}'
    )
    assert ps.version == "2"
    assert ps.prompts[0].kind == "factual"


def test_resolve_file_wins_over_paste(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(
        '{"version":"9","prompts":["What is a long enough frozen prompt one?"]}',
        encoding="utf-8",
    )
    ps = resolve_prompt_set(
        prompts_file=p,
        prompts_text="factual: What is a long enough frozen prompt two?",
    )
    assert ps is not None
    assert ps.version == "9"
    assert "one" in ps.prompts[0].text


def test_resolve_none_when_empty():
    assert resolve_prompt_set() is None


def test_competitors_cli_and_file():
    comps = parse_competitors("Acme|acme.com,Beta:beta.io\nGamma")
    assert comps == [
        Competitor(name="Acme", domain="acme.com"),
        Competitor(name="Beta", domain="beta.io"),
        Competitor(name="Gamma", domain=None),
    ]
    from_file = parse_competitors(competitors_file=COMP_EXAMPLE)
    assert len(from_file) == 2
    assert from_file[0].name == "LangChain"


def test_empty_prompt_set_errors():
    with pytest.raises(LLMError):
        parse_prompts_text("")
