"""SQLAlchemy 2.x models matching BLUEPRINT §6 schema."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    demo_mode: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    options_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    health_formula_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    experiment_protocol_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)

    pages: Mapped[list[Page]] = relationship(back_populates="job", cascade="all, delete-orphan")
    evidence: Mapped[list[AnalysisEvidence]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    score_components: Mapped[list[ScoreComponent]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    experiment_configs: Mapped[list[ExperimentConfig]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    observations: Mapped[list[VisibilityObservation]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    experiment_metrics: Mapped[list[ExperimentMetric]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    findings: Mapped[list[Finding]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    report: Mapped[Report | None] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    site_profile: Mapped[SiteProfile | None] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("job_id", "url", name="uq_pages_job_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # URL that supplied analyzable body (may be a .md alternate).
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # html | markdown — content representation of the analyzable body.
    content_representation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # HTTP status of the primary (user) URL fetch; preserved when alternate used.
    primary_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # success | blocked | failed
    primary_fetch_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # not_applicable | not_attempted | success | failed
    alternate_fetch_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    html: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Exact fetched Markdown when content_representation=markdown; never reconstructed.
    source_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    robots_meta: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetch_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[Job] = relationship(back_populates="pages")
    evidence: Mapped[list[AnalysisEvidence]] = relationship(back_populates="page")


class AnalysisEvidence(Base):
    __tablename__ = "analysis_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    page_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("pages.id"), nullable=True)
    analyzer: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    provenance: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)

    job: Mapped[Job] = relationship(back_populates="evidence")
    page: Mapped[Page | None] = relationship(back_populates="evidence")


class ScoreComponent(Base):
    __tablename__ = "score_components"
    __table_args__ = (
        UniqueConstraint("job_id", "component", "formula_version", name="uq_score_comp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    component: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)
    breakdown_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="derived_metric")

    job: Mapped[Job] = relationship(back_populates="score_components")


class ExperimentConfig(Base):
    __tablename__ = "experiment_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_set_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompts_json: Mapped[str] = mapped_column(Text, nullable=False)
    runs_per_prompt: Mapped[int] = mapped_column(Integer, nullable=False)
    experiment_kind: Mapped[str | None] = mapped_column(String(64), nullable=True, default="llm_mention")
    retrieval_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discovered_queries_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)

    job: Mapped[Job] = relationship(back_populates="experiment_configs")
    observations: Mapped[list[VisibilityObservation]] = relationship(
        back_populates="experiment_config"
    )


class VisibilityObservation(Base):
    __tablename__ = "visibility_observations"
    __table_args__ = (
        UniqueConstraint(
            "experiment_config_id",
            "prompt_id",
            "run_index",
            name="uq_vis_obs_cfg_prompt_run",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    experiment_config_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_configs.id"), nullable=False
    )
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_label: Mapped[str] = mapped_column(String(128), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_index: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_storage_permitted: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    detected_mention: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_citation: Mapped[int] = mapped_column(Integer, nullable=False)
    cited_urls_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    extraction_methodology: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False)
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retrieval_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    experiment_kind: Mapped[str | None] = mapped_column(String(64), nullable=True, default="llm_mention")
    search_queries_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_urls_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_domain_appeared: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_domain_cited: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job: Mapped[Job] = relationship(back_populates="observations")
    experiment_config: Mapped[ExperimentConfig] = relationship(back_populates="observations")


class ExperimentMetric(Base):
    __tablename__ = "experiment_metrics"
    __table_args__ = (
        UniqueConstraint("job_id", "metric_name", "protocol_version", name="uq_exp_metric"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    numerator: Mapped[int] = mapped_column(Integer, nullable=False)
    denominator: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="estimate")
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)

    job: Mapped[Job] = relationship(back_populates="experiment_metrics")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    observation_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)

    job: Mapped[Job] = relationship(back_populates="findings")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    effort: Mapped[str] = mapped_column(String(8), nullable=False)
    impact: Mapped[float] = mapped_column(Float, nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    finding_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[Job] = relationship(back_populates="recommendations")



class SiteProfile(Base):
    __tablename__ = "site_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id"), nullable=False, unique=True
    )
    profile_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    method: Mapped[str] = mapped_column(String(64), nullable=False, default="deterministic_html_v1")
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="derived_metric")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)

    job: Mapped[Job] = relationship(back_populates="site_profile")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id"), nullable=False, unique=True
    )
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    emitted_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)

    job: Mapped[Job] = relationship(back_populates="report")


# Help type checkers / avoid unused import warnings for Any in annotations
_Any = Any
