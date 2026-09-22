"""Grounded LLM section synthesis (opt-in; fail-closed).

Design lock: thin module owned by content optimization. Uses the same
OpenAI-compatible ``/chat/completions`` path as draft_paid (api_key, model,
base_url). Never invents facts. Hashnode markdown_generator must not import
or call this module.

Ops:
- rewrite_section (primary): replace a bounded section body
- add_explanation (secondary): insert clarifying prose after an anchor

Every body op returns ``proposed`` + ``claims[{claim, evidence_quote}]``.
Reject → author_input_required (evidence exists but blocked) or
research_required (corpus insufficient).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import httpx

from aeo_mvp.config import get_settings

logger = logging.getLogger(__name__)

Disposition = Literal["actionable", "author_input_required", "research_required"]
EntailmentLabel = Literal["ENTAILED", "NOT_ENTAILED"]

ChatFn = Callable[[list[dict[str, str]], float], str]

_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
_PROPER_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-]{2,}")
_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+)$", re.M)

_SYNTH_SYSTEM = (
    "You rewrite or clarify web article Markdown using ONLY the provided "
    "corpus evidence. Never invent URLs, numbers, product names, citations, "
    "or facts absent from the corpus. Respond with a single JSON object only."
)

_ENTAIL_SYSTEM = (
    "You are an entailment judge. Given a claim and evidence quotes from a "
    "source page, reply with exactly one token: ENTAILED or NOT_ENTAILED."
)

# Prefer quality: at most this many grounded body ops per plan pass.
MAX_GROUNDED_BODY_OPS = 2
# Soft token-overlap prefilter (never sufficient alone for accept).
MIN_TOKEN_OVERLAP_RATIO = 0.35


@dataclass
class GroundedClaim:
    claim: str
    evidence_quote: str

    def to_dict(self) -> dict[str, str]:
        return {"claim": self.claim, "evidence_quote": self.evidence_quote}


@dataclass
class SynthResult:
    op_kind: str
    disposition: Disposition
    proposed: str | None = None
    claims: list[GroundedClaim] = field(default_factory=list)
    original: str | None = None
    evidence: list[str] = field(default_factory=list)
    target: str = ""
    target_kind: str = "section"
    action: str = "rewrite"
    apply_mode: str = "replace_region"
    reason: str = ""
    expected_aeo_benefit: str = (
        "Improves grounded answer extractability without inventing claims."
    )
    warnings: list[str] = field(default_factory=list)
    llm_used: bool = False
    related_gap_ids: list[str] = field(default_factory=list)
    related_query_ids: list[str] = field(default_factory=list)
    query_text: str | None = None

    @property
    def status(self) -> str:
        if self.disposition == "actionable" and self.proposed:
            return "ready"
        return "needs_author_input"

    def to_dict(self) -> dict[str, Any]:
        return {
            "op_kind": self.op_kind,
            "disposition": self.disposition,
            "status": self.status,
            "proposed": self.proposed,
            "claims": [c.to_dict() for c in self.claims],
            "original": self.original,
            "evidence": list(self.evidence),
            "target": self.target,
            "target_kind": self.target_kind,
            "action": self.action,
            "apply_mode": self.apply_mode,
            "reason": self.reason,
            "expected_aeo_benefit": self.expected_aeo_benefit,
            "warnings": list(self.warnings),
            "llm_used": self.llm_used,
            "related_gap_ids": list(self.related_gap_ids),
            "related_query_ids": list(self.related_query_ids),
            "query_text": self.query_text,
        }


def grounded_synth_enabled(
    *,
    draft_paid: bool = False,
    api_key: str | None = None,
) -> bool:
    """Fail closed unless draft_paid opt-in and API key are both present."""
    return bool(draft_paid) and bool((api_key or "").strip())


def resolve_openai_compatible_credentials(
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Resolve OpenAI-compatible key/model/base_url (OPENAI_* or DO inference).

    Prefer explicit args, then OPENAI_*, then DO_MODEL_ACCESS_KEY +
    DO_INFERENCE_BASE_URL / DO_INFERENCE_MODEL. Never logs secrets.
    """
    settings = get_settings()
    key = (api_key or "").strip() or None
    if not key:
        key = (settings.openai_api_key or "").strip() or None
    if not key:
        key = (settings.effective_do_api_key or "").strip() or None

    mdl = (model or "").strip() or None
    if not mdl:
        # If key came from DO-only path (no OPENAI key), prefer DO model.
        if not (settings.openai_api_key or "").strip() and (
            settings.effective_do_api_key or ""
        ).strip():
            mdl = (settings.do_inference_model or "").strip() or None
        else:
            mdl = (settings.openai_model or "").strip() or None
    if not mdl:
        mdl = (settings.do_inference_model or "").strip() or None

    base = (base_url or "").strip() or None
    if not base:
        if not (settings.openai_api_key or "").strip() and (
            settings.effective_do_api_key or ""
        ).strip():
            base = (settings.do_inference_base_url or "").strip() or None
        else:
            base = (settings.openai_base_url or "").strip() or None
    if not base:
        base = (settings.do_inference_base_url or "").strip() or None
    return key, mdl, base


