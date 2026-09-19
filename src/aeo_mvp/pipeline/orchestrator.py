"""JobOrchestrator — authoritative pipeline order from BLUEPRINT §4 (+ P1 steps)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from aeo_mvp.analyzers.ai_crawlers import analyze_ai_crawlers
from aeo_mvp.analyzers.base import domain_label
from aeo_mvp.analyzers.content import analyze_content
from aeo_mvp.analyzers.entities import analyze_entities
from aeo_mvp.analyzers.structured_data import analyze_structured_data
from aeo_mvp.analyzers.technical import analyze_technical
from aeo_mvp.config import (
    AI_SEARCH_PROTOCOL_VERSION,
    DEMO_BASE_URL,
    HEALTH_FORMULA_VERSION,
    LLM_MENTION_PROTOCOL_VERSION,
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
from aeo_mvp.domains import registrable_domain
from aeo_mvp.queries.discovery import discover_queries
from aeo_mvp.recommendations.engine import (
    TriggerContext,
    prioritize_recommendations,
    synthesize_findings,
)
from aeo_mvp.report.builder import build_report
from aeo_mvp.scoring.health import compute_health
from aeo_mvp.security.ssrf import SSRFError, is_obviously_unsafe_url
from aeo_mvp.target_site import MATCH_RULE_VERSION, resolve_target_site_identity
from aeo_mvp.understanding.site import infer_site_understanding
from aeo_mvp.visibility.base import VisibilityContext
from aeo_mvp.visibility.competitors import extract_competitor_domains
from aeo_mvp.visibility.demo import DemoProvider
from aeo_mvp.visibility.digitalocean_web_search import (
    DigitalOceanWebSearchError,
    DigitalOceanWebSearchProvider,
)
from aeo_mvp.visibility.metrics import (
    aggregate_ai_search_metrics,
    aggregate_llm_metrics,
    filter_brand_tokens,
)
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

    @staticmethod
    def _allow_paid_do_retrieval(
        *, paid_opt_in: bool, paid_retrieval_ready: bool
    ) -> bool:
        """ADR-026: paid DO web_search only when explicit opt-in ∧ ready QuerySet."""
        return bool(paid_opt_in) and bool(paid_retrieval_ready)

    def _select_provider(
        self,
        job: Job,
        options: dict[str, Any],
        *,
        allow_paid_retrieval: bool = False,
    ) -> tuple[Any, str | None, bool]:
        """Return (provider, model_id, used_demo_fallback).

        Selection order (non-demo):
          1. Explicit options.provider or AEO_VISIBILITY_PROVIDER
          2. auto → DigitalOcean web_search if DO key present **and**
             allow_paid_retrieval (ADR-026 opt-in ∧ ready QuerySet),
             else OpenAI-compatible if OPENAI_API_KEY,
             else DemoProvider + fallback flag
        Demo mode always uses DemoProvider (deterministic).

        A configured DO API key never implicitly authorizes paid retrieval.
        """
        settings = self.settings
        provider_opt = (
            options.get("provider")
            or settings.visibility_provider
            or "auto"
        )
        provider_opt = str(provider_opt).lower().strip()
        demo = bool(job.demo_mode) or settings.demo_mode or provider_opt == "demo"
        if demo or provider_opt == "demo":
            return DemoProvider(), None, False

        if provider_opt in ("digitalocean_web_search", "digitalocean", "do_web_search"):
            if not allow_paid_retrieval:
                raise DigitalOceanWebSearchError(
                    "provider=digitalocean_web_search requires paid_retrieval_opt_in=true "
                    "and a ready QuerySet (ADR-026); DO API key alone is not sufficient"
                )
            if not settings.effective_do_api_key:
                raise DigitalOceanWebSearchError(
                    "provider=digitalocean_web_search requires DO_MODEL_ACCESS_KEY "
                    "(or MODEL_ACCESS_KEY)"
                )
            p = DigitalOceanWebSearchProvider()
            return p, p.model, False

        if provider_opt == "openai_compatible":
            if not settings.openai_api_key:
                raise RuntimeError(
                    "provider=openai_compatible requires OPENAI_API_KEY"
                )
            p = OpenAICompatibleProvider()
            return p, p.model, False

        if provider_opt not in ("auto", ""):
            raise RuntimeError(
                f"Unknown visibility provider {provider_opt!r}. "
                "Use auto, demo, openai_compatible, or digitalocean_web_search."
            )

        # auto — paid DO only when opt-in ∧ ready; never silent Perplexity stub
        if allow_paid_retrieval and settings.effective_do_api_key:
            p = DigitalOceanWebSearchProvider()
            return p, p.model, False
        if settings.openai_api_key:
            p = OpenAICompatibleProvider()
            return p, p.model, False
        return DemoProvider(), None, True

    def _fixed_template_prompts(
        self, job: Job, options: dict[str, Any], brand: str
    ) -> list[dict[str, str]]:
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

    def _build_prompts(
        self,
        job: Job,
        options: dict[str, Any],
        brand: str,
        *,
        discovered: list[dict[str, str]] | None = None,
    ) -> tuple[list[dict[str, str]], str]:
        """Return (prompts, prompt_set_id).

        Demo mode keeps fixture prompt-set for bit-stable visibility metrics.
        Otherwise prefer discovered queries; fall back to fixed templates.
        """
        if job.demo_mode:
            fixture = load_prompt_set_fixture()
            prompts = [
                {"id": p["id"], "query": p["query"], "intent": p["intent"]}
                for p in fixture["prompts"]
            ]
            return prompts, fixture.get("prompt_set_id", PROMPT_SET_ID)

        if discovered:
            return discovered, "discovered-queries-v1"

        return self._fixed_template_prompts(job, options, brand), PROMPT_SET_ID

    async def run(self, job_id: str) -> Job:
        job = self.session.get(Job, job_id)
        if job is None:
            raise ValueError(f"unknown job {job_id}")
        options = json.loads(job.options_json or "{}")
        provenance = "synthetic_demo" if job.demo_mode else "derived_metric"
        p1_sections: dict[str, Any] = {}

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

            # 2–5. Analyzers (+ P1-A AI crawlers)
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
            ai_crawl = analyze_ai_crawlers(
                self.session,
                job.id,
                pages,
                robots_raw=crawl.robots_raw,
                base_url=job.base_url,
                provenance=provenance,
            )
            p1_sections["ai_crawler_access"] = ai_crawl.report_section

            # P1-B site understanding
            use_llm = bool(options.get("site_understanding_llm")) or bool(
                self.settings.site_understanding_llm
            )
            understanding = infer_site_understanding(
                self.session,
                job.id,
                pages,
                job.base_url,
                provenance=provenance,
                use_llm=use_llm,
                openai_api_key=self.settings.openai_api_key,
            )
            p1_sections["site_understanding"] = understanding.to_dict()

            # P1-C / Phase 3–4 query discovery (generate→gate→select).
            # Paid DO retrieval is NEVER auto-started here — requires explicit opt-in
            # after a ready QuerySet (options.paid_retrieval_opt_in / settings).
            top_n = int(
                options.get("query_top_n")
                if options.get("query_top_n") is not None
                else self.settings.query_top_n
            )
            discovery_only = bool(
                options.get("discovery_only") or options.get("dry_run")
            )
            paid_opt_in = bool(
                options.get("paid_retrieval_opt_in", self.settings.paid_retrieval_opt_in)
            )
            if discovery_only:
                paid_opt_in = False
            early_identity = resolve_target_site_identity(job.base_url)
            target_audit = early_identity.to_audit_dict()
            p1_sections["target_site"] = target_audit
            discovery = discover_queries(
                understanding,
                top_n=top_n,
                provenance=provenance,
                options=options,
                paid_retrieval_opt_in=paid_opt_in,
                target_site_audit=target_audit,
                discovery_only=discovery_only,
                page_count=len(pages),
            )
            p1_sections["discovered_queries"] = discovery.to_dict()
            # ADR-026 hard gate: opt-in ∧ ready QuerySet. A DO key alone never
            # authorizes paid web_search; logging alone is not sufficient.
            allow_paid_retrieval = self._allow_paid_do_retrieval(
                paid_opt_in=paid_opt_in,
                paid_retrieval_ready=discovery.paid_retrieval_ready,
            )
            if paid_opt_in and not discovery.paid_retrieval_ready:
                logger.info(
                    "paid_retrieval_opt_in set but query set not ready; "
                    "hard-skipping DigitalOcean paid retrieval (ADR-026)"
                )
            elif not paid_opt_in:
                logger.info(
                    "paid_retrieval_opt_in false; "
                    "hard-skipping DigitalOcean paid retrieval (ADR-026)"
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
            target_identity = early_identity
            if discovery_only:
                # Persist QuerySet only — zero visibility / paid provider calls.
                used_demo_fallback = False
                prompts = (
                    discovery.as_prompts()
                    if not discovery.fallback_used
                    else []
                )
                prompt_set_id = "discovered-queries-dry-run"
                runs_per_prompt = 0
                retrieval_enabled = False
                experiment_kind = "discovery_only"
                protocol_version = LLM_MENTION_PROTOCOL_VERSION
                job.experiment_protocol_version = protocol_version
                exp_cfg = ExperimentConfig(
                    id=new_id(),
                    job_id=job.id,
                    protocol_version=protocol_version,
                    provider_name="discovery_only",
                    model_id="none",
                    prompt_set_id=prompt_set_id,
                    prompts_json=json.dumps(prompts, sort_keys=True),
                    runs_per_prompt=0,
                    experiment_kind=experiment_kind,
                    retrieval_enabled=0,
                    discovered_queries_json=json.dumps(
                        discovery.to_dict(), sort_keys=True
                    ),
                    created_at=utc_now_iso(),
                )
                self.session.add(exp_cfg)
                self.session.flush()
                observations = []
                rates_llm = None
                rates_ai = None
                mention_for_recs = 0.0
                citation_for_recs = 0.0
                log_rate = 0.0
                metric_prov = "derived_metric"
                metric_rows = []
            else:
                provider, model_id, used_demo_fallback = self._select_provider(
                    job,
                    options,
                    allow_paid_retrieval=allow_paid_retrieval,
                )
                brand = (
                    understanding.organization_brand
                    or (entity.brand_tokens[0] if entity.brand_tokens else None)
                    or domain_label(job.base_url)
                )
                prompts, prompt_set_id = self._build_prompts(
                    job,
                    options,
                    brand,
                    discovered=discovery.as_prompts() if not discovery.fallback_used else None,
                )
                runs_per_prompt = int(options.get("runs_per_prompt", 3))
                runs_per_prompt = max(1, min(runs_per_prompt, 5))

                caps = getattr(provider, "capabilities", None)
                retrieval_enabled = (
                    bool(getattr(caps, "retrieval_enabled", False)) if caps else False
                )
                experiment_kind = (
                    "ai_search_visibility" if retrieval_enabled else "llm_mention"
                )
                protocol_version = (
                    LLM_MENTION_PROTOCOL_VERSION
                    if not retrieval_enabled
                    else AI_SEARCH_PROTOCOL_VERSION
                )
                job.experiment_protocol_version = protocol_version

                exp_cfg = ExperimentConfig(
                    id=new_id(),
                    job_id=job.id,
                    protocol_version=protocol_version,
                    provider_name=provider.name,
                    model_id=model_id,
                    prompt_set_id=prompt_set_id,
                    prompts_json=json.dumps(prompts, sort_keys=True),
                    runs_per_prompt=runs_per_prompt,
                    experiment_kind=experiment_kind,
                    retrieval_enabled=1 if retrieval_enabled else 0,
                    discovered_queries_json=json.dumps(discovery.to_dict(), sort_keys=True),
                    created_at=utc_now_iso(),
                )
                self.session.add(exp_cfg)
                self.session.flush()

                brand_tokens = filter_brand_tokens(entity.brand_tokens)
                # Never use multi-tenant platform apex (e.g. "hashnode") as brand token.
                target_identity = resolve_target_site_identity(job.base_url)
                site_domain = target_identity.registrable_domain
                if (
                    target_identity.multi_tenant_host
                    and target_identity.identity_kind != "platform_apex"
                ):
                    platform_label = site_domain.split(".")[0] if site_domain else ""
                    brand_tokens = [
                        t
                        for t in brand_tokens
                        if t.lower() != platform_label.lower()
                    ]
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
                            protocol_version=protocol_version,
                            target_hostname=target_identity.hostname,
                            target_origin=target_identity.origin,
                            target_domain_scope=target_identity.target_domain_scope,
                            multi_tenant_host=target_identity.multi_tenant_host,
                            match_rule_version=MATCH_RULE_VERSION,
                            target_site=target_identity.to_audit_dict(),
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
                            model_id=obs.model_id,
                            retrieval_enabled=1 if obs.retrieval_enabled else 0,
                            experiment_kind=obs.experiment_kind,
                            search_queries_json=json.dumps(obs.search_queries or []),
                            source_urls_json=json.dumps(obs.source_urls or []),
                            target_domain_appeared=(
                                None
                                if obs.target_domain_appeared is None
                                else (1 if obs.target_domain_appeared else 0)
                            ),
                            target_domain_cited=(
                                None
                                if obs.target_domain_cited is None
                                else (1 if obs.target_domain_cited else 0)
                            ),
                        )
                        self.session.add(row)
                self.session.flush()

                rates_llm = None
                rates_ai = None
                if retrieval_enabled:
                    rates_ai = aggregate_ai_search_metrics(observations)
                    metric_prov = (
                        "synthetic_demo" if provider.name == "demo" else "estimate"
                    )
                    metric_rows = [
                        (
                            "ai_search_mention_rate",
                            rates_ai.ai_search_mention_rate,
                            rates_ai.mention_numerator,
                            rates_ai.denominator_runs,
                        ),
                        (
                            "ai_search_citation_rate",
                            rates_ai.ai_search_citation_rate,
                            rates_ai.citation_numerator,
                            rates_ai.denominator_runs,
                        ),
                        (
                            "target_domain_appearance_rate",
                            rates_ai.target_domain_appearance_rate,
                            rates_ai.appearance_numerator,
                            rates_ai.denominator_runs,
                        ),
                        (
                            "query_coverage",
                            rates_ai.query_coverage,
                            rates_ai.coverage_numerator,
                            rates_ai.denominator_prompts,
                        ),
                    ]
                    mention_for_recs = rates_ai.ai_search_mention_rate
                    citation_for_recs = rates_ai.ai_search_citation_rate
                    log_rate = rates_ai.ai_search_mention_rate
                else:
                    rates_llm = aggregate_llm_metrics(observations)
                    metric_prov = (
                        "synthetic_demo" if provider.name == "demo" else "estimate"
                    )
                    metric_rows = [
                        (
                            "llm_mention_rate",
                            rates_llm.llm_mention_rate,
                            rates_llm.mention_numerator,
                            rates_llm.denominator_runs,
                        ),
                        (
                            "llm_url_mention_rate",
                            rates_llm.llm_url_mention_rate,
                            rates_llm.url_mention_numerator,
                            rates_llm.denominator_runs,
                        ),
                        (
                            "query_coverage",
                            rates_llm.query_coverage,
                            rates_llm.coverage_numerator,
                            rates_llm.denominator_prompts,
                        ),
                    ]
                    mention_for_recs = rates_llm.llm_mention_rate
                    citation_for_recs = rates_llm.llm_url_mention_rate
                    log_rate = rates_llm.llm_mention_rate

            for name, value, num, den in metric_rows:
                self.session.add(
                    ExperimentMetric(
                        id=new_id(),
                        job_id=job.id,
                        metric_name=name,
                        value=value,
                        numerator=num,
                        denominator=den,
                        provenance=metric_prov,
                        protocol_version=protocol_version,
                    )
                )
            self.session.flush()

            # P1-D competitors only when retrieval_enabled
            competitors = extract_competitor_domains(
                observations,
                target_identity=target_identity,
            )
            if retrieval_enabled and competitors.get("applicable"):
                p1_sections["competitors"] = competitors
            if retrieval_enabled:
                p1_sections["target_site"] = target_identity.to_audit_dict()

            # Stash P1 sections into job options for report builder
            options["_p1_sections"] = p1_sections
            job.options_json = json.dumps(options, sort_keys=True)
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
                mention_rate=mention_for_recs,
                citation_rate=citation_for_recs,
                used_demo_fallback=used_demo_fallback or bool(job.demo_mode),
                observation_ids=[o.id for o in obs_rows],
            )

            evidence_by_code: dict[str, list] = defaultdict(list)
            for ev in evidence:
                evidence_by_code[ev.code].append(ev)

            home_af = None
            if content.page_scores:
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
                mention_rate=mention_for_recs,
                citation_rate=citation_for_recs,
                used_demo_fallback=used_demo_fallback or bool(job.demo_mode),
                evidence_by_code=dict(evidence_by_code),
                home_answer_first=home_af,
            )
            prioritize_recommendations(self.session, job.id, findings, ctx)

            # 11. Report
            self._set_status(job, "completed")
            build_report(self.session, job)
            logger.info(
                "job %s completed health=%.1f visibility_rate=%.2f kind=%s",
                job.id,
                health.health,
                log_rate,
                experiment_kind,
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
        base = DEMO_BASE_URL
    elif is_obviously_unsafe_url(url):
        raise SSRFError(
            f"Refusing to create job for unsafe URL (SSRF policy): {url!r}"
        )
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
