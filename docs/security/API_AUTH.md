# API Authentication (P0-3)

**Module:** `aeo_mvp.security.api_auth`  
**Date:** 2026-09-19

## Goal

Fail-closed authentication for every network-exposed endpoint that can create,
execute, inspect, retrieve, or mutate AEO jobs/data. Auth only — no RBAC.

## Endpoint inventory

| Method | Path | Class | Notes |
| --- | --- | --- | --- |
| `GET`/`HEAD` | `/health` | **Public** | LB liveness; body `{"status":"ok"}` only — no job/data |
| `POST` | `/api/v1/jobs` | **Protected** | Create + schedule pipeline |
| `GET` | `/api/v1/jobs/{job_id}` | **Protected** | Job status / scores |
| `GET` | `/api/v1/jobs/{job_id}/report` | **Protected** | Full report JSON |
| `GET` | `/api/v1/jobs/{job_id}/pages` | **Protected** | Crawled pages |
| `POST` | `/api/v1/content-optimization` | **Protected** | Page optimization |
| `GET`/`HEAD` | `/openapi.json` | **Protected** | FastAPI schema |
| `GET`/`HEAD` | `/docs` | **Protected** | Swagger UI |
| `GET`/`HEAD` | `/docs/oauth2-redirect` | **Protected** | Swagger OAuth redirect |
| `GET`/`HEAD` | `/redoc` | **Protected** | ReDoc UI |

No other application routes are registered.

## Mechanism

Central Starlette/FastAPI middleware (`ApiAuthMiddleware`) runs **before**
routing for every request (covers trailing-slash aliases and docs routes).

- Credential: `Authorization: Bearer <AEO_API_KEY>`
- Comparison: `secrets.compare_digest` (constant-time)
- Failure: HTTP `401` with `{"detail":"Unauthorized"}` and `WWW-Authenticate: Bearer`
- Responses and application logs never include the API key / Authorization value

## Config / env

| Variable | Default | Meaning |
| --- | --- | --- |
| `AEO_API_KEY` | unset | Shared bearer secret. **Required** for protected routes to succeed |
| `AEO_ENVIRONMENT` | `production` | Deployment mode |
| `AEO_ALLOW_UNAUTHENTICATED` | `false` | Explicit local bypass — **only** honored when `AEO_ENVIRONMENT` is `development`, `dev`, `test`, or `local` |

## Fail-closed behavior

- Missing / blank `AEO_API_KEY` → all protected routes return **401** (auth is not disabled)
- Invalid, missing, or malformed `Authorization` → **401**
- Query-param / body / alternate header credentials are **not** accepted
- `AEO_ALLOW_UNAUTHENTICATED=true` in production (or any non-bypass environment) is **ignored**
- There is no hidden default API key

## Health / readiness

`GET /health` remains public so load balancers can probe without storing the
API key. The response is minimal (`status` only) and never includes job or
site data.
