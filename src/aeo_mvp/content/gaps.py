"""content-gap-v1 — deterministic gaps vs query-set-v3 (≠ visibility/health)."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from aeo_mvp.content.models import (
    GAP_VERSION,
    RESEARCHER_GAP_TAXONOMY,
    ContentGap,
    ContentGapReport,
    CoverageStatus,
    GapKind,
    GapSeverity,
    GapType,
    PageIntelligence,
    QueryCoverageRow,
    normalize_gap_type,
    normalize_severity,
)
from aeo_mvp.queries.evidence import normalize_provenance

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#-]{1,}", re.I)
_STOP = frozenset(
    {
        "the", "and", "for", "with", "from", "this", "that", "your", "our",
        "into", "about", "using", "have", "will", "are", "was", "were",
        "been", "being", "their", "they", "them", "what", "when", "where",
        "which", "while", "how", "who", "why", "a", "an", "of", "to", "in",
        "on", "at", "by", "or", "as", "is", "it", "be", "vs", "versus",
    }
)

_TAXONOMY_LABEL = dict(RESEARCHER_GAP_TAXONOMY)

ANTI_PATTERN_CAVEATS = [
    "page_coverage_is_not_ai_visibility",
    "page_coverage_is_not_health_v1",
    "no_keyword_stuffing",
    "no_fake_citations",
    "no_guaranteed_inclusion_or_citation",
    "no_llms_txt_silver_bullet",
    "no_opaque_content_aeo_score",
    "no_thin_page_farms_per_query",
    "no_folding_page_score_into_sov",
    "cite_miss_requires_visibility_observations",
]

# Genre → expected format cues (same taxonomy; lean formats differ)
_GENRE_FORMAT_CUES: dict[str, tuple[str, ...]] = {
    "saas_product": ("pricing", "compare", "vs", "howto", "how to", "trial", "plan"),
    "documentation": ("definition", "step", "install", "reference", "api"),
    "personal_tech_blog": ("tutorial", "guide", "how to", "notes"),
    "ecommerce": ("spec", "specs", "buy", "cart", "product", "price"),
}


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if len(t) > 2 and t.lower() not in _STOP
    }


def _page_blob(page: PageIntelligence) -> str:
    parts = [
        page.title or "",
        page.meta_description or "",
        page.h1 or "",
        " ".join(h.text for h in page.headings),
        " ".join(page.topics),
        " ".join(page.entities),
        " ".join(u.heading or "" for u in page.answer_units),
        " ".join(page.faq_coverage.get("question_headings") or []),
    ]
    return " ".join(parts).lower()


def page_coverage_status(
    query_text: str,
    page: PageIntelligence,
    *,
    topic: str | None = None,
    entity: str | None = None,
    intent: str | None = None,
) -> tuple[CoverageStatus, list[str]]:
    """Lexical/topic page coverage — never labeled AI visibility or health."""
    blob = _page_blob(page)
    q_tokens = _tokens(query_text)
    matched: list[str] = []
    if not q_tokens:
        return "unknown", matched

    phrase = re.sub(r"\s+", " ", (query_text or "").strip().lower())
    if len(phrase) >= 8 and phrase in blob:
        matched.append("exact_phrase")
        return "full", matched

    hit = sorted(t for t in q_tokens if t in blob)
    matched.extend(hit)
    ratio = len(hit) / max(len(q_tokens), 1)

    topic_hit = False
    if topic:
        if topic.lower() in blob or _tokens(topic).issubset(_tokens(blob)):
            topic_hit = True
            matched.append(f"topic:{topic}")

    entity_hit = False
    if entity and entity.lower() in blob:
        entity_hit = True
        matched.append(f"entity:{entity}")

    # Intent mismatch: commercial query on thin personal-blog page without buy/pricing signals
    mismatched = False
    if intent == "commercial":
        commercial_cues = ("pricing", "buy", "price", "cart", "trial", "plan")
        if not any(c in blob for c in commercial_cues) and ratio < 0.5:
            mismatched = True
            matched.append("intent_mismatch:commercial")

    if mismatched and ratio < 0.45:
        return "mismatched", matched
    if ratio >= 0.75 and (topic_hit or entity_hit or len(hit) >= 3):
        return "full", matched
    if ratio >= 0.45 or (topic_hit and ratio >= 0.25):
        return "partial", matched
    if 0 < ratio < 0.45 or topic_hit or entity_hit:
        return "thin", matched
    return "absent", matched


def _iter_queries(queryset: Any) -> list[dict[str, Any]]:
    if queryset is None:
        return []
    if isinstance(queryset, list):
        out = []
        for i, item in enumerate(queryset):
            if isinstance(item, dict):
                out.append(item)
            elif hasattr(item, "to_dict"):
                out.append(item.to_dict())
            else:
                out.append({"query_id": f"q_{i}", "text": str(item)})
        return out
    if hasattr(queryset, "members"):
        rows = []
        for m in queryset.members:
            q = m.query if hasattr(m, "query") else m
            rows.append(
                {
                    "query_id": getattr(q, "query_id", None)
                    or (q.get("query_id") if isinstance(q, dict) else None),
                    "text": getattr(q, "text", None)
                    or (q.get("text") if isinstance(q, dict) else str(q)),
                    "intent": getattr(q, "intent", None)
                    if not isinstance(q, dict)
                    else q.get("intent"),
                    "topic": getattr(q, "topic", None)
                    if not isinstance(q, dict)
                    else q.get("topic"),
                    "entity": getattr(q, "entity", None)
                    if not isinstance(q, dict)
                    else q.get("entity"),
                }
            )
        return rows
    if isinstance(queryset, dict):
        members = queryset.get("members") or queryset.get("queries") or []
        rows = []
        for m in members:
            if not isinstance(m, dict):
                continue
            q = m.get("query") if isinstance(m.get("query"), dict) else m
            rows.append(
                {
                    "query_id": q.get("query_id") or q.get("id"),
                    "text": q.get("text") or q.get("query"),
                    "intent": q.get("intent"),
                    "topic": q.get("topic"),
                    "entity": q.get("entity"),
                }
            )
        return rows
    return []


def assess_coverage_by_query(
    page: PageIntelligence,
    queryset: Any,
    *,
    visibility_observations: list[dict[str, Any]] | None = None,
) -> list[QueryCoverageRow]:
    rows: list[QueryCoverageRow] = []
    obs_by_qid: dict[str, dict[str, Any]] = {}
    for obs in visibility_observations or []:
        # Optional enrich only — cite_miss only when observations exist (D1)
        qid = str(obs.get("prompt_id") or obs.get("query_id") or "")
        if qid:
            obs_by_qid[qid] = obs

    for q in _iter_queries(queryset):
        text = (q.get("text") or "").strip()
        qid = str(q.get("query_id") or q.get("id") or f"q_{len(rows)}")
        status, matched = page_coverage_status(
            text,
            page,
            topic=q.get("topic"),
            entity=q.get("entity"),
            intent=q.get("intent"),
        )
        note = {
            "full": "Query concepts appear substantively on page",
            "partial": "Partial lexical/topic overlap",
            "thin": "Thin/weak mention only",
            "absent": "No detectable page coverage",
            "mismatched": "Intent/format mismatch with page signals",
            "unknown": "Insufficient tokens to assess",
        }[status]
        enrich = None
        if qid in obs_by_qid:
            o = obs_by_qid[qid]
            enrich = {
                "source": "optional_visibility_observation",
                "detected_mention": bool(o.get("detected_mention")),
                "detected_citation": bool(o.get("detected_citation")),
                "note": "visibility enrich only; not page_coverage",
            }
            if not o.get("detected_citation"):
                enrich["cite_miss"] = True  # allowed only because observation exists
        rows.append(
            QueryCoverageRow(
                query_id=qid,
                query_text=text,
                intent=q.get("intent"),
                topic=q.get("topic"),
                page_coverage=status,
                matched_signals=matched,
                note=note,
                visibility_enrichment=enrich,
            )
        )
    order = {
        "absent": 0,
        "mismatched": 1,
        "thin": 2,
        "unknown": 3,
        "partial": 4,
        "full": 5,
    }
    rows.sort(key=lambda r: (order[r.page_coverage], r.query_id, r.query_text.lower()))
    return rows


def summarize_coverage(rows: Iterable[QueryCoverageRow]) -> dict[str, int]:
    summary = {
        "full": 0,
        "partial": 0,
        "thin": 0,
        "absent": 0,
        "mismatched": 0,
        "unknown": 0,
    }
    for r in rows:
        summary[r.page_coverage] = summary.get(r.page_coverage, 0) + 1
    return summary


def _gap_id(kind: str, *parts: str) -> str:
    h = hashlib.sha256("|".join([kind, *parts]).encode()).hexdigest()[:10]
    return f"gap_{kind}_{h}"


def _taxonomy_label(gap_type: GapType) -> str | None:
    return _TAXONOMY_LABEL.get(gap_type)


def _make_gap(
    *,
    id: str,
    kind: GapKind,
    gap_type: GapType,
    severity: GapSeverity,
    explanation: str,
    evidence: list[dict[str, Any]],
    action: str,
    confidence: float,
    query_ids: list[str] | None = None,
    page_coverage: CoverageStatus | None = None,
) -> ContentGap:
    return ContentGap(
        id=id,
        kind=kind,
        gap_type=gap_type,
        severity=severity,
        query_ids=list(query_ids or []),
        explanation=explanation,
        evidence=evidence,
        action=action,
        confidence=confidence,
        provenance="derived",
        page_coverage=page_coverage,
        taxonomy_label=_taxonomy_label(gap_type),
    )


def _sev_rank(s: GapSeverity | str) -> int:
    s = normalize_severity(str(s))
    return {"high": 0, "medium": 1, "low": 2}.get(s, 9)


def _type_rank(t: GapType | str) -> int:
    from aeo_mvp.content.models import normalize_gap_type

    t = normalize_gap_type(str(t))
    order = [
        "missing_page",
        "thin_coverage",
        "no_answer_block",
        "entity_mismatch",
        "schema_gap",
        "cite_miss",
        "structure_gap",
        "question_coverage_gap",
        "evidence_gap",
        "format_gap",
        "freshness_gap",
        "technical_extractability_gap",
        "genre_mismatch",
        "intent_mismatch",
        "unsupported_claim",
        "orphan_strength",
        "false_coverage_nav",
    ]
    return order.index(t) if t in order else 99


def _kind_for_coverage(status: CoverageStatus) -> GapKind:
    if status == "absent":
        return "missing_answer"
    if status == "thin":
        return "thin_passage"
    if status == "mismatched":
        return "wrong_intent"
    return "thin_passage"


def build_content_gap_report(
    page: PageIntelligence,
    queryset: Any,
    *,
    site_profile: dict[str, Any] | None = None,
    visibility_observations: list[dict[str, Any]] | None = None,
) -> ContentGapReport:
    """Deterministic content-gap-v1. Evidence-backed only. No opaque AEO score."""
    gaps: list[ContentGap] = []
    coverage_rows = assess_coverage_by_query(
        page, queryset, visibility_observations=visibility_observations
    )
    summary = summarize_coverage(coverage_rows)
    profile = site_profile or {}
    readiness_ids: list[str] = []
    queryset_ids: list[str] = []

    qs_version = "query-set-v3"
    if isinstance(queryset, dict) and queryset.get("query_set_version"):
        qs_version = str(queryset["query_set_version"])
    elif hasattr(queryset, "query_set_version"):
        qs_version = str(getattr(queryset, "query_set_version"))

    # --- query coverage gaps ---
    for row in coverage_rows:
        if row.page_coverage in ("absent", "thin", "mismatched"):
            sev: GapSeverity = (
                "high" if row.page_coverage == "absent" else "medium"
            )
            gtype: GapType = (
                "intent_mismatch"
                if row.page_coverage == "mismatched"
                else "query"
            )
            gid = _gap_id(row.page_coverage, row.query_id)
            gaps.append(
                ContentGap(
                    id=gid,
                    kind=_kind_for_coverage(row.page_coverage),
                    gap_type=gtype,
                    severity=sev,
                    query_ids=[row.query_id],
                    explanation=(
                        f"Query '{row.query_text}' has page_coverage={row.page_coverage}"
                    ),
                    evidence=[
                        {
                            "evidence_class": "article_body",
                            "provenance": normalize_provenance("derived"),
                            "snippet": row.note,
                            "matched_signals": row.matched_signals,
                        }
                    ],
                    action=(
                        "Add one strong answer unit for this probe using on-page facts only."
                    ),
                    confidence=0.72 if row.page_coverage == "absent" else 0.55,
                    provenance="derived",
                    page_coverage=row.page_coverage,
                )
            )
            queryset_ids.append(gid)

    # --- structure / thin ---
    if page.word_count < 120 or page.body_signals.get("empty"):
        gid = _gap_id("structure", "thin")
        gaps.append(
            ContentGap(
                id=gid,
                kind="thin_passage",
                gap_type="structure",
                severity="critical" if page.word_count < 40 else "high",
                explanation=f"Thin or empty body (word_count={page.word_count})",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": "derived",
                        "snippet": f"word_count={page.word_count}",
                    }
                ],
                action="Expand with answer-first sections grounded in known site facts.",
                confidence=0.8,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)
    elif len(page.headings) < 2:
        gid = _gap_id("structure", "headings")
        gaps.append(
            ContentGap(
                id=gid,
                kind="unstructured",
                gap_type="structure",
                severity="medium",
                explanation="Fewer than two headings; weak section structure",
                evidence=[
                    {
                        "evidence_class": "title_h1",
                        "provenance": "observed",
                        "snippet": f"heading_count={len(page.headings)}",
                    }
                ],
                action="Introduce H2 sections aligned to uncovered probes.",
                confidence=0.62,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)

    # --- QA / FAQ ---
    faq = page.faq_coverage or {}
    if not faq.get("has_faq_schema") and int(faq.get("question_count") or 0) == 0:
        gid = _gap_id("qa", page.url or "page")
        gaps.append(
            ContentGap(
                id=gid,
                kind="missing_faq",
                gap_type="qa_coverage",
                severity="medium",
                explanation="No FAQ schema and no question-shaped headings observed",
                evidence=[
                    {
                        "evidence_class": "jsonld",
                        "provenance": normalize_provenance(faq.get("provenance")),
                        "snippet": "faq_missing",
                    }
                ],
                action="Add 2–5 question headings with concise answers; consider FAQPage JSON-LD.",
                confidence=0.66,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)

    # --- evidence / answerability ---
    ans = page.answerability_signals or {}
    if not ans.get("answer_first_heuristic"):
        gid = _gap_id("evidence", "answer_first")
        gaps.append(
            ContentGap(
                id=gid,
                kind="thin_passage",
                gap_type="evidence",
                severity="medium",
                explanation="Page does not lead with a clear declarative answer",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": normalize_provenance(ans.get("provenance")),
                        "snippet": "answer_first_heuristic=false",
                    }
                ],
                action="Open with a 40+ character direct answer sentence.",
                confidence=0.5,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)
    if not ans.get("has_howto_steps") and not ans.get("has_definition_pattern"):
        gid = _gap_id("evidence", "steps")
        gaps.append(
            ContentGap(
                id=gid,
                kind="missing_steps",
                gap_type="evidence",
                severity="low",
                explanation="No definition or how-to step patterns observed",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": "derived",
                        "snippet": "missing_definition_and_howto",
                    }
                ],
                action="Add a short definition and/or numbered steps where truthful.",
                confidence=0.45,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)

    # --- entity ---
    profile_entities: list[str] = []
    for key in ("org_name", "products", "authors"):
        fld = profile.get(key) or {}
        val = fld.get("value") if isinstance(fld, dict) else None
        if isinstance(val, list):
            profile_entities.extend(str(x) for x in val)
        elif isinstance(val, str) and val.strip():
            profile_entities.append(val.strip())
    blob = _page_blob(page)
    page_ent = {e.lower() for e in page.entities}
    for ent in sorted({e for e in profile_entities if e}, key=str.lower):
        if ent.lower() not in page_ent and ent.lower() not in blob:
            gid = _gap_id("entity", ent.lower())
            gaps.append(
                ContentGap(
                    id=gid,
                    kind="entity_unclear",
                    gap_type="entity",
                    severity="low",
                    explanation=f"Entity '{ent}' from site profile missing on page",
                    evidence=[
                        {
                            "evidence_class": "metadata",
                            "provenance": normalize_provenance("derived"),
                            "snippet": ent,
                        }
                    ],
                    action=f"Mention '{ent}' with a grounded definition or role statement.",
                    confidence=0.4,
                    provenance="derived",
                )
            )
            readiness_ids.append(gid)

    # --- format / structured data ---
    sd = page.structured_data or {}
    types = set(sd.get("types") or [])
    if not types:
        gid = _gap_id("format", "jsonld")
        gaps.append(
            ContentGap(
                id=gid,
                kind="unstructured",
                gap_type="format",
                severity="medium",
                explanation="No JSON-LD types observed",
                evidence=[
                    {
                        "evidence_class": "jsonld",
                        "provenance": normalize_provenance(sd.get("provenance")),
                        "snippet": "jsonld_absent",
                    }
                ],
                action="Add appropriate schema.org types mirroring visible content.",
                confidence=0.7,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)

    # --- metadata ---
    if not page.title:
        gid = _gap_id("metadata", "title")
        gaps.append(
            ContentGap(
                id=gid,
                kind="missing_answer",
                gap_type="metadata",
                severity="high",
                explanation="Missing document title",
                evidence=[
                    {
                        "evidence_class": "title_h1",
                        "provenance": normalize_provenance(None),
                        "snippet": "title_missing",
                    }
                ],
                action="Set a unique, descriptive <title>.",
                confidence=0.9,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)
    if not page.meta_description:
        gid = _gap_id("metadata", "meta")
        gaps.append(
            ContentGap(
                id=gid,
                kind="thin_passage",
                gap_type="metadata",
                severity="medium",
                explanation="Missing meta description",
                evidence=[
                    {
                        "evidence_class": "og_meta",
                        "provenance": normalize_provenance(None),
                        "snippet": "meta_description_missing",
                    }
                ],
                action="Add a 120–160 character meta description.",
                confidence=0.85,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)
    if not page.h1:
        gid = _gap_id("metadata", "h1")
        gaps.append(
            ContentGap(
                id=gid,
                kind="missing_answer",
                gap_type="metadata",
                severity="high",
                explanation="Missing H1",
                evidence=[
                    {
                        "evidence_class": "title_h1",
                        "provenance": normalize_provenance(None),
                        "snippet": "h1_missing",
                    }
                ],
                action="Add a single H1 stating the primary answer topic.",
                confidence=0.88,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)

    # --- technical extractability ---
    if not page.body_signals.get("has_main") and not page.body_signals.get("empty"):
        gid = _gap_id("technical", "main")
        gaps.append(
            ContentGap(
                id=gid,
                kind="unstructured",
                gap_type="technical",
                severity="low",
                explanation="No <main> landmark — weaker extractability",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": "observed",
                        "snippet": "has_main=false",
                    }
                ],
                action="Wrap primary content in <main> for clearer extraction.",
                confidence=0.42,
                provenance="derived",
                taxonomy_label=_taxonomy_label("technical"),
            )
        )
        readiness_ids.append(gid)

    # --- freshness / accuracy (Researcher) ---
    # Heuristic: year tokens in title/meta that look stale relative to none — flag
    # only when page asserts a year and has commercial/outdated cue without update signal.
    year_hits = re.findall(r"\b(20[0-1]\d)\b", blob)
    if year_hits and not re.search(r"\b(updated|as of|revised|202[4-9]|203\d)\b", blob):
        gid = _gap_id("freshness", "stale_year")
        gaps.append(
            _make_gap(
                id=gid,
                kind="outdated_claim",
                gap_type="freshness",
                severity="low",
                explanation=f"Page references year(s) {sorted(set(year_hits))} without an update cue",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": "derived",
                        "snippet": f"years={sorted(set(year_hits))}",
                    }
                ],
                action="Verify claims remain accurate; add an observed 'updated' date if true.",
                confidence=0.35,
            )
        )
        readiness_ids.append(gid)

    # --- media (Researcher) ---
    # Thin media eligibility: ecommerce/docs with zero images/figures in body_signals
    media_count = int(page.body_signals.get("image_count") or 0)
    genre = None
    gf = profile.get("site_genre") or {}
    if isinstance(gf, dict):
        genre = gf.get("value")
    elif isinstance(gf, str):
        genre = gf
    if genre in ("ecommerce", "documentation", "saas_product") and media_count == 0 and page.word_count > 40:
        gid = _gap_id("media", "missing")
        gaps.append(
            _make_gap(
                id=gid,
                kind="thin_passage",
                gap_type="media",
                severity="info",
                explanation="No observed images/figures — weaker multimodal extractability for this genre",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": "derived",
                        "snippet": f"image_count={media_count};genre={genre}",
                    }
                ],
                action="Add descriptive figures/screenshots only when they clarify the answer unit.",
                confidence=0.3,
            )
        )
        readiness_ids.append(gid)

    # --- genre mismatch (Researcher) — same taxonomy; lean formats differ ---
    if genre and genre in _GENRE_FORMAT_CUES:
        cues = _GENRE_FORMAT_CUES[genre]
        if not any(c in blob for c in cues) and page.word_count > 30:
            gid = _gap_id("genre_mismatch", str(genre))
            gaps.append(
                _make_gap(
                    id=gid,
                    kind="wrong_intent",
                    gap_type="genre_mismatch",
                    severity="low",
                    explanation=(
                        f"Site genre '{genre}' expects format cues {list(cues)[:4]}… "
                        "not observed on this page"
                    ),
                    evidence=[
                        {
                            "evidence_class": "metadata",
                            "provenance": "derived",
                            "snippet": f"genre={genre};cues_missing=true",
                        }
                    ],
                    action=(
                        "Add genre-appropriate answer formats (SaaS: compare/pricing/HowTo; "
                        "Docs: defs/steps; Blog: tutorials; Ecommerce: specs/PDP) — same taxonomy."
                    ),
                    confidence=0.38,
                )
            )
            readiness_ids.append(gid)

    # --- false coverage nav: only nav/chrome tokens, thin body ---
    if page.word_count < 80 and page.internal_links and not page.h1:
        gid = _gap_id("false_coverage_nav", page.url or "page")
        gaps.append(
            ContentGap(
                id=gid,
                kind="thin_passage",
                gap_type="false_coverage_nav",
                severity="medium",
                explanation="Likely nav/chrome-only page without substantive answer body",
                evidence=[
                    {
                        "evidence_class": "url_path",
                        "provenance": "derived",
                        "snippet": f"links={len(page.internal_links)};words={page.word_count}",
                    }
                ],
                action="Do not treat navigation-only pages as answer coverage.",
                confidence=0.5,
                provenance="derived",
            )
        )
        readiness_ids.append(gid)

    # Stamp Researcher taxonomy labels on readiness-taxonomy gaps
    for g in gaps:
        if g.taxonomy_label is None:
            g.taxonomy_label = _taxonomy_label(g.gap_type)

    # Never invent cite_miss gaps without observations; emit cite_miss only with obs
    if visibility_observations:
        for row in coverage_rows:
            vis = row.visibility_enrichment or row.visibility or {}
            if vis.get("cite_miss"):
                gid = _gap_id("cite_miss", row.query_id)
                gaps.append(
                    ContentGap(
                        id=gid,
                        gap_id=gid,
                        query_id=row.query_id,
                        intent=row.intent or "informational",
                        topic=row.topic,
                        kind="missing_answer",
                        gap_type="cite_miss",
                        severity="medium",
                        explanation="Mentioned or probed but not cited in visibility observations",
                        rationale="Mentioned or probed but not cited in visibility observations",
                        evidence=[
                            {
                                "evidence_class": "visibility_observation",
                                "provenance": "observed",
                                "snippet": str(vis)[:240],
                            }
                        ],
                        action="Improve cite-worthy answer blocks; do not invent citations.",
                        confidence=0.45,
                        page_coverage=row.page_coverage,
                        impact_class="experiment_informed",
                        best_page_url=page.url or None,
                        page_id=page.page_id or None,
                    )
                )
                queryset_ids.append(gid)
    else:
        for row in coverage_rows:
            assert row.visibility_enrichment is None or "cite_miss" not in (
                row.visibility_enrichment or {}
            )

    gaps.sort(key=lambda g: (_sev_rank(g.severity), _type_rank(g.gap_type), g.id))

    # Researcher gap catalog keyed by display label (page readiness taxonomy)
    catalog: dict[str, list[str]] = {label: [] for _, label in RESEARCHER_GAP_TAXONOMY}
    for g in gaps:
        label = g.taxonomy_label or g.gap_type
        if label not in catalog and g.gap_type in _TAXONOMY_LABEL:
            label = _TAXONOMY_LABEL[g.gap_type]
        if label in catalog:
            catalog[label].append(g.id)
        else:
            catalog.setdefault(label, []).append(g.id)

    qs_id = ""
    if isinstance(queryset, dict):
        qs_id = str(queryset.get("query_set_id") or "")
    elif hasattr(queryset, "query_set_id"):
        qs_id = str(getattr(queryset, "query_set_id") or "")

    covered = sum(
        1 for r in coverage_rows if r.page_coverage in ("full", "partial")
    )
    n_queries = len(coverage_rows)
    architect_summary = {
        "queries": n_queries,
        "covered": covered,
        "gapped": max(0, n_queries - covered),
        **dict(summary),
    }
    fingerprint = hashlib.sha1(
        f"{qs_id}|{qs_version}|{page.url}|{len(gaps)}".encode()
    ).hexdigest()[:16]

    return ContentGapReport(
        gap_report_version=GAP_VERSION,
        schema_version=GAP_VERSION,
        query_set_id=qs_id,
        query_set_version=qs_version,
        queryset_fingerprint=fingerprint,
        page_url=page.url,
        gaps=gaps,
        coverage_by_query=coverage_rows,
        coverage_summary=architect_summary,
        readiness_gaps=sorted(set(readiness_ids)),
        queryset_gaps=sorted(set(queryset_ids)),
        gap_catalog_by_taxonomy=catalog,
        anti_pattern_caveats=list(ANTI_PATTERN_CAVEATS),
        warnings=[],
    )
