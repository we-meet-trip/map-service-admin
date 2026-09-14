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
    async def recorded(*_a, **_k): return 1
    monkeypatch.setattr(audit, "record", recorded)
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


# ── 개인정보 열람 기록과 원문 열람 등급 ──────────────────────────────

def _capture_audit(monkeypatch):
    """audit.record 호출을 가로채 인자만 모은다."""
    calls = []

    async def record(actor, action, **kwargs):
        # record 의 기본값과 같은 모양으로 모은다.
        kwargs.setdefault("status", "ok")
        calls.append({"actor": actor, "action": action, **kwargs})
        return len(calls)

    monkeypatch.setattr(audit, "record", record)
    return calls


def test_member_list_lookup_is_audited_without_the_search_text(client, monkeypatch):
    identify(monkeypatch, "operator", ["test"])
    calls = _capture_audit(monkeypatch)

    async def listed(*_a, **_k):
        return {"items": [], "total": 0}

    monkeypatch.setattr(bff_client, "list_users", listed)

    response = client.get("/api/v1/users", params={"query": "someone@example.com"})

    assert response.status_code == 200
    entries = [call for call in calls if call["action"] == "users.list"]
    assert len(entries) == 1
    assert entries[0]["actor"] == "person"
    assert entries[0]["target_table"] == "users"
    assert entries[0]["params"] == {"searched": True, "page": 0, "size": 20}
    assert "someone@example.com" not in repr(calls)


def test_viewer_cannot_read_the_raw_email_detail(client, monkeypatch):
    identify(monkeypatch, "viewer", ["test"])
    _capture_audit(monkeypatch)

    async def forbidden(*_a, **_k):
        raise AssertionError("upstream must not be called")

    monkeypatch.setattr(bff_client, "get_user", forbidden)

    assert client.get("/api/v1/users/5").status_code == 403


def test_operator_still_reads_the_raw_email_detail(client, monkeypatch):
    identify(monkeypatch, "operator", ["test"])
    calls = _capture_audit(monkeypatch)

    async def detail(*_a, **_k):
        return {"id": 5}

    monkeypatch.setattr(bff_client, "get_user", detail)

    assert client.get("/api/v1/users/5").status_code == 200
    assert [call["action"] for call in calls] == ["users.view-detail"]


# ── 관리자 접속 기록 ─────────────────────────────────────────────────

def test_login_records_success_failure_and_throttling(client, monkeypatch):
    calls = _capture_audit(monkeypatch)

    async def allowed(*_a):
        return True

    async def rejected(*_a):
        return None

    monkeypatch.setattr(accounts, "login_allowed", allowed)
    monkeypatch.setattr(accounts, "authenticate", rejected)
    assert client.post("/api/v1/auth/login",
                       json={"username": "person", "password": "wrong"}).status_code == 401

    async def accepted(*_a):
        return 1

    async def session(*_a):
        return "11111111-1111-1111-1111-111111111111", None

    async def permissions(_):
        return {"id": 1, "username": "person", "role": "owner", "is_active": True,
                "allowed_environments": []}

    monkeypatch.setattr(accounts, "authenticate", accepted)
    monkeypatch.setattr(accounts, "create_session", session)
    monkeypatch.setattr(accounts, "permissions", permissions)
    assert client.post("/api/v1/auth/login",
                       json={"username": "person", "password": "right"}).status_code == 200

    async def denied(*_a):
        return False

    monkeypatch.setattr(accounts, "login_allowed", denied)
    assert client.post("/api/v1/auth/login",
                       json={"username": "person", "password": "right"}).status_code == 429

    assert [call["status"] for call in calls if call["action"] == "auth.login"] == [
        "failed", "ok", "throttled"]
    assert all("right" not in repr(call) and "wrong" not in repr(call) for call in calls)


def test_logout_records_only_a_real_session(client, monkeypatch):
    calls = _capture_audit(monkeypatch)

    async def none(*_a):
        return None

    async def deleted(*_a):
        return None

    monkeypatch.setattr(accounts, "operator_for_session", none)
    monkeypatch.setattr(accounts, "delete_session", deleted)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert [call for call in calls if call["action"] == "auth.logout"] == []

    async def person(*_a):
        return "person"

    monkeypatch.setattr(accounts, "operator_for_session", person)
    assert client.post("/api/v1/auth/logout").status_code == 204
    entries = [call for call in calls if call["action"] == "auth.logout"]
    assert len(entries) == 1 and entries[0]["actor"] == "person"
