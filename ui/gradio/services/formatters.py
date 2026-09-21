"""KPI and display formatters — no scoring logic."""

from __future__ import annotations

from typing import Any


def score_value(obj: Any) -> float | None:
    if obj is None:
        return None
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, dict):
        v = obj.get("value")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return None


def format_score(obj: Any, *, digits: int = 1, empty: str = "—") -> str:
    v = score_value(obj)
    if v is None:
        return empty
    return f"{v:.{digits}f}"


def format_pct_rate(obj: Any, *, digits: int = 0, empty: str = "—") -> str:
    """Format a 0–1 rate (or metric object) as a percentage string."""
    v = score_value(obj)
    if v is None:
        return empty
    if v <= 1.0:
        v = v * 100.0
    return f"{v:.{digits}f}%"


def format_provenance(obj: Any, empty: str = "—") -> str:
    if not isinstance(obj, dict):
        return empty
    p = obj.get("provenance")
    return str(p) if p else empty


def health_label(score: float | None) -> str:
    if score is None:
        return "Unavailable"
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Moderate"
    if score >= 40:
        return "Needs work"
    return "Weak"


def severity_rank(severity: str | None) -> int:
    s = (severity or "").lower()
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return order.get(s, 99)


def effort_label(effort: str | None) -> str:
    e = (effort or "").upper()
    return e if e in {"S", "M", "L"} else (effort or "—")
