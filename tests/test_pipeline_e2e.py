"""End-to-end pipeline with mocked LLM (no network)."""

from pathlib import Path

from aeo_mvp.llm import llm_used, reset_execution_flags, retrieval_used
from aeo_mvp.pipeline import run_pipeline

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "sample_article.md"


class E2EMock:
    """Sequenced mock: discover → quality questions → recommend → evaluate."""

    def __init__(self):
        self.model = "mock-e2e"
        self.step = 0

    def available(self) -> bool:
        return True

    def respond(self, *args, **kwargs):
        raise AssertionError("visibility should be dry-run in this test")

    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096):
        import aeo_mvp.llm as llm_mod

        llm_mod._LLM_CALLS += 1
        self.step += 1
        questions = {
            "questions": [
                {
                    "question": "What is an agent loop for tool calling?",
                    "importance": "high",
                    "reason": "core",
                    "article_topics_or_evidence": "The agent loop",
                },
                {
                    "question": "How does tool calling use schemas?",
                    "importance": "high",
                    "reason": "mechanism",
                    "article_topics_or_evidence": "How tool calling works",
                },
                {
                    "question": "Which tools belong in a minimal harness?",
                    "importance": "medium",
                    "reason": "practical",
                    "article_topics_or_evidence": "Choosing tools",
                },
                {
                    "question": "What failure modes appear in agent loops?",
                    "importance": "medium",
                    "reason": "risks",
                    "article_topics_or_evidence": "Common failure modes",
                },
                {
                    "question": "What should come after basic tool calling?",
                    "importance": "low",
                    "reason": "roadmap",
                    "article_topics_or_evidence": "Next steps",
                },
            ],
            "notes": "ok",
        }
        if self.step in (1, 2):
            return questions
        if self.step == 3:
            md = Path(FIXTURE).read_text(encoding="utf-8")
            # RECOMMENDED assembly input must be article body only — no YAML/frontmatter.
            if md.lstrip().startswith("---"):
                parts = md.split("---", 2)
                if len(parts) >= 3:
                    md = parts[2].lstrip("\n")
            from aeo_mvp.markdown import parse_sections

            loop = next(
                s for s in parse_sections(md) if s.heading == "What is an agent loop?"
            )
            replacement = (
                loop.body.rstrip()
                + "\n\nIt keeps invoking tools until the task is finished."
            )
            evidence = (
                "The agent loop is the control flow that lets a model call tools, "
                "see results, and decide whether to continue."
            )
            return {
                "opportunities": [
                    {
                        "question": "What is an agent loop for tool calling?",
                        "gap": "Could state the loop more directly for extractability.",
                        "evidence_quote": evidence,
                        "target_heading": "What is an agent loop?",
                        "recommended_change": "Clarify the lead definition.",
                        "answerability": "weak",
                    }
                ],
                "section_edits": [
                    {
                        "target_heading": "What is an agent loop?",
                        "replacement_body": replacement,
                    }
                ],
                "change_explanations": ["Clarified agent loop wording."],
            }
        return {
            "passed": True,
            "summary": "Questions are realistic; edit is small.",
            "question_feedback": ["specific"],
            "recommendation_feedback": ["grounded"],
            "unsupported_claims": [],
            "unnecessary_changes": [],
            "explanations": ["pass"],
        }


def test_pipeline_e2e_mock_writes_artifacts(tmp_path):
    reset_execution_flags()
    report = run_pipeline(
        FIXTURE,
        dry_run=True,
        write_artifacts_dir=tmp_path,
        client=E2EMock(),  # type: ignore[arg-type]
    )
    assert report.auto_publish is False
    assert report.llm_used is True
    assert report.retrieval_used is False  # dry_run visibility
    assert 5 <= len(report.queries.selected) <= 10
    assert report.quality_eval is not None
    assert report.quality_eval.passed is True
    assert (tmp_path / "CURRENT.md").is_file()
    assert (tmp_path / "RECOMMENDED.md").is_file()
    assert (tmp_path / "DIFF.patch").is_file()
    assert (tmp_path / "report.json").is_file()
    d = report.to_dict()
    assert d["model"] == "mock-e2e"
    assert d["auto_publish"] is False
    assert "How does Repository work?" not in d["queries_selected"]


def test_flags_false_until_called():
    reset_execution_flags()
    assert llm_used() is False
    assert retrieval_used() is False
