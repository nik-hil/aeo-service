"""JobOrchestrator — authoritative pipeline order from BLUEPRINT §4."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from aeo_mvp.analyzers.content import analyze_content
from aeo_mvp.analyzers.entities import analyze_entities
from aeo_mvp.analyzers.structured_data import analyze_structured_data
from aeo_mvp.analyzers.technical import analyze_technical
from aeo_mvp.config import (
    DEMO_BASE_URL,
    EXPERIMENT_PROTOCOL_VERSION,
    HEALTH_FORMULA_VERSION,
    PROMPT_SET_ID,
    get_settings,
)
from aeo_mvp.crawler.discover import crawl_site
from aeo_mvp.db.models import (
    AnalysisEvidence,
    ExperimentConfig,
    ExperimentMetric,
    Job,
    VisibilityObservation as VisObsRow,
    new_id,
    utc_now_iso,
)
from aeo_mvp.demo.loader import load_prompt_set_fixture
from aeo_mvp.recommendations.engine import (
    TriggerContext,
    prioritize_recommendations,
    synthesize_findings,
)
from aeo_mvp.report.builder import build_report
from aeo_mvp.scoring.health import compute_health
from aeo_mvp.visibility.base import VisibilityContext
from aeo_mvp.visibility.demo import DemoProvider
from aeo_mvp.visibility.metrics import aggregate_metrics, filter_brand_tokens, registrable_domain
from aeo_mvp.visibility.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class JobOrchestrator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()

    def _set_status(self, job: Job, status: str, error: str | None = None) -> None:
        job.status = status
        job.updated_at = utc_now_iso()
        if error is not None:
            job.error_message = error
        if status == "completed":
            job.completed_at = utc_now_iso()
        self.session.flush()

    def _select_provider(
        self, job: Job, options: dict[str, Any]
    ) -> tuple[Any, str | None, bool]:
        """Return (provider, model_id, used_demo_fallback)."""
        provider_opt = (options.get("provider") or "auto").lower()
        demo = bool(job.demo_mode) or self.settings.demo_mode or provider_opt == "demo"
        if demo or provider_opt == "demo":
            return DemoProvider(), None, False
        if provider_opt == "openai_compatible":
            if not self.settings.openai_api_key:
                raise RuntimeError(
                    "provider=openai_compatible requires OPENAI_API_KEY"
                )
            p = OpenAICompatibleProvider()
            return p, p.model, False
        # auto
        if self.settings.openai_api_key:
            p = OpenAICompatibleProvider()
            return p, p.model, False
        return DemoProvider(), None, True

    def _build_prompts(
        self, job: Job, options: dict[str, Any], brand: str
    ) -> list[dict[str, str]]:
        if job.demo_mode:
            fixture = load_prompt_set_fixture()
            return [
                {"id": p["id"], "query": p["query"], "intent": p["intent"]}
                for p in fixture["prompts"]
            ]
        domain = registrable_domain(job.base_url)
        category = options.get("category") or "answer engine optimization"
        templates = [
            ("ps1_brand", "brand", f"What is {brand}?"),
            ("ps2_category", "category", f"What are leading options for {category}?"),
            (
                "ps3_compare",
                "comparison-neutral",
                f"How do teams evaluate tools in {category}?",
            ),
            (
                "ps4_problem",
                "problem/solution",
                "How can a website improve its chances of being cited in AI answers?",
            ),
            (
                "ps5_best",
                "best-for",
                f"What is a good resource for answer engine optimization on {domain}?",
            ),
        ]
        return [{"id": i, "intent": intent, "query": q} for i, intent, q in templates]

    async def run(self, job_id: str) -> Job:
        job = self.session.get(Job, job_id)
        if job is None:
            raise ValueError(f"unknown job {job_id}")
        options = json.loads(job.options_json or "{}")
        provenance = "synthetic_demo" if job.demo_mode else "derived_metric"

        try:
            # 1. Crawl
            self._set_status(job, "crawling")
            crawl = await crawl_site(
                self.session,
                job.id,
                job.base_url,
                demo_mode=bool(job.demo_mode),
                max_pages=min(int(options.get("max_pages", 25)), 25),
                max_depth=min(int(options.get("max_depth", 2)), 2),
                timeout_s=float(options.get("timeout_s", self.settings.crawl_timeout_s)),
            )
            pages = crawl.pages

            # 2–5. Analyzers
            self._set_status(job, "analyzing")
            tech = analyze_technical(
                self.session,
                job.id,
                pages,
                robots_allowed_root=crawl.robots_allowed_root,
                provenance=provenance,
            )
            content = analyze_content(
                self.session, job.id, pages, provenance=provenance
            )
            entity = analyze_entities(
                self.session, job.id, pages, job.base_url, provenance=provenance
            )
            structured = analyze_structured_data(
                self.session, job.id, pages, provenance=provenance
            )

            # 6. Health
            self._set_status(job, "scoring")
            job.health_formula_version = HEALTH_FORMULA_VERSION
            health = compute_health(
                self.session,
                job.id,
                technical=tech.score,
                content=content.content_score,
                entity=entity.score,
                structured_data=structured.score,
                answerability=content.answerability_score,
                breakdowns={
                    "technical": tech.breakdown,
                    "content": content.content_breakdown,
                    "entity": entity.breakdown,
                    "structured_data": structured.breakdown,
                    "answerability": content.answerability_breakdown,
                },
                provenance=provenance,
            )

            # 7–8. Experiment
            self._set_status(job, "experimenting")
            job.experiment_protocol_version = EXPERIMENT_PROTOCOL_VERSION
            provider, model_id, used_demo_fallback = self._select_provider(job, options)
            brand = entity.brand_tokens[0] if entity.brand_tokens else registrable_domain(job.base_url).split(".")[0]
            prompts = self._build_prompts(job, options, brand)
            runs_per_prompt = int(options.get("runs_per_prompt", 3))
            runs_per_prompt = max(1, min(runs_per_prompt, 5))

            exp_cfg = ExperimentConfig(
                id=new_id(),
                job_id=job.id,
                protocol_version=EXPERIMENT_PROTOCOL_VERSION,
                provider_name=provider.name,
                model_id=model_id,
                prompt_set_id=PROMPT_SET_ID,
                prompts_json=json.dumps(prompts, sort_keys=True),
                runs_per_prompt=runs_per_prompt,
                created_at=utc_now_iso(),
            )
            self.session.add(exp_cfg)
            self.session.flush()

            brand_tokens = filter_brand_tokens(entity.brand_tokens)
            site_domain = registrable_domain(job.base_url)
            observations = []
            for prompt in prompts:
                for run_index in range(runs_per_prompt):
                    ctx = VisibilityContext(
                        job_id=job.id,
                        base_url=job.base_url,
                        brand_tokens=brand_tokens,
                        site_registrable_domain=site_domain,
                        prompt_id=prompt["id"],
                        run_index=run_index,
                    )
                    obs = await provider.run_query(prompt["query"], context=ctx)
                    observations.append(obs)
                    row = VisObsRow(
                        id=new_id(),
                        job_id=job.id,
                        experiment_config_id=exp_cfg.id,
                        provider_name=obs.provider_name,
                        engine_label=obs.engine_label,
                        query=obs.query,
                        prompt_id=obs.prompt_id,
                        run_index=obs.run_index,
                        observed_at=obs.observed_at.replace(microsecond=0).isoformat(),
                        raw_response=obs.raw_response if obs.raw_storage_permitted else None,
                        raw_storage_permitted=1 if obs.raw_storage_permitted else 0,
                        detected_mention=1 if obs.detected_mention else 0,
                        detected_citation=1 if obs.detected_citation else 0,
                        cited_urls_json=json.dumps(obs.cited_urls),
                        extraction_methodology=obs.extraction_methodology,
                        provenance=obs.provenance,
                        meta_json=json.dumps(obs.meta, sort_keys=True),
                    )
                    self.session.add(row)
            self.session.flush()

            rates = aggregate_metrics(observations)
            metric_prov = "synthetic_demo" if provider.name == "demo" else "estimate"
            for name, value, num, den in (
                (
                    "ai_mention_rate",
                    rates.ai_mention_rate,
                    rates.mention_numerator,
                    rates.denominator_runs,
                ),
                (
                    "ai_citation_rate",
                    rates.ai_citation_rate,
                    rates.citation_numerator,
                    rates.denominator_runs,
                ),
                (
                    "query_coverage",
                    rates.query_coverage,
                    rates.coverage_numerator,
                    rates.denominator_prompts,
                ),
            ):
                self.session.add(
                    ExperimentMetric(
                        id=new_id(),
                        job_id=job.id,
                        metric_name=name,
                        value=value,
                        numerator=num,
                        denominator=den,
                        provenance=metric_prov,
                        protocol_version=EXPERIMENT_PROTOCOL_VERSION,
                    )
                )
            self.session.flush()

            # 9–10. Findings + recommendations
            self._set_status(job, "synthesizing")
            evidence = (
                self.session.query(AnalysisEvidence)
                .filter(AnalysisEvidence.job_id == job.id)
                .all()
            )
            obs_rows = (
                self.session.query(VisObsRow)
                .filter(VisObsRow.job_id == job.id)
                .all()
            )
            findings = synthesize_findings(
                self.session,
                job.id,
                evidence,
                mention_rate=rates.ai_mention_rate,
                citation_rate=rates.ai_citation_rate,
                used_demo_fallback=used_demo_fallback or bool(job.demo_mode),
                observation_ids=[o.id for o in obs_rows],
            )

            evidence_by_code: dict[str, list] = defaultdict(list)
            for ev in evidence:
                evidence_by_code[ev.code].append(ev)

            home_af = None
            if content.page_scores:
                # homepage is depth 0 — match first page score by url path /
                home_ps = content.page_scores[0]
                for ps in content.page_scores:
                    path = urlparse(ps.url).path or "/"
                    if path in ("/", ""):
                        home_ps = ps
                        break
                home_af = home_ps.checks.get("C2")

            ctx = TriggerContext(
                tech_checks=tech.checks,
                content_page_checks=[ps.checks for ps in content.page_scores],
                entity_checks=entity.checks,
                sd_checks=structured.checks,
                ans_checks=content.checks_a,
                has_organization=structured.has_organization,
                parse_error_evidence_ids=[
                    e.id for e in evidence_by_code.get("SD_PARSE_ERROR", [])
                ],
                component_scores=health.components,
                mention_rate=rates.ai_mention_rate,
                citation_rate=rates.ai_citation_rate,
                used_demo_fallback=used_demo_fallback or bool(job.demo_mode),
                evidence_by_code=dict(evidence_by_code),
                home_answer_first=home_af,
            )
            prioritize_recommendations(self.session, job.id, findings, ctx)

            # 11. Report — mark completed before emit so report_json.status matches job
            self._set_status(job, "completed")
            build_report(self.session, job)
            logger.info(
                "job %s completed health=%.1f mention=%.2f",
                job.id,
                health.health,
                rates.ai_mention_rate,
            )
            return job
        except Exception as exc:  # noqa: BLE001
            logger.exception("job %s failed", job_id)
            self._set_status(job, "failed", error=str(exc))
            self.session.commit()
            raise


async def run_job(session: Session, job_id: str) -> Job:
    return await JobOrchestrator(session).run(job_id)


def create_job_record(
    session: Session,
    url: str,
    *,
    demo_mode: bool = False,
    options: dict[str, Any] | None = None,
) -> Job:
    settings = get_settings()
    options = dict(options or {})
    force_demo = demo_mode or settings.demo_mode or options.get("provider") == "demo"
    base = DEMO_BASE_URL if force_demo else url
    if force_demo:
        # Normalize demo URL
        base = DEMO_BASE_URL
    job = Job(
        id=new_id(),
        base_url=base,
        demo_mode=1 if force_demo else 0,
        status="pending",
        options_json=json.dumps(options, sort_keys=True),
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    session.add(job)
    session.flush()
    return job
