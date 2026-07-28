"""admin cut 2 스모크 테스트 (세션 API).

DB/Redis/업스트림을 건드리지 않도록 각 데이터 모듈 함수를 monkeypatch 하고,
세션 의존성(require_operator)은 dependency_overrides 로 대체한다. 실제 DB 통합
검증은 E2E 체크리스트(Phase 7)에서 다룬다.

Settings 가 ADMIN_DATABASE_URL 을 필수로 요구하므로 app 임포트 전에 주입한다.
"""
from __future__ import annotations

import os

os.environ.setdefault(
    "ADMIN_DATABASE_URL", "postgresql+psycopg://map_admin:x@localhost:5432/map"
)
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-token")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import (  # noqa: E402
    accounts,
    audit,
    bff_client,
    external_status,
    health_client,
    hub_client,
    repo,
)
from app.main import app  # noqa: E402
from app.security import require_operator  # noqa: E402
from app.upstream import UpstreamError, UpstreamUnavailable  # noqa: E402

client = TestClient(app)


@pytest.fixture
def authed():
    """require_operator 를 'tester' 로 오버라이드한 인증 컨텍스트."""
    app.dependency_overrides[require_operator] = lambda: "tester"
    yield
    app.dependency_overrides.pop(require_operator, None)


# ── liveness / 게이팅 ────────────────────────────────────────────────

def test_health_no_auth() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "admin"}


@pytest.mark.parametrize("path", [
    "/api/v1/ops/health", "/api/v1/audit", "/api/v1/users",
    "/api/v1/jobs/stats", "/api/v1/db/tables", "/docs",
])
def test_protected_requires_session(path) -> None:
    """세션 쿠키 없으면 401."""
    assert client.get(path).status_code == 401


# ── 로그인 ───────────────────────────────────────────────────────────

def test_login_success(monkeypatch) -> None:
    async def fake_auth(u, p):
        return 7

    async def fake_session(aid):
        from datetime import datetime, timezone
        return "11111111-1111-1111-1111-111111111111", datetime.now(timezone.utc)

    monkeypatch.setattr(accounts, "authenticate", fake_auth)
    monkeypatch.setattr(accounts, "create_session", fake_session)
    r = client.post("/api/v1/auth/login",
                    json={"username": "op", "password": "pw"})
    assert r.status_code == 200
    assert r.json() == {"username": "op"}
    assert "admin_session" in r.cookies


def test_login_bad_credentials(monkeypatch) -> None:
    async def fake_auth(u, p):
        return None

    monkeypatch.setattr(accounts, "authenticate", fake_auth)
    r = client.post("/api/v1/auth/login",
                    json={"username": "op", "password": "bad"})
    assert r.status_code == 401


def test_me(authed) -> None:
    assert client.get("/api/v1/auth/me").json() == {"username": "tester"}


# ── ops ──────────────────────────────────────────────────────────────

def test_ops_monitoring(authed) -> None:
    """config 기반 — DB 무관."""
    r = client.get("/api/v1/ops/monitoring")
    assert r.status_code == 200
    assert "panels" in r.json()


def test_ops_health(authed, monkeypatch) -> None:
    async def fake_rollup():
        return [{"service": "hub", "ok": True}]

    monkeypatch.setattr(health_client, "rollup", fake_rollup)
    r = client.get("/api/v1/ops/health")
    assert r.status_code == 200
    assert r.json()["services"][0]["service"] == "hub"


def test_external_probe_unknown(authed) -> None:
    assert client.post("/api/v1/ops/external/nope/probe").status_code == 404


def test_external_probe_known(authed, monkeypatch) -> None:
    async def fake_probe(p):
        return {"provider": p, "ok": True, "latency_ms": 5, "detail": {}}

    async def fake_record(*a, **k):
        return 42

    monkeypatch.setattr(external_status, "probe", fake_probe)
    monkeypatch.setattr(audit, "record", fake_record)
    r = client.post("/api/v1/ops/external/kakao/probe")
    assert r.status_code == 200
    assert r.json()["audit_id"] == 42


# ── db 뷰어 ──────────────────────────────────────────────────────────

def test_db_rows_unknown_table_404(authed, monkeypatch) -> None:
    async def fake_names():
        return set()

    monkeypatch.setattr(repo, "hub_table_names", fake_names)
    assert client.get("/api/v1/db/tables/nope").status_code == 404


def test_db_rows_invalid_sort_422(authed, monkeypatch) -> None:
    async def fake_names():
        return {"places"}

    async def fake_browse(*a, **k):
        raise ValueError("unknown sort column: x")

    monkeypatch.setattr(repo, "hub_table_names", fake_names)
    monkeypatch.setattr(repo, "browse_table", fake_browse)
    r = client.get("/api/v1/db/tables/places?sort=x:asc")
    assert r.status_code == 422


# ── actions + audit ─────────────────────────────────────────────────

def test_action_grid_toggle_records_audit(authed, monkeypatch) -> None:
    recorded = {}

    async def fake_toggle(gid, active):
        return {"ok": True, "changed": True,
                "before": {"is_active": True}, "after": {"is_active": active}}

    async def fake_record(actor, action, **k):
        recorded["action"] = action
        recorded["actor"] = actor
        return 99

    monkeypatch.setattr(hub_client, "toggle_grid", fake_toggle)
    monkeypatch.setattr(audit, "record", fake_record)
    r = client.patch("/api/v1/actions/grids/3", json={"is_active": False})
    assert r.status_code == 200
    assert recorded["action"] == "grids.toggle"
    assert recorded["actor"] == "tester"


# ── 프록시 에러 매핑 ─────────────────────────────────────────────────

def test_proxy_upstream_error_propagates(authed, monkeypatch) -> None:
    async def fake_users(*a, **k):
        raise UpstreamError(404, {"detail": "not found"})

    monkeypatch.setattr(bff_client, "list_users", fake_users)
    assert client.get("/api/v1/users").status_code == 404


def test_proxy_upstream_unavailable_502(authed, monkeypatch) -> None:
    async def fake_users(*a, **k):
        raise UpstreamUnavailable("connection refused")

    monkeypatch.setattr(bff_client, "list_users", fake_users)
    assert client.get("/api/v1/users").status_code == 502