def resolve_openai_compatible_client(
    *,
    draft_paid: bool = False,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    chat_fn: ChatFn | None = None,
) -> "OpenAICompatibleChat | None":
    """Return a chat client when opted in; else None (fail closed)."""
    key, mdl, base = resolve_openai_compatible_credentials(
        api_key=api_key, model=model, base_url=base_url
    )
    if chat_fn is not None and grounded_synth_enabled(
        draft_paid=draft_paid, api_key=key or api_key or "mock"
    ):
        # Tests may inject chat_fn with a sentinel key.
        use_key = (key or api_key or "").strip() or "mock"
        return OpenAICompatibleChat(
            api_key=use_key,
            model=mdl or model,
            base_url=base or base_url,
            chat_fn=chat_fn,
        )
    if not grounded_synth_enabled(draft_paid=draft_paid, api_key=key):
        return None
    return OpenAICompatibleChat(
        api_key=(key or "").strip(),
        model=mdl or model,
        base_url=base or base_url,
        chat_fn=None,
    )


class OpenAICompatibleChat:
    """Thin sync OpenAI-compatible ``/chat/completions`` client."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        chat_fn: ChatFn | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key
        self.model = model or settings.openai_model
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self._chat_fn = chat_fn
        self.timeout_s = timeout_s

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
    ) -> str:
        if self._chat_fn is not None:
            return self._chat_fn(messages, temperature)
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"openai_compatible_http_{resp.status_code}"
                )
            data = resp.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("openai_compatible_malformed_choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise RuntimeError("openai_compatible_malformed_content")
        return content


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def token_overlap_ratio(proposed: str, corpus: str) -> float:
    """Prefilter helper — never sufficient alone to accept a proposal."""
    pt = _tokens(proposed)
    if not pt:
        return 0.0
    ct = _tokens(corpus)
    if not ct:
        return 0.0
    return len(pt & ct) / len(pt)


def quote_is_verbatim(quote: str, corpus: str) -> bool:
    q = (quote or "").strip()
    if not q or len(q) < 8:
        return False
    return q in (corpus or "")


def novelty_violations(text: str, corpus: str) -> list[str]:
    """URLs / numbers / multi-word proper names must already appear in corpus."""
    violations: list[str] = []
    c = corpus or ""
    c_lower = c.lower()
    for url in _URL_RE.findall(text or ""):
        if url.rstrip(".,);") not in c and url not in c:
            violations.append(f"invented_url:{url[:80]}")
    for num in _NUMBER_RE.findall(text or ""):
        if num not in c:
            violations.append(f"invented_number:{num}")
    for name in _PROPER_NAME_RE.findall(text or ""):
        if name.lower() not in c_lower:
            violations.append(f"invented_name:{name}")
    return violations


def validate_claims_against_corpus(
    claims: list[GroundedClaim],
    *,
    corpus: str,
    proposed: str,
) -> list[str]:
    """Quote lock + atomicity + novelty bans. Empty list ⇒ structural pass."""
    errors: list[str] = []
    if not claims:
        errors.append("claims_empty")
        return errors
    for i, cl in enumerate(claims):
        claim = (cl.claim or "").strip()
        quote = (cl.evidence_quote or "").strip()
        if not claim:
            errors.append(f"claim_{i}_empty")
            continue
        if not quote:
            errors.append(f"claim_{i}_missing_evidence_quote")
            continue
        if not quote_is_verbatim(quote, corpus):
            errors.append(f"claim_{i}_quote_not_verbatim")
        # Atomicity: claim must be supported by ≥1 quote (this claim's quote).
        # Soft lexical check — entailment judge is authoritative.
        if token_overlap_ratio(claim, quote) < 0.15 and claim.lower() not in quote.lower():
            # Still allow if quote appears in claim context; entailment decides.
            pass
        for v in novelty_violations(claim, corpus):
            errors.append(f"claim_{i}_{v}")
    for v in novelty_violations(proposed, corpus):
        errors.append(f"proposed_{v}")
    return errors


def judge_entailment(
    client: OpenAICompatibleChat,
    claims: list[GroundedClaim],
    *,
    corpus: str,
) -> list[tuple[GroundedClaim, EntailmentLabel]]:
    """ENTALED|NOT_ENTAILED per claim via the same OpenAI-compatible model."""
    out: list[tuple[GroundedClaim, EntailmentLabel]] = []
    for cl in claims:
        user = (
            f"Evidence corpus (excerpts):\n{corpus[:6000]}\n\n"
            f"Evidence quote:\n{cl.evidence_quote}\n\n"
            f"Claim:\n{cl.claim}\n\n"
            "Is the claim fully entailed by the evidence quote and corpus? "
            "Reply with exactly ENTAILED or NOT_ENTAILED."
        )
        try:
            raw = client.chat(
                [
                    {"role": "system", "content": _ENTAIL_SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001 — fail closed
            logger.warning("entailment_judge_failed: %s", type(exc).__name__)
            out.append((cl, "NOT_ENTAILED"))
            continue
        # Prefer NOT_ENTAILED when both tokens appear (substring-safe).
        upper = (raw or "").upper()
        if "NOT_ENTAILED" in upper:
            label: EntailmentLabel = "NOT_ENTAILED"
        elif re.search(r"(?<!NOT_)\bENTAILED\b", upper):
            label = "ENTAILED"
        else:
            label = "NOT_ENTAILED"
        out.append((cl, label))
    return out


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Strip common fences.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _claims_from_payload(data: dict[str, Any]) -> list[GroundedClaim]:
    raw = data.get("claims")
    if not isinstance(raw, list):
        return []
    out: list[GroundedClaim] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        quote = str(
            item.get("evidence_quote") or item.get("evidence") or ""
        ).strip()
        if claim and quote:
            out.append(GroundedClaim(claim=claim, evidence_quote=quote))
    return out


def list_section_bodies(source_markdown: str) -> list[tuple[str, str, str]]:
    """Return [(heading, body, level_marker), ...] for H2–H6 sections."""
    md = source_markdown or ""
    matches = list(_HEADING_RE.finditer(md))
    sections: list[tuple[str, str, str]] = []
    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        # Only cut at same-or-higher level.
        level = len(m.group(1))
        body_end = end
        for j in range(i + 1, len(matches)):
            if len(matches[j].group(1)) <= level:
                body_end = matches[j].start()
                break
        else:
            body_end = len(md)
        body = md[start:body_end].strip("\n")
        sections.append((heading, body, m.group(1)))
    return sections


def _score_section_for_query(heading: str, body: str, query: str) -> float:
    q_tokens = _tokens(query)
    if not q_tokens:
        return 0.0
    blob = f"{heading}\n{body}".lower()
    hit = sum(1 for t in q_tokens if t in blob)
    dens = hit / max(len(q_tokens), 1)
    # Prefer sections with some prose but not empty.
    length_bonus = 0.2 if 40 <= len(body) <= 4000 else 0.0
    return dens + length_bonus


def select_section_for_query(
    source_markdown: str,
    *,
    query_text: str,
    h1: str | None = None,
) -> tuple[str, str] | None:
    """Pick best non-H1 section for rewrite; None if nothing suitable."""
    sections = list_section_bodies(source_markdown)
    scored: list[tuple[float, str, str]] = []
    h1_l = (h1 or "").strip().lower()
    for heading, body, _lvl in sections:
        if h1_l and heading.strip().lower() == h1_l:
            continue
        if not body.strip():
            continue
        # Skip FAQ/Steps promote targets — separate ops.
        if heading.strip().lower() in {"faq", "steps", "how to", "howto"}:
            continue
        score = _score_section_for_query(heading, body, query_text)
        if score <= 0:
            continue
        scored.append((score, heading, body))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], len(x[2])))
    _s, heading, body = scored[0]
    return heading, body


def _reject(
    *,
    op_kind: str,
    disposition: Disposition,
    reason: str,
    original: str | None = None,
    evidence: list[str] | None = None,
    target: str = "",
    warnings: list[str] | None = None,
    related_gap_ids: list[str] | None = None,
    related_query_ids: list[str] | None = None,
    query_text: str | None = None,
    apply_mode: str = "author_input_required",
    action: str = "rewrite",
    llm_used: bool = False,
) -> SynthResult:
    return SynthResult(
        op_kind=op_kind,
        disposition=disposition,
        proposed=None,
        claims=[],
        original=original,
        evidence=list(evidence or []),
        target=target,
        action=action,
        apply_mode=apply_mode,
        reason=reason,
        warnings=list(warnings or []),
        llm_used=llm_used,
        related_gap_ids=list(related_gap_ids or []),
        related_query_ids=list(related_query_ids or []),
        query_text=query_text,
    )


def _finalize_grounded(
    *,
    client: OpenAICompatibleChat,
    op_kind: str,
    proposed: str,
    claims: list[GroundedClaim],
    corpus: str,
    original: str | None,
    evidence: list[str],
    target: str,
    action: str,
    apply_mode: str,
    reason: str,
    related_gap_ids: list[str],
    related_query_ids: list[str],
    query_text: str | None,
) -> SynthResult:
    warnings: list[str] = []
    if not (proposed or "").strip():
        return _reject(
            op_kind=op_kind,
            disposition="author_input_required",
            reason="LLM returned empty proposed; author input required.",
            original=original,
            evidence=evidence,
            target=target,
            related_gap_ids=related_gap_ids,
            related_query_ids=related_query_ids,
            query_text=query_text,
            llm_used=True,
        )

    # Token-overlap prefilter only — never sufficient to accept.
    overlap = token_overlap_ratio(proposed, corpus)
    if overlap < MIN_TOKEN_OVERLAP_RATIO:
        warnings.append(f"token_overlap_prefilter:{overlap:.2f}")
        return _reject(
            op_kind=op_kind,
            disposition="author_input_required",
            reason=(
                "Proposed text failed token-overlap prefilter against on-page "
                "corpus; evidence exists but rewrite blocked."
            ),
            original=original,
            evidence=evidence,
            target=target,
            warnings=warnings,
            related_gap_ids=related_gap_ids,
            related_query_ids=related_query_ids,
            query_text=query_text,
            llm_used=True,
        )

    structural = validate_claims_against_corpus(
        claims, corpus=corpus, proposed=proposed
    )
    if structural:
        warnings.extend(structural)
        # Distinguish empty corpus quotes vs blocked evidence.
        if any("quote_not_verbatim" in e or "claims_empty" in e for e in structural):
            # If corpus itself is thin relative to query → research; else author.
            if len(_tokens(corpus)) < 12:
                disp: Disposition = "research_required"
                reason_r = (
                    "Corpus insufficient for grounded claims "
                    "(research_required); never invent."
                )
            else:
                disp = "author_input_required"
                reason_r = (
                    "Claim quote-lock / novelty validation failed; evidence "
                    "exists but blocked — author input required."
                )
        else:
            disp = "author_input_required"
            reason_r = (
                "Claim novelty or atomicity validation failed; "
                "author input required — never invent."
            )
        return _reject(
            op_kind=op_kind,
            disposition=disp,
            reason=reason_r,
            original=original,
            evidence=evidence,
            target=target,
            warnings=warnings,
            related_gap_ids=related_gap_ids,
            related_query_ids=related_query_ids,
            query_text=query_text,
            llm_used=True,
        )

    judgments = judge_entailment(client, claims, corpus=corpus)
    if any(label == "NOT_ENTAILED" for _, label in judgments):
        warnings.append("entailment_not_entailed")
        return _reject(
            op_kind=op_kind,
            disposition="author_input_required",
            reason=(
                "Entailment judge marked ≥1 claim NOT_ENTAILED; "
                "rejecting whole op — author input required."
            ),
            original=original,
            evidence=evidence,
            target=target,
            warnings=warnings,
            related_gap_ids=related_gap_ids,
            related_query_ids=related_query_ids,
            query_text=query_text,
            llm_used=True,
        )

    return SynthResult(
        op_kind=op_kind,
        disposition="actionable",
        proposed=proposed.strip(),
        claims=claims,
        original=original,
        evidence=evidence,
        target=target,
        target_kind="section",
        action=action,
        apply_mode=apply_mode,
        reason=reason,
        warnings=warnings,
        llm_used=True,
        related_gap_ids=related_gap_ids,
        related_query_ids=related_query_ids,
        query_text=query_text,
    )


def synthesize_rewrite_section(
    *,
    client: OpenAICompatibleChat | None,
    source_markdown: str,
    query_text: str,
    h1: str | None = None,
    related_gap_ids: list[str] | None = None,
    related_query_ids: list[str] | None = None,
    section_heading: str | None = None,
    section_body: str | None = None,
) -> SynthResult:
    """Primary op: grounded rewrite of a bounded section."""
    gap_ids = list(related_gap_ids or [])
    qids = list(related_query_ids or [])
    q = (query_text or "").strip()

    if client is None:
        return _reject(
            op_kind="rewrite_section",
            disposition="author_input_required",
            reason=(
                "rewrite_section requires draft_paid=true and API key "
                "(fail closed); author input required."
            ),
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
        )

    if section_heading and section_body is not None:
        heading, body = section_heading, section_body
    else:
        picked = select_section_for_query(
            source_markdown, query_text=q, h1=h1
        )
        if picked is None:
            return _reject(
                op_kind="rewrite_section",
                disposition="research_required",
                reason=(
                    "No on-page section corpus sufficient for grounded "
                    "rewrite_section (research_required)."
                ),
                related_gap_ids=gap_ids,
                related_query_ids=qids,
                query_text=q or None,
            )
        heading, body = picked

    if not (body or "").strip():
        return _reject(
            op_kind="rewrite_section",
            disposition="research_required",
            reason="Empty section body — corpus insufficient (research_required).",
            target=f"section:{heading}",
            original="",
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
        )

    corpus = f"{heading}\n{body}"
    evidence = [body.strip()[:500]] if body.strip() else []
    target = f"section:{heading}"

    user = (
        f"Query the section should answer better:\n{q}\n\n"
        f"Section heading:\n{heading}\n\n"
        f"Original section body (corpus — rewrite using only this):\n{body}\n\n"
        "Return JSON with keys:\n"
        '  "proposed": rewritten Markdown body (no heading line),\n'
        '  "claims": [{"claim": "...", "evidence_quote": "verbatim substring"}]\n'
        "Rules: every claim needs a verbatim evidence_quote from the corpus; "
        "do not add URLs/numbers/names absent from the corpus; keep NEW wording "
        "that is still entailed by the corpus."
    )
    try:
        raw = client.chat(
            [
                {"role": "system", "content": _SYNTH_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001
        return _reject(
            op_kind="rewrite_section",
            disposition="author_input_required",
            reason=f"LLM call failed ({type(exc).__name__}); author input required.",
            original=body,
            evidence=evidence,
            target=target,
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
            llm_used=False,
        )

    data = _parse_json_object(raw)
    if data is None:
        return _reject(
            op_kind="rewrite_section",
            disposition="author_input_required",
            reason="LLM returned non-JSON; author input required.",
            original=body,
            evidence=evidence,
            target=target,
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
            llm_used=True,
        )

    proposed = str(data.get("proposed") or "").strip()
    claims = _claims_from_payload(data)
    return _finalize_grounded(
        client=client,
        op_kind="rewrite_section",
        proposed=proposed,
        claims=claims,
        corpus=corpus,
        original=body,
        evidence=evidence,
        target=target,
        action="rewrite",
        apply_mode="replace_region",
        reason=(
            f"Grounded rewrite_section for query {q!r} using in-section evidence."
        ),
        related_gap_ids=gap_ids,
        related_query_ids=qids,
        query_text=q or None,
    )


def synthesize_add_explanation(
    *,
    client: OpenAICompatibleChat | None,
    source_markdown: str,
    query_text: str,
    anchor_heading: str,
    h1: str | None = None,
    related_gap_ids: list[str] | None = None,
    related_query_ids: list[str] | None = None,
) -> SynthResult:
    """Secondary op: insert clarifying prose after an anchor heading."""
    gap_ids = list(related_gap_ids or [])
    qids = list(related_query_ids or [])
    q = (query_text or "").strip()
    anchor = (anchor_heading or "").strip()
    target = f"section:{anchor}" if anchor else "section:unknown"

    if client is None:
        return _reject(
            op_kind="add_explanation",
            disposition="author_input_required",
            reason=(
                "add_explanation requires draft_paid=true and API key "
                "(fail closed); author input required."
            ),
            target=target,
            action="add",
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
        )

    if not anchor:
        return _reject(
            op_kind="add_explanation",
            disposition="research_required",
            reason="No anchor heading for add_explanation (research_required).",
            action="add",
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
        )

    # Corpus = whole page (evidence must be on-page) + anchor section body.
    sections = {h: b for h, b, _ in list_section_bodies(source_markdown)}
    section_body = sections.get(anchor, "")
    # Fuzzy match
    if not section_body:
        for h, b in sections.items():
            if anchor.lower() in h.lower() or h.lower() in anchor.lower():
                anchor = h
                section_body = b
                target = f"section:{anchor}"
                break

    corpus = source_markdown or ""
    if not corpus.strip() or len(_tokens(corpus)) < 12:
        return _reject(
            op_kind="add_explanation",
            disposition="research_required",
            reason="Page corpus insufficient for add_explanation (research_required).",
            target=target,
            action="add",
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
        )

    evidence = []
    if section_body.strip():
        evidence.append(section_body.strip()[:500])
    else:
        # Use nearby page excerpts as evidence pool.
        evidence.append(corpus.strip()[:500])

    user = (
        f"Query needing a clarifying explanation:\n{q}\n\n"
        f"Anchor heading (insert AFTER this heading):\n{anchor}\n\n"
        f"On-page corpus (only source of facts):\n{corpus[:8000]}\n\n"
        "Return JSON with keys:\n"
        '  "proposed": 1-3 short Markdown paragraphs to insert (no heading),\n'
        '  "claims": [{"claim": "...", "evidence_quote": "verbatim substring"}]\n'
        "Rules: every claim needs a verbatim evidence_quote from the corpus; "
        "do not invent URLs/numbers/names; only clarify what the page already says."
    )
    try:
        raw = client.chat(
            [
                {"role": "system", "content": _SYNTH_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001
        return _reject(
            op_kind="add_explanation",
            disposition="author_input_required",
            reason=f"LLM call failed ({type(exc).__name__}); author input required.",
            target=target,
            action="add",
            evidence=evidence,
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
        )

    data = _parse_json_object(raw)
    if data is None:
        return _reject(
            op_kind="add_explanation",
            disposition="author_input_required",
            reason="LLM returned non-JSON; author input required.",
            target=target,
            action="add",
            evidence=evidence,
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
            llm_used=True,
        )

    proposed = str(data.get("proposed") or "").strip()
    claims = _claims_from_payload(data)
    _ = h1  # reserved for intro-guard callers
    return _finalize_grounded(
        client=client,
        op_kind="add_explanation",
        proposed=proposed,
        claims=claims,
        corpus=corpus,
        original=None,
        evidence=evidence,
        target=target,
        action="add",
        apply_mode="insert_after",
        reason=(
            f"Grounded add_explanation after {anchor!r} for query {q!r}."
        ),
        related_gap_ids=gap_ids,
        related_query_ids=qids,
        query_text=q or None,
    )


def synth_result_to_change_fields(result: SynthResult) -> dict[str, Any]:
    """Map SynthResult onto SubstantiveChangeItem / edit-op fields."""
    status = result.status
    apply_mode = (
        result.apply_mode
        if result.disposition == "actionable"
        else "author_input_required"
    )
    return {
        "op_kind": result.op_kind,
        "disposition": result.disposition,
        "status": status,
        "apply_mode": apply_mode,
        "proposed_content": result.proposed,
        "proposed": result.proposed,
        "claims": [c.to_dict() for c in result.claims],
        "original": result.original,
        "evidence": list(result.evidence),
        "target": result.target,
        "target_kind": result.target_kind,
        "action": result.action,
        "reason": result.reason,
        "expected_aeo_benefit": result.expected_aeo_benefit,
        "related_gap_ids": list(result.related_gap_ids),
        "related_query_ids": list(result.related_query_ids),
        "query_text": result.query_text,
        "llm_used": result.llm_used,
        "warnings": list(result.warnings),
    }
