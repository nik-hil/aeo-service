"""Fail-closed HTTP API authentication (shared bearer secret).

Protects every network-exposed route except an explicit public allowlist
(health/readiness for load-balancer probes). No RBAC — authentication only.
"""

from __future__ import annotations

import logging
import secrets
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from aeo_mvp.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Exact paths (trailing slashes normalized) that may be called without credentials.
PUBLIC_PATHS: Final[frozenset[str]] = frozenset({"/health"})
# GET for LB probes; HEAD allowed through auth so probe clients are not 401'd.
PUBLIC_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD"})

# Environments where AEO_ALLOW_UNAUTHENTICATED=true is honored.
# Default AEO_ENVIRONMENT is "production", so bypass cannot happen accidentally.
_BYPASS_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {"development", "dev", "test", "local"}
)


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def is_public_route(method: str, path: str) -> bool:
    return (
        normalize_path(path) in PUBLIC_PATHS
        and method.upper() in PUBLIC_METHODS
    )


def auth_bypass_allowed(settings: Settings) -> bool:
    """Explicit local/dev/test opt-in only; ignored in production / unknown envs."""
    if not settings.allow_unauthenticated:
        return False
    env = (settings.environment or "").strip().lower()
    if env in _BYPASS_ENVIRONMENTS:
        return True
    logger.warning(
        "AEO_ALLOW_UNAUTHENTICATED ignored: AEO_ENVIRONMENT is not a "
        "local/dev/test value (fail-closed)"
    )
    return False


def configured_api_key(settings: Settings) -> str | None:
    key = settings.api_key
    if key is None:
        return None
    if not isinstance(key, str):
        return None
    key = key.strip()
    return key or None


def parse_bearer_token(authorization: str | None) -> str | None:
    """Return bearer token, or None if missing/malformed.

    Never log ``authorization`` or the returned token.
    """
    if authorization is None or not isinstance(authorization, str):
        return None
    if "\r" in authorization or "\n" in authorization:
        return None
    scheme, sep, param = authorization.partition(" ")
    if sep != " " or not scheme or not param:
        return None
    if scheme.lower() != "bearer":
        return None
    if not param or any(c.isspace() for c in param):
        return None
    return param


def credentials_match(provided: str, expected: str) -> bool:
    return secrets.compare_digest(
        provided.encode("utf-8"),
        expected.encode("utf-8"),
    )


def unauthorized_response() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Unauthorized"},
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_request_authorized(request: Request, settings: Settings | None = None) -> bool:
    """Return True if the request may proceed."""
    if is_public_route(request.method, request.url.path):
        return True
    cfg = settings if settings is not None else get_settings()
    if auth_bypass_allowed(cfg):
        return True
    expected = configured_api_key(cfg)
    if expected is None:
        # Missing production credentials must not silently disable auth.
        return False
    token = parse_bearer_token(request.headers.get("Authorization"))
    if token is None:
        return False
    return credentials_match(token, expected)


class ApiAuthMiddleware(BaseHTTPMiddleware):
    """Central fail-closed auth for all routes except the public allowlist."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if verify_request_authorized(request):
            return await call_next(request)
        return unauthorized_response()
