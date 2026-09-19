"""P0-3: fail-closed API authentication.

Isolates auth config via Settings(_env_file=None) — same pattern as P0-1.
No external network calls.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aeo_mvp.config import get_settings
from aeo_mvp.db.session import init_db, reset_engine
from aeo_mvp.security.api_auth import (
    PUBLIC_PATHS,
    credentials_match,
    is_public_route,
    normalize_path,
    parse_bearer_token,
)
from tests.conftest import TEST_API_KEY, _install_isolated_settings

DUMMY_JOB = "00000000-0000-0000-0000-000000000000"

# Canonical inventory — new protected routes must be added here (and implemented
# behind ApiAuthMiddleware) or classification tests fail.
EXPECTED_PUBLIC: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/health"),
    }
)

EXPECTED_PROTECTED: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/jobs"),
        ("GET", "/api/v1/jobs/{job_id}"),
        ("GET", "/api/v1/jobs/{job_id}/report"),
        ("GET", "/api/v1/jobs/{job_id}/pages"),
        ("POST", "/api/v1/content-optimization"),
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("GET", "/redoc"),
    }
)

# Concrete requests used to exercise every protected application route.
PROTECTED_PROBE_REQUESTS: list[tuple[str, str, dict[str, Any] | None]] = [
    (
        "POST",
        "/api/v1/jobs",
        {"url": "https://demo.example/", "demo_mode": True, "options": {"provider": "demo"}},
    ),
    ("GET", f"/api/v1/jobs/{DUMMY_JOB}", None),
    ("GET", f"/api/v1/jobs/{DUMMY_JOB}/report", None),
    ("GET", f"/api/v1/jobs/{DUMMY_JOB}/pages", None),
    (
        "POST",
        "/api/v1/content-optimization",
        {"html": "<html><body><h1>t</h1><p>x</p></body></html>", "url": "https://demo.example/"},
    ),
    ("GET", "/openapi.json", None),
    ("GET", "/docs", None),
    ("GET", "/redoc", None),
]


def _walk_routes(app) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()

    def walk(routes) -> None:
        for r in routes:
            path = getattr(r, "path", None)
            methods = getattr(r, "methods", None)
            if path and methods:
                norm = normalize_path(path)
                for m in methods:
                    if m in {"HEAD", "OPTIONS"} and norm not in PUBLIC_PATHS:
                        # FastAPI adds HEAD for GET; classify GET routes only in inventory
                        # except public health HEAD.
                        if m == "HEAD" and not is_public_route("HEAD", norm):
                            continue
                    if m == "OPTIONS":
                        continue
                    found.add((m, norm))
            nested = getattr(r, "routes", None)
            if nested:
                walk(nested)
            original = getattr(r, "original_router", None)
            if original is not None:
                walk(original.routes)

    walk(app.routes)
    return found


def _auth_client(tmp_path, monkeypatch, settings_kwargs: dict[str, Any]) -> TestClient:
    db_path = tmp_path / "auth.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("AEO_DATABASE_URL", url)
    reset_engine()
    kwargs = {
        "AEO_DATABASE_URL": url,
        "AEO_ALLOW_UNAUTHENTICATED": False,
        "AEO_ENVIRONMENT": "test",
        **settings_kwargs,
    }
    _install_isolated_settings(monkeypatch, **kwargs)
    init_db(url)
    from aeo_mvp.api.app import create_app

    return TestClient(create_app())


def _assert_unauthorized(response) -> None:
    assert response.status_code == 401
    body = response.json()
    assert body == {"detail": "Unauthorized"}
    blob = response.text.lower()
    assert TEST_API_KEY.lower() not in blob
    assert "traceback" not in blob
    assert "secret" not in blob


@pytest.fixture()
def authed_client(tmp_path, monkeypatch):
    client = _auth_client(
        tmp_path,
        monkeypatch,
        {"AEO_API_KEY": TEST_API_KEY, "AEO_ENVIRONMENT": "test"},
    )
    with client:
        yield client
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def bare_client(tmp_path, monkeypatch):
    """Client with API key configured but no default Authorization header."""
    client = _auth_client(
        tmp_path,
        monkeypatch,
        {"AEO_API_KEY": TEST_API_KEY, "AEO_ENVIRONMENT": "test"},
    )
    with client:
        yield client
    reset_engine()
    get_settings.cache_clear()


def test_route_inventory_classification():
    from aeo_mvp.api.app import create_app

    app = create_app()
    discovered = _walk_routes(app)
    public = {(m, p) for m, p in discovered if is_public_route(m, p)}
    protected_paths = {
        (m, p)
        for m, p in discovered
        if not is_public_route(m, p) and m in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    assert public == EXPECTED_PUBLIC
    # Parameterized inventory: every discovered app/docs route must be listed.
    assert protected_paths == EXPECTED_PROTECTED, (
        f"Route inventory drift. New routes must be classified in "
        f"EXPECTED_PUBLIC / EXPECTED_PROTECTED / docs/security/API_AUTH.md. "
        f"extra={protected_paths - EXPECTED_PROTECTED} "
        f"missing={EXPECTED_PROTECTED - protected_paths}"
    )


@pytest.mark.parametrize("method,path,json_body", PROTECTED_PROBE_REQUESTS)
def test_protected_without_credentials_401(bare_client, method, path, json_body):
    r = bare_client.request(method, path, json=json_body)
    _assert_unauthorized(r)


@pytest.mark.parametrize("method,path,json_body", PROTECTED_PROBE_REQUESTS)
def test_protected_invalid_credentials_401(bare_client, method, path, json_body):
    r = bare_client.request(
        method,
        path,
        json=json_body,
        headers={"Authorization": "Bearer wrong-key-not-real"},
    )
    _assert_unauthorized(r)


@pytest.mark.parametrize("method,path,json_body", PROTECTED_PROBE_REQUESTS)
def test_protected_valid_credentials_not_401(bare_client, method, path, json_body):
    r = bare_client.request(
        method,
        path,
        json=json_body,
        headers={"Authorization": f"Bearer {TEST_API_KEY}"},
    )
    assert r.status_code != 401
    assert TEST_API_KEY not in r.text


def test_missing_authorization_header_401(bare_client):
    r = bare_client.post(
        "/api/v1/jobs",
        json={"url": "https://demo.example/", "demo_mode": True},
    )
    _assert_unauthorized(r)


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Bearer",
        "Bearer ",
        "bearer",
        "Basic dXNlcjpwYXNz",
        "Bearer token with spaces",
        "Token " + TEST_API_KEY,
        "Bearer\t" + TEST_API_KEY,
        "Bearer " + TEST_API_KEY + " ",
    ],
)
def test_malformed_authorization_401(bare_client, header):
    r = bare_client.get(
        f"/api/v1/jobs/{DUMMY_JOB}",
        headers={"Authorization": header},
    )
    _assert_unauthorized(r)


def test_query_param_api_key_does_not_authenticate(bare_client):
    r = bare_client.get(
        f"/api/v1/jobs/{DUMMY_JOB}",
        params={"api_key": TEST_API_KEY, "authorization": f"Bearer {TEST_API_KEY}"},
    )
    _assert_unauthorized(r)


def test_trailing_slash_still_requires_auth(bare_client):
    r = bare_client.post(
        "/api/v1/jobs/",
        json={"url": "https://demo.example/", "demo_mode": True},
    )
    # Middleware rejects before slash-redirect can become an unauthenticated alias.
    _assert_unauthorized(r)


def test_health_public_minimal(bare_client):
    r = bare_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "job" not in r.text.lower()
    assert "report" not in r.text.lower()


def test_health_head_not_rejected_by_auth(bare_client):
    """Auth allowlists HEAD /health; framework may still return 405 if no HEAD route."""
    r = bare_client.head("/health")
    assert r.status_code != 401
    assert TEST_API_KEY not in r.text


def test_health_trailing_slash_public(bare_client):
    r = bare_client.get("/health/")
    # Either normalized public allow or redirect; must not expose data or require auth.
    assert r.status_code in (200, 307, 308)
    if r.status_code == 200:
        assert r.json() == {"status": "ok"}


def test_no_unauthenticated_job_data_exposure(bare_client):
    for method, path, json_body in PROTECTED_PROBE_REQUESTS:
        if "/jobs" not in path and "content-optimization" not in path:
            continue
        r = bare_client.request(method, path, json=json_body)
        _assert_unauthorized(r)
        assert "base_url" not in r.text
        assert "health_score" not in r.text
        assert "recommendations" not in r.text


def test_missing_auth_config_fails_closed(tmp_path, monkeypatch):
    client = _auth_client(
        tmp_path,
        monkeypatch,
        {"AEO_API_KEY": None, "AEO_ENVIRONMENT": "production"},
    )
    with client:
        r = client.get(
            f"/api/v1/jobs/{DUMMY_JOB}",
            headers={"Authorization": f"Bearer {TEST_API_KEY}"},
        )
        _assert_unauthorized(r)
        # Health still public
        h = client.get("/health")
        assert h.status_code == 200
        assert h.json() == {"status": "ok"}
    reset_engine()
    get_settings.cache_clear()


def test_blank_api_key_fails_closed(tmp_path, monkeypatch):
    client = _auth_client(
        tmp_path,
        monkeypatch,
        {"AEO_API_KEY": "   ", "AEO_ENVIRONMENT": "production"},
    )
    with client:
        r = client.post(
            "/api/v1/jobs",
            json={"url": "https://demo.example/", "demo_mode": True},
            headers={"Authorization": "Bearer    "},
        )
        _assert_unauthorized(r)
    reset_engine()
    get_settings.cache_clear()


def test_bypass_ignored_in_production(tmp_path, monkeypatch):
    client = _auth_client(
        tmp_path,
        monkeypatch,
        {
            "AEO_API_KEY": TEST_API_KEY,
            "AEO_ALLOW_UNAUTHENTICATED": True,
            "AEO_ENVIRONMENT": "production",
        },
    )
    with client:
        r = client.get(f"/api/v1/jobs/{DUMMY_JOB}")
        _assert_unauthorized(r)
    reset_engine()
    get_settings.cache_clear()


def test_explicit_bypass_only_in_local_env(tmp_path, monkeypatch):
    client = _auth_client(
        tmp_path,
        monkeypatch,
        {
            "AEO_API_KEY": None,
            "AEO_ALLOW_UNAUTHENTICATED": True,
            "AEO_ENVIRONMENT": "development",
        },
    )
    with client:
        r = client.get(f"/api/v1/jobs/{DUMMY_JOB}")
        # Bypass allows the request through; unknown job → 404, not 401
        assert r.status_code == 404
    reset_engine()
    get_settings.cache_clear()


def test_credentials_never_in_logs_on_failure(bare_client, caplog):
    secret = "super-secret-api-key-should-not-log"
    with caplog.at_level(logging.DEBUG):
        r = bare_client.get(
            f"/api/v1/jobs/{DUMMY_JOB}",
            headers={"Authorization": f"Bearer {secret}"},
        )
    _assert_unauthorized(r)
    combined = "\n".join(r.message for r in caplog.records) + caplog.text
    assert secret not in combined
    assert "Authorization" not in combined


def test_valid_auth_preserves_create_job_behavior(client):
    """Existing authenticated behavior unchanged (uses shared client fixture)."""
    r = client.post(
        "/api/v1/jobs",
        json={
            "url": "https://demo.example/",
            "demo_mode": True,
            "options": {"provider": "demo", "runs_per_prompt": 3},
        },
    )
    assert r.status_code == 202
    assert "id" in r.json()
    assert TEST_API_KEY not in r.text


def test_parse_bearer_and_compare_helpers():
    assert parse_bearer_token(None) is None
    assert parse_bearer_token("Bearer") is None
    assert parse_bearer_token(f"Bearer {TEST_API_KEY}") == TEST_API_KEY
    assert parse_bearer_token(f"bearer {TEST_API_KEY}") == TEST_API_KEY
    assert credentials_match(TEST_API_KEY, TEST_API_KEY) is True
    assert credentials_match("a", "b") is False


def test_public_paths_constant():
    assert PUBLIC_PATHS == frozenset({"/health"})
