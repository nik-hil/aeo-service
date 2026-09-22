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

import hashlib
import json
import logging
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import httpx

from aeo_mvp.config import get_settings
from aeo_mvp.content.md_sections import list_section_bodies as _shared_list_section_bodies

logger = logging.getLogger(__name__)

Disposition = Literal["actionable", "author_input_required", "research_required"]
EntailmentLabel = Literal["ENTAILED", "NOT_ENTAILED"]

ChatFn = Callable[[list[dict[str, str]], float], str]

_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
_PROPER_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-]{2,}")

# Query tokens that carry no topical signal for section selection.
_QUERY_STOPWORDS = frozenset(
    {
        "what", "the", "and", "for", "how", "why", "does", "are", "with", "this",
        "that", "from", "into", "when", "where", "which", "who", "can", "you",
        "your", "there", "here", "about", "explain", "describe", "mean", "means",
        "work", "works", "use", "used", "using",
    }
)

_SYNTH_SYSTEM = (
    "You rewrite or clarify web article Markdown using ONLY the provided "
    "corpus evidence. Never invent URLs, numbers, product names, citations, "
    "or facts absent from the corpus. Respond with a single JSON object only."
)
# Bump when system/user prompt contract for rewrite_section changes.
SYNTH_PROMPT_VERSION = "grounded_rewrite_section_v1"

_ENTAIL_SYSTEM = (
    "You are an entailment judge. Given a claim and evidence quotes from a "
    "source page, reply with exactly one token: ENTAILED or NOT_ENTAILED."
)

# Prefer quality: at most this many grounded body ops per plan pass.
MAX_GROUNDED_BODY_OPS = 2
# Soft token-overlap prefilter (never sufficient alone for accept).
MIN_TOKEN_OVERLAP_RATIO = 0.35
# rewrite_section must stay local: refuse to hand the LLM a "section" larger
# than this (chars). Oversized spans mean the section boundary is wrong or the
# section is really a whole article — never summarise that under one heading.
MAX_REWRITE_SECTION_CORPUS_CHARS = 4000
# Defense-in-depth: proposed must stay within this multiple of the *actual*
# selected section body (not a mis-bounded mega-corpus).
MAX_PROPOSED_TO_BODY_RATIO = 2.0
# Size band that earns a small selection bonus (readable, locally rewritable).
PREFERRED_SECTION_MIN_CHARS = 40
PREFERRED_SECTION_MAX_CHARS = 2500
# Deterministic synth: same corpus + query ⇒ same candidate across jobs
# (HTML twin and .md twin of one Hashnode article share one proposal).
SYNTH_TEMPERATURE = 0.0


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


# Process-local memo: hash(source, heading, query)+model+prompt_version → result.
_REWRITE_MEMO: dict[str, "SynthResult"] = {}


def clear_rewrite_memo() -> None:
    """Test helper: drop process-local rewrite_section memo entries."""
    _REWRITE_MEMO.clear()


