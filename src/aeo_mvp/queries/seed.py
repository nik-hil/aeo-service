"""Root / effective seed resolution (Phase 4).

Accepts aliases ``selection_seed``, ``query_selection_seed``, ``experiment_seed``.
Persists ``root_seed``, ``effective_seed``, and derivation metadata for audit.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

SEED_ALIASES = ("selection_seed", "query_selection_seed", "experiment_seed")
# Prefer explicit operator-facing name first, then Phase 3 key, then experiment alias.
SEED_ALIAS_PRIORITY = ("selection_seed", "query_selection_seed", "experiment_seed")


@dataclass
class SeedResolution:
    root_seed: int | str | None
    effective_seed: int
    source: str  # explicit | evidence_hash_fallback | default
    alias_used: str | None = None
    aliases_accepted: list[str] = field(default_factory=lambda: list(SEED_ALIASES))
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_seed(value: Any) -> int | str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s)
        return s
    return str(value)


def effective_seed_from_root(root: int | str | None, evidence_hash: str | None) -> tuple[int, str]:
    """Map root seed → canonical int used by RNG."""
    if root is None:
        raw = evidence_hash or "default"
        return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16), (
            "evidence_hash_fallback" if evidence_hash else "default"
        )
    if isinstance(root, int):
        return int(root), "explicit"
    # Stable int from string root
    return int(hashlib.sha256(str(root).encode()).hexdigest()[:8], 16), "explicit"


def resolve_seed_from_options(
    options: dict[str, Any] | None,
    *,
    evidence_hash: str | None = None,
    explicit: int | str | None = None,
) -> SeedResolution:
    """Resolve seed from options dict and/or explicit kwarg.

    Priority: ``explicit`` kwarg → first present alias in SEED_ALIAS_PRIORITY →
    evidence_hash fallback.
    """
    opts = options or {}
    warnings: list[str] = []
    alias_used: str | None = None
    root: int | str | None = _coerce_seed(explicit) if explicit is not None else None

    if root is None:
        for key in SEED_ALIAS_PRIORITY:
            if key in opts and opts[key] is not None and opts[key] != "":
                root = _coerce_seed(opts[key])
                alias_used = key
                break

    # Warn if unknown-looking seed keys present but no alias matched
    if root is None:
        for k in opts:
            if "seed" in str(k).lower() and k not in SEED_ALIASES:
                warnings.append(f"SEED_ALIAS_MISMATCH:{k}")

    effective, source = effective_seed_from_root(root, evidence_hash)
    if root is not None and source == "explicit":
        # When root was an int, source stays explicit; string roots also explicit.
        pass
    elif root is None:
        source = "evidence_hash_fallback" if evidence_hash else "default"

    return SeedResolution(
        root_seed=root,
        effective_seed=effective,
        source=source if root is not None else (
            "evidence_hash_fallback" if evidence_hash else "default"
        ),
        alias_used=alias_used,
        warnings=warnings,
    )


def resolve_seed(
    *,
    selection_seed: int | str | None = None,
    options: dict[str, Any] | None = None,
    evidence_hash: str | None = None,
) -> SeedResolution:
    """Convenience wrapper used by discovery / select."""
    return resolve_seed_from_options(
        options,
        evidence_hash=evidence_hash,
        explicit=selection_seed,
    )
