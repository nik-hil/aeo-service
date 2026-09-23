"""Quality evaluation wiring tests."""

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.evaluation import evaluate_quality
from aeo_mvp.llm import reset_execution_flags
from aeo_mvp.queries import Query, QuerySet
from aeo_mvp.recommendations import Opportunity, RecommendationBundle


class ScriptedLLM:
    def __init__(self, payload: dict):
        self.payload = payload
        self.model = "mock-eval"
        self.prompts: list[str] = []

    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096):
        import aeo_mvp.llm as llm_mod

        self.prompts.append(prompt)
        llm_mod._LLM_CALLS += 1
        return self.payload


def test_quality_eval_parses_pass_fail_and_wires_inputs():
    reset_execution_flags()
    article = load_hashnode_markdown(
        text="# T\n\n## A\n\nBody about agents.\n\n## B\n\nMore.\n"
    )
    qs = QuerySet(selected=[Query(text="What is an agent loop in practice?")])
    bundle = RecommendationBundle(
        opportunities=[
            Opportunity(
                question="What is an agent loop in practice?",
                answerability="weak",
                evidence_quote="",
                target_heading="A",
                problem="unclear",
                recommended_change="clarify",
            )
        ],
        recommended_markdown=article.markdown + "\nClarified.\n",
        change_explanations=["clarified A"],
    )
    client = ScriptedLLM(
        {
            "passed": True,
            "summary": "Looks grounded.",
            "question_feedback": ["realistic"],
            "recommendation_feedback": ["small useful edit"],
            "unsupported_claims": [],
            "unnecessary_changes": [],
            "explanations": ["pass: grounded"],
        }
    )
    ev = evaluate_quality(article, qs, bundle, client=client)
    assert ev.passed is True
    assert ev.source == "llm_generated"
    assert "ORIGINAL ARTICLE" in client.prompts[0] or "T" in client.prompts[0]
    assert "What is an agent loop in practice?" in client.prompts[0]
    assert "clarified A" in client.prompts[0] or "Clarified" in client.prompts[0]