def _rewrite_memo_key(
    *,
    source_markdown: str,
    heading: str,
    query_text: str,
    model: str | None,
) -> str:
    payload = "\0".join(
        [
            SYNTH_PROMPT_VERSION,
            (model or "").strip(),
            (heading or "").strip().lower(),
            (query_text or "").strip(),
            source_markdown or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _collapse_ws(text: str) -> str:
    """Collapse whitespace runs to a single space (for containment checks only)."""
    return re.sub(r"\s+", " ", (text or "").strip())


def find_ws_canonical_corpus_span(quote: str, corpus: str) -> str | None:
    """Return an exact corpus substring that matches quote under WS-canonical rules.

    Exact substring wins. Otherwise non-whitespace character sequences must match
    contiguously in corpus order (whitespace may differ). No paraphrase / fuzzy /
    edit-distance. Returns None when no such span exists (fail closed).
    """
    q = (quote or "").strip()
    c = corpus or ""
    if not q or len(q) < 8 or not c:
        return None
    if q in c:
        return q
    # Collapsed containment prefilter (not sufficient alone).
    cq = _collapse_ws(q)
    if len(cq) < 8 or cq not in _collapse_ws(c):
        return None
    q_chars = [ch for ch in q if not ch.isspace()]
    if len(q_chars) < 8:
        return None
    c_idx = [(i, ch) for i, ch in enumerate(c) if not ch.isspace()]
    n = len(q_chars)
    if n > len(c_idx):
        return None
    for start in range(len(c_idx) - n + 1):
        window = c_idx[start : start + n]
        if [ch for _, ch in window] == q_chars:
            lo = window[0][0]
            hi = window[-1][0]
            span = c[lo : hi + 1]
            # Span must be a real contiguous slice of the original corpus.
            if span and span in c:
                return span
    return None


def quote_is_verbatim(quote: str, corpus: str) -> bool:
    """True when quote is an exact or whitespace-canonical contiguous corpus span."""
    return find_ws_canonical_corpus_span(quote, corpus) is not None


def repair_claim_evidence_quotes(
    claims: list[GroundedClaim],
    *,
    corpus: str,
) -> tuple[list[GroundedClaim], list[str]]:
    """Fail-closed WS repair: remap quotes to exact corpus spans when WS-canonical.

    Never invents quotes. Unrepairable quotes are left unchanged for validation reject.
    """
    out: list[GroundedClaim] = []
    warnings: list[str] = []
    for i, cl in enumerate(claims):
        raw_q = (cl.evidence_quote or "").strip()
        span = find_ws_canonical_corpus_span(raw_q, corpus)
        if span is None:
            out.append(cl)
            continue
        if span != raw_q:
            warnings.append(f"claim_{i}_evidence_quote_ws_repaired")
            out.append(GroundedClaim(claim=cl.claim, evidence_quote=span))
        else:
            out.append(GroundedClaim(claim=cl.claim, evidence_quote=span))
    return out, warnings


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


def _llm_repair_quotes_once(
    client: OpenAICompatibleChat,
    *,
    claims: list[GroundedClaim],
    corpus: str,
    proposed: str,
    errors: list[str],
) -> tuple[list[GroundedClaim] | None, list[str]]:
    """One fail-closed LLM attempt to rematerialize evidence_quote from corpus.

    Returns (repaired_claims, warnings). On any failure → (None, warnings) and
    caller keeps author_input. Never invents facts outside corpus; output still
    must pass full validate + entailment.
    """
    warnings: list[str] = ["llm_quote_repair_attempted"]
    bad = [e for e in errors if "quote_not_verbatim" in e]
    if not bad:
        return None, warnings
    user = (
        "Fix evidence_quote fields so each is an EXACT contiguous substring of the "
        "corpus (whitespace differences only are allowed to be normalized to the "
        "corpus spelling). Do not invent facts, URLs, numbers, or names.\n\n"
        f"Corpus:\n{corpus[:8000]}\n\n"
        f"Proposed (unchanged):\n{proposed}\n\n"
        f"Claims JSON:\n{json.dumps([c.to_dict() for c in claims])}\n\n"
        f"Validation errors:\n{json.dumps(errors)}\n\n"
        'Return JSON: {"claims":[{"claim":"...","evidence_quote":"..."}]}'
    )
    try:
        raw = client.chat(
            [
                {"role": "system", "content": _SYNTH_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"llm_quote_repair_failed:{type(exc).__name__}")
        return None, warnings
    data = _parse_json_object(raw)
    if data is None:
        warnings.append("llm_quote_repair_non_json")
        return None, warnings
    repaired = _claims_from_payload(data)
    if not repaired:
        warnings.append("llm_quote_repair_empty_claims")
        return None, warnings
    warnings.append("llm_quote_repair_applied")
    return repaired, warnings


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
    """Return [(heading, body, level_marker), ...] for every ATX section (H1–H6).

    Delegates to the shared fence-aware parser also used by the Hashnode
    Markdown generator's ``_find_section_span``, so the corpus the LLM rewrites
    is exactly the span that will be swapped in.
    """
    return _shared_list_section_bodies(source_markdown)


def _query_tokens(query: str) -> set[str]:
    """Topical tokens of a query (stopwords removed; falls back to all tokens)."""
    all_tokens = _tokens(query)
    topical = {t for t in all_tokens if t not in _QUERY_STOPWORDS}
    return topical or all_tokens


def _score_section_for_query(heading: str, body: str, query: str) -> float:
    """Heading-weighted locality score.

    Heading overlap counts double: a query glossed from a heading ("What is
    The complete flow?") must land on *that* section, not on whichever body
    happens to contain the most common words. Oversized bodies are penalised
    so a mis-bounded mega-section can never win on vocabulary coverage alone.
    """
    q_tokens = _query_tokens(query)
    if not q_tokens:
        return 0.0
    h_tokens = _tokens(heading)
    b_tokens = _tokens(body)
    heading_hit = len(q_tokens & h_tokens) / len(q_tokens)
    body_hit = len(q_tokens & b_tokens) / len(q_tokens)
    n = len(body)
    if PREFERRED_SECTION_MIN_CHARS <= n <= PREFERRED_SECTION_MAX_CHARS:
        size_adj = 0.1
    elif n > MAX_REWRITE_SECTION_CORPUS_CHARS:
        size_adj = -0.5
    else:
        size_adj = 0.0
    return 2.0 * heading_hit + body_hit + size_adj


def select_section_for_query(
    source_markdown: str,
    *,
    query_text: str,
    h1: str | None = None,
    exclude_headings: set[str] | frozenset[str] | None = None,
) -> tuple[str, str] | None:
    """Pick the best local section for a grounded rewrite; None if none suitable.

    Skips: the article H1 / intro (by title *and* by position), empty bodies,
    FAQ/Steps promote targets, headings already targeted in this plan
    (``exclude_headings``), and bodies larger than
    ``MAX_REWRITE_SECTION_CORPUS_CHARS`` (not locally rewritable).
    """
    sections = list_section_bodies(source_markdown)
    scored: list[tuple[float, str, str]] = []
    h1_l = (h1 or "").strip().lower()
    excluded = {str(x).strip().lower() for x in (exclude_headings or set()) if x}
    for idx, (heading, body, lvl) in enumerate(sections):
        h_l = heading.strip().lower()
        if idx == 0 and lvl == "#":
            # Leading H1 = article title / introduction (PR #44 owns intro).
            continue
        if h1_l and h_l == h1_l:
            continue
        if h_l in excluded:
            continue
        if not body.strip():
            continue
        if len(body) > MAX_REWRITE_SECTION_CORPUS_CHARS:
            continue
        # Skip FAQ/Steps promote targets — separate ops.
        if h_l in {"faq", "steps", "how to", "howto"}:
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

    # Defense-in-depth size guard vs the *actual* selected section body.
    body_chars = len((original or "").strip())
    prop_chars = len(proposed.strip())
    if (
        op_kind == "rewrite_section"
        and body_chars > 0
        and prop_chars > MAX_PROPOSED_TO_BODY_RATIO * body_chars
    ):
        warnings.append(
            f"proposed_to_body_ratio:{prop_chars}:{body_chars}"
        )
        return _reject(
            op_kind=op_kind,
            disposition="author_input_required",
            reason=(
                f"Proposed rewrite is {prop_chars} chars vs actual section body "
                f"{body_chars} chars (>{MAX_PROPOSED_TO_BODY_RATIO}x); refuse — "
                "likely mega-corpus dump into a local heading."
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

    # Fail-closed WS quote repair before structural validate (never invents).
    claims, repair_warns = repair_claim_evidence_quotes(claims, corpus=corpus)
    warnings.extend(repair_warns)

    structural = validate_claims_against_corpus(
        claims, corpus=corpus, proposed=proposed
    )
    if structural and any("quote_not_verbatim" in e for e in structural):
        # Optional one repair LLM call for quote_not_verbatim only (fail closed).
        non_quote = [
            e
            for e in structural
            if "quote_not_verbatim" not in e and e != "claims_empty"
        ]
        if not non_quote:
            repaired_claims, llm_repair_warns = _llm_repair_quotes_once(
                client,
                claims=claims,
                corpus=corpus,
                proposed=proposed,
                errors=structural,
            )
            warnings.extend(llm_repair_warns)
            if repaired_claims is not None:
                claims, ws_warns = repair_claim_evidence_quotes(
                    repaired_claims, corpus=corpus
                )
                warnings.extend(ws_warns)
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

    # Locality guard: a rewrite_section corpus must be a bounded section, not
    # half the article. Fail closed before spending an LLM call.
    if len(body) > MAX_REWRITE_SECTION_CORPUS_CHARS:
        return _reject(
            op_kind="rewrite_section",
            disposition="author_input_required",
            reason=(
                f"Section body is {len(body)} chars (> "
                f"{MAX_REWRITE_SECTION_CORPUS_CHARS}); not locally rewritable "
                "without summarising downstream sections — author input required."
            ),
            original=body,
            evidence=evidence,
            target=target,
            warnings=[f"rewrite_section_corpus_oversized:{len(body)}"],
            related_gap_ids=gap_ids,
            related_query_ids=qids,
            query_text=q or None,
            llm_used=False,
        )

    memo_key = _rewrite_memo_key(
        source_markdown=source_markdown,
        heading=heading,
        query_text=q,
        model=getattr(client, "model", None),
    )
    cached = _REWRITE_MEMO.get(memo_key)
    if cached is not None:
        hit = deepcopy(cached)
        hit.related_gap_ids = gap_ids
        hit.related_query_ids = qids
        hit.query_text = q or None
        hit.target = target
        if "rewrite_section_memo_hit" not in hit.warnings:
            hit.warnings = list(hit.warnings) + ["rewrite_section_memo_hit"]
        return hit

    user = (
        f"Query the section should answer better:\n{q}\n\n"
        f"Section heading:\n{heading}\n\n"
        f"Original section body (corpus — rewrite using only this):\n{body}\n\n"
        "Return JSON with keys:\n"
        '  "proposed": rewritten Markdown body (no heading line),\n'
        '  "claims": [{"claim": "...", "evidence_quote": "verbatim substring"}]\n'
        "Rules: every claim needs a verbatim evidence_quote from the corpus; "
        "do not add URLs/numbers/names absent from the corpus; keep NEW wording "
        "that is still entailed by the corpus; preserve the section's structure "
        "(keep bullet/numbered lists as lists, keep code blocks verbatim); stay "
        "focused on this section only."
    )
    try:
        raw = client.chat(
            [
                {"role": "system", "content": _SYNTH_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=SYNTH_TEMPERATURE,
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
    result = _finalize_grounded(
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
    # Memoize only validated actionable proposals (deterministic reuse).
    if result.disposition == "actionable" and result.proposed:
        _REWRITE_MEMO[memo_key] = deepcopy(result)
    return result


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
            temperature=SYNTH_TEMPERATURE,
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
