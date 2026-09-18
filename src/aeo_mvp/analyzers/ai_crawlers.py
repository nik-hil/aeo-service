"""AI crawler accessibility analysis (P1-A).

Reports robots.txt / meta policy per documented AI agent.
Never claims that allow ⇒ AI visibility or consumer ranking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

from aeo_mvp.analyzers.base import EvidenceAtom, eligible_pages, homepage, persist_evidence
from aeo_mvp.crawler.robots import RobotsRules, parse_robots, path_from_url
from aeo_mvp.db.models import Page
from sqlalchemy.orm import Session

Purpose = Literal["training", "search_index", "user_fetch"]

SAMPLE_PATHS_DEFAULT = ("/", "/about", "/blog", "/pricing", "/faq")

# Documented agents from docs/research/retrieval-providers-and-ai-crawlers.md
AI_CRAWLER_AGENTS: list[dict[str, Any]] = [
    {
        "name": "GPTBot",
        "robots_token": "GPTBot",
        "purpose": "training",
        "source_url": "https://developers.openai.com/api/docs/bots",
        "notes": "OpenAI foundation-model training crawl",
    },
    {
        "name": "OAI-SearchBot",
        "robots_token": "OAI-SearchBot",
        "purpose": "search_index",
        "source_url": "https://developers.openai.com/api/docs/bots",
        "notes": "Indexes sites for ChatGPT search results (not training)",
    },
    {
        "name": "ChatGPT-User",
        "robots_token": "ChatGPT-User",
        "purpose": "user_fetch",
        "source_url": "https://developers.openai.com/api/docs/bots",
        "notes": "User-triggered fetches; robots.txt may not apply",
        "robots_may_not_apply": True,
    },
    {
        "name": "Google-Extended",
        "robots_token": "Google-Extended",
        "purpose": "training",
        "source_url": "https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers",
        "notes": "Robots control token for Gemini training/grounding — not a separate HTTP UA; does not affect Google Search inclusion",
        "is_control_token": True,
    },
    {
        "name": "Googlebot",
        "robots_token": "Googlebot",
        "purpose": "search_index",
        "source_url": "https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers",
        "notes": "Primary Google Search crawler",
    },
    {
        "name": "ClaudeBot",
        "robots_token": "ClaudeBot",
        "purpose": "training",
        "source_url": "https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler",
        "notes": "Anthropic training crawl",
    },
    {
        "name": "Claude-SearchBot",
        "robots_token": "Claude-SearchBot",
        "purpose": "search_index",
        "source_url": "https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler",
        "notes": "Anthropic search/index crawl",
    },
    {
        "name": "Claude-User",
        "robots_token": "Claude-User",
        "purpose": "user_fetch",
        "source_url": "https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler",
        "notes": "User-initiated Claude fetches",
    },
    {
        "name": "PerplexityBot",
        "robots_token": "PerplexityBot",
        "purpose": "search_index",
        "source_url": "https://docs.perplexity.ai/docs/resources/perplexity-crawlers",
        "notes": "Surfaces sites in Perplexity search; not foundation-model training",
    },
    {
        "name": "Perplexity-User",
        "robots_token": "Perplexity-User",
        "purpose": "user_fetch",
        "source_url": "https://docs.perplexity.ai/docs/resources/perplexity-crawlers",
        "notes": "User-triggered fetches; generally ignores robots.txt",
        "robots_may_not_apply": True,
    },
]

CAVEAT = (
    "robots.txt allow/disallow is an accessibility signal only. "
    "Allow does NOT imply AI search visibility, citation, or consumer-UI ranking."
)


@dataclass
class CrawlerPathPolicy:
    path: str
    allowed: bool | None  # True allow, False disallow, None default-allow / unknown
    decision: str  # allow | disallow | default_allow | unknown | not_applicable


@dataclass
class CrawlerAgentReport:
    crawler_name: str
    purpose: Purpose
    robots_token: str
    source_url: str
    confidence: float
    path_policies: list[CrawlerPathPolicy] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    robots_fetched: bool = False


@dataclass
class AICrawlerAccessResult:
    agents: list[CrawlerAgentReport]
    robots_url: str | None
    robots_fetched: bool
    google_extended_meta: dict[str, Any]
    robots_meta_home: str | None
    caveat: str
    evidence_ids: list[str]
    report_section: dict[str, Any]


def _decision_label(
    allowed: bool | None,
    *,
    robots_fetched: bool,
    robots_may_not_apply: bool,
) -> str:
    if robots_may_not_apply:
        return "not_applicable"
    if not robots_fetched:
        return "unknown"
    if allowed is False:
        return "disallow"
    if allowed is True:
        return "allow"
    return "default_allow"


def _confidence(
    *,
    robots_fetched: bool,
    is_control_token: bool,
    robots_may_not_apply: bool,
) -> float:
    if robots_may_not_apply:
        return 0.4
    if not robots_fetched:
        return 0.2
    if is_control_token:
        return 0.75
    return 0.9


def _extract_google_extended_and_robots_meta(pages: list[Page]) -> tuple[dict[str, Any], str | None]:
    """Scan homepage (and eligible pages) for google-extended / robots meta."""
    home = homepage(pages)
    robots_meta_home = home.robots_meta if home else None
    google_extended: dict[str, Any] = {
        "present": False,
        "content": None,
        "page_url": None,
    }
    for p in ([home] if home else []) + eligible_pages(pages):
        if not p or not p.html:
            continue
        html_l = p.html.lower()
        # Look for meta name="google-extended" or robots content mentioning google-extended
        if 'name="google-extended"' in html_l or "name='google-extended'" in html_l:
            # crude extract
            google_extended = {
                "present": True,
                "content": "detected",
                "page_url": p.url,
            }
            break
        if "google-extended" in html_l and "meta" in html_l:
            google_extended = {
                "present": True,
                "content": "mentioned_in_html",
                "page_url": p.url,
            }
            break
    return google_extended, robots_meta_home


def analyze_path_for_agent(
    robots_text: str | None,
    token: str,
    path: str,
    *,
    robots_may_not_apply: bool = False,
) -> CrawlerPathPolicy:
    if robots_may_not_apply:
        return CrawlerPathPolicy(path=path, allowed=None, decision="not_applicable")
    if robots_text is None:
        return CrawlerPathPolicy(path=path, allowed=None, decision="unknown")
    rules: RobotsRules = parse_robots(robots_text, token)
    allowed = rules.is_allowed(path)
    return CrawlerPathPolicy(
        path=path,
        allowed=allowed,
        decision=_decision_label(
            allowed, robots_fetched=True, robots_may_not_apply=False
        ),
    )


def analyze_ai_crawlers(
    session: Session,
    job_id: str,
    pages: list[Page],
    *,
    robots_raw: str | None,
    base_url: str,
    sample_paths: list[str] | None = None,
    provenance: str = "derived_metric",
) -> AICrawlerAccessResult:
    paths = list(sample_paths or SAMPLE_PATHS_DEFAULT)
    # Prefer real crawled paths when available
    crawled_paths = sorted({path_from_url(p.url) for p in pages if p.url})
    if crawled_paths:
        merged: list[str] = []
        for p in ["/", *crawled_paths, *paths]:
            if p not in merged:
                merged.append(p)
        paths = merged[:8]

    robots_fetched = bool(robots_raw and robots_raw.strip())
    parsed_base = urlparse(base_url)
    robots_url = urljoin(base_url if base_url.endswith("/") else base_url + "/", "robots.txt")
    if parsed_base.scheme and parsed_base.netloc:
        robots_url = f"{parsed_base.scheme}://{parsed_base.netloc}/robots.txt"

    google_extended_meta, robots_meta_home = _extract_google_extended_and_robots_meta(pages)

    agents: list[CrawlerAgentReport] = []
    atoms: list[EvidenceAtom] = []

    for spec in AI_CRAWLER_AGENTS:
        may_na = bool(spec.get("robots_may_not_apply"))
        is_token = bool(spec.get("is_control_token"))
        path_policies = [
            analyze_path_for_agent(
                robots_raw if robots_fetched else None,
                spec["robots_token"],
                path,
                robots_may_not_apply=may_na,
            )
            for path in paths
        ]
        conf = _confidence(
            robots_fetched=robots_fetched,
            is_control_token=is_token,
            robots_may_not_apply=may_na,
        )
        meta: dict[str, Any] = {
            "is_control_token": is_token,
            "robots_may_not_apply": may_na,
        }
        if spec["name"] == "Google-Extended":
            meta["google_extended_html"] = google_extended_meta
        if robots_meta_home:
            meta["homepage_robots_meta"] = robots_meta_home

        report = CrawlerAgentReport(
            crawler_name=spec["name"],
            purpose=spec["purpose"],
            robots_token=spec["robots_token"],
            source_url=spec["source_url"],
            confidence=conf,
            path_policies=path_policies,
            meta=meta,
            notes=spec.get("notes", ""),
            robots_fetched=robots_fetched,
        )
        agents.append(report)

        disallowed = [pp for pp in path_policies if pp.decision == "disallow"]
        sev = "medium" if disallowed and spec["purpose"] == "search_index" else "info"
        atoms.append(
            EvidenceAtom(
                analyzer="ai_crawlers",
                code=f"AI_CRAWLER_{spec['name'].upper().replace('-', '_')}",
                severity=sev,
                message=(
                    f"{spec['name']} ({spec['purpose']}): "
                    + (
                        f"{len(disallowed)} path(s) disallowed"
                        if disallowed
                        else "no explicit disallow on sample paths"
                    )
                ),
                data={
                    "crawler_name": spec["name"],
                    "purpose": spec["purpose"],
                    "source_url": spec["source_url"],
                    "confidence": conf,
                    "paths": [
                        {"path": pp.path, "decision": pp.decision, "allowed": pp.allowed}
                        for pp in path_policies
                    ],
                    "caveat": CAVEAT,
                },
                page_id=homepage(pages).id if homepage(pages) else None,
                provenance=provenance,
            )
        )

    atoms.append(
        EvidenceAtom(
            analyzer="ai_crawlers",
            code="AI_CRAWLER_CAVEAT",
            severity="info",
            message=CAVEAT,
            data={"robots_fetched": robots_fetched, "robots_url": robots_url},
            provenance=provenance,
        )
    )

    rows = persist_evidence(session, job_id, atoms)
    section = {
        "robots_url": robots_url,
        "robots_fetched": robots_fetched,
        "caveat": CAVEAT,
        "google_extended_meta": google_extended_meta,
        "homepage_robots_meta": robots_meta_home,
        "agents": [
            {
                "crawler_name": a.crawler_name,
                "purpose": a.purpose,
                "robots_token": a.robots_token,
                "source_url": a.source_url,
                "confidence": a.confidence,
                "notes": a.notes,
                "robots_fetched": a.robots_fetched,
                "meta": a.meta,
                "path_policies": [
                    {
                        "path": pp.path,
                        "allowed": pp.allowed,
                        "decision": pp.decision,
                    }
                    for pp in a.path_policies
                ],
            }
            for a in agents
        ],
        "provenance": provenance,
    }
    return AICrawlerAccessResult(
        agents=agents,
        robots_url=robots_url,
        robots_fetched=robots_fetched,
        google_extended_meta=google_extended_meta,
        robots_meta_home=robots_meta_home,
        caveat=CAVEAT,
        evidence_ids=[r.id for r in rows],
        report_section=section,
    )
