import asyncio
import os
os.environ.setdefault("ADMIN_DATABASE_URL", "postgresql+psycopg://map_admin:x@localhost:5432/map")

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import accounts, audit, bff_client, health_client, redis_probe, repo
from app.config import control_settings, settings, select_environment, reset_environment
from app.main import app
from app.security import require_operator


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    return TestClient(app)


def identify(monkeypatch, role="owner", environments=None):
    async def operator(_): return "person"
    async def permissions(_):
        return {"id": 1, "username": "person", "role": role, "is_active": True,
                "allowed_environments": environments or []}
    monkeypatch.setattr(accounts, "operator_for_session", operator)
    monkeypatch.setattr(accounts, "permissions", permissions)


def test_login_throttle_precedes_password_check(client, monkeypatch):
    async def denied(*_): return False
    async def forbidden(*_): raise AssertionError("password check must not run")
    monkeypatch.setattr(accounts, "login_allowed", denied)
    monkeypatch.setattr(accounts, "authenticate", forbidden)
    response = client.post("/api/v1/auth/login", json={"username": "person", "password": "password"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_viewer_cannot_run_mutation(client, monkeypatch):
    identify(monkeypatch, "viewer", ["test"])
    response = client.post("/api/v1/actions/dlq/reprocess", headers={"X-Map-Environment": "test"}, json={"ids": ["1-0"]})
    assert response.status_code == 403


def test_environment_access_fails_closed(client, monkeypatch):
    identify(monkeypatch, "operator", ["prod"])
    assert client.get("/api/v1/ops/overview").status_code == 403
    # 자신의 허용 환경을 고를 수 있도록 중앙 메타 정보는 접근 가능하다.
    assert client.get("/api/v1/environments").status_code == 200
    assert client.get("/api/v1/ops/overview", headers={"X-Map-Environment": "unknown"}).status_code == 400


def test_mutation_requires_explicit_environment(client, monkeypatch):
    identify(monkeypatch)
    assert client.post("/api/v1/actions/dlq/reprocess", json={"ids": ["1-0"]}).status_code == 403


def test_audit_failure_stops_upstream_action(client, monkeypatch):
    identify(monkeypatch)
    async def failed(*a, **k): raise HTTPException(503, "audit unavailable")
    async def forbidden(*a, **k): raise AssertionError("upstream must not be called")
    monkeypatch.setattr(audit, "record", failed)
    monkeypatch.setattr(bff_client, "dlq_reprocess", forbidden)
    response = client.post("/api/v1/actions/dlq/reprocess", headers={"X-Map-Environment": "test"}, json={"ids": ["1-0"]})
    assert response.status_code == 503


def test_parallel_environment_settings_do_not_mix(monkeypatch):
    monkeypatch.setattr(control_settings, "ADMIN_TARGETS", {"prod": {
        "ADMIN_DATABASE_URL": "postgresql+psycopg://readonly:x@prod/db",
        "ADMIN_REDIS_URL": "redis://prod:6379", "USER_BASE_URL": "http://prod-user:8080",
        "AGENT_BASE_URL": "http://prod-agent:8000", "HUB_BASE_URL": "http://prod-hub:8000",
        "INTERNAL_SERVICE_TOKEN": "prod-only",
    }})
    async def read(name):
        token = select_environment(name)
        try:
            await asyncio.sleep(0)
            return settings.USER_BASE_URL, settings.GEMINI_API_KEY.get_secret_value()
        finally: reset_environment(token)
    async def both(): return await asyncio.gather(read("test"), read("prod"))
    local, remote = asyncio.run(both())
    assert local[0] == control_settings.USER_BASE_URL
    assert remote == ("http://prod-user:8080", "")
    assert settings.USER_BASE_URL == control_settings.USER_BASE_URL


def test_redis_error_is_unavailable_not_empty_queue(client, monkeypatch):
    app.dependency_overrides[require_operator] = lambda: "tester"
    async def rollup(): return []
    async def empty(): return {}
    async def failed(): return {"error": "ConnectionError", "detail": "private detail"}
    monkeypatch.setattr(health_client, "rollup", rollup)
    monkeypatch.setattr(repo, "polling_status", empty)
    monkeypatch.setattr(repo, "places_stats", empty)
    monkeypatch.setattr(redis_probe, "gemini_quota", failed)
    monkeypatch.setattr(redis_probe, "streams_overview", failed)
    response = client.get("/api/v1/ops/overview")
    assert response.status_code == 200
    assert response.json()["streams"] is None
    assert response.json()["errors"]["streams"] == "ConnectionError"
    assert "private detail" not in response.text
    app.dependency_overrides.clear()


def test_unknown_health_body_is_not_healthy():
    assert not health_client._is_up({"message": "reachable"})
    assert not health_client._is_up("ok")
    assert health_client._is_up({"status": "UP"})
