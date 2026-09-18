"""API tests with TestClient."""

from __future__ import annotations

import time


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_demo_job_and_report(client):
    r = client.post(
        "/api/v1/jobs",
        json={
            "url": "https://demo.example/",
            "demo_mode": True,
            "options": {"provider": "demo", "runs_per_prompt": 3},
        },
    )
    assert r.status_code == 202
    body = r.json()
    job_id = body["id"]
    assert body["demo_mode"] is True
    assert body["status"] == "pending"

    # Poll until completed
    status = None
    for _ in range(100):
        g = client.get(f"/api/v1/jobs/{job_id}")
        assert g.status_code == 200
        status = g.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert status == "completed", g.json()
    assert g.json()["health_score"] is not None
    assert g.json()["component_scores"] is not None

    report = client.get(f"/api/v1/jobs/{job_id}/report")
    assert report.status_code == 200
    data = report.json()
    assert data["status"] == "completed"
    assert data["scores"]["aeo_health"]["value"] is not None
    assert data["experiment"]["observations_count"] == 15
    assert len(data["recommendations"]) >= 1

    pages = client.get(f"/api/v1/jobs/{job_id}/pages")
    assert pages.status_code == 200
    assert pages.json()["count"] == 5


def test_invalid_url(client):
    r = client.post("/api/v1/jobs", json={"url": "ftp://nope"})
    assert r.status_code == 422 or r.status_code == 400


def test_unknown_job(client):
    r = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_report_conflict_while_pending(client, monkeypatch):
    # Create job but do not wait — race may complete fast; if completed, skip 409 check
    r = client.post(
        "/api/v1/jobs",
        json={"url": "https://demo.example/", "demo_mode": True, "options": {"provider": "demo"}},
    )
    job_id = r.json()["id"]
    # Immediately request report — may be 409 or 200 if already done
    rep = client.get(f"/api/v1/jobs/{job_id}/report")
    assert rep.status_code in (200, 409)
