import asyncio
import os
os.environ.setdefault("ADMIN_DATABASE_URL", "postgresql+psycopg://legacy:x@localhost/map")

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import accounts, db
from app.config import control_settings, settings, select_environment, reset_environment
from app.main import app


def target(**overrides):
    return {"ADMIN_REDIS_URL": "redis://target:6379", "USER_BASE_URL": "http://target-user:8080",
            "AGENT_BASE_URL": "http://target-agent:8000", "HUB_BASE_URL": "http://target-hub:8000",
            "INTERNAL_SERVICE_TOKEN": "target-token", **overrides}


def test_default_target_override_and_api_only_never_inherit_control(monkeypatch):
    monkeypatch.setattr(control_settings, "ADMIN_CONTROL_DATABASE_URL", "postgresql+psycopg://control:x@control/admin")
    monkeypatch.setattr(control_settings, "ADMIN_TARGETS", {"test": target()})
    token = select_environment("test")
    try:
        assert settings.USER_BASE_URL == "http://target-user:8080"
        assert settings.ADMIN_DATABASE_URL == ""
        assert not settings.GEMINI_API_KEY.get_secret_value()
        with pytest.raises(HTTPException, match="target database not configured"):
            db.get_engine()
    finally:
        reset_environment(token)


def test_control_lifespan_and_login_survive_missing_or_invalid_default_target(monkeypatch):
    monkeypatch.setattr(control_settings, "ADMIN_CONTROL_DATABASE_URL", "postgresql+psycopg://control:x@control/admin")
    monkeypatch.setattr(control_settings, "ADMIN_TARGETS", {"test": {"USER_BASE_URL": "http://invalid"}})
    calls = []
    async def bootstrap(): calls.append("bootstrap")
    async def allowed(*_): return True
    async def auth(*_): return None
    monkeypatch.setattr(accounts, "bootstrap_if_empty", bootstrap)
    monkeypatch.setattr(accounts, "login_allowed", allowed)
    monkeypatch.setattr(accounts, "authenticate", auth)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/api/v1/auth/login", json={"username": "synthetic", "password": "wrong"}).status_code == 401
        assert client.get("/api/v1/ops/overview").status_code == 400
    assert calls == ["bootstrap"]


def test_readonly_target_pool_separate_even_when_legacy_dsn_is_same(monkeypatch):
    monkeypatch.setattr(control_settings, "ADMIN_CONTROL_DATABASE_URL", "")
    made = []
    def create(url, **kwargs):
        engine = object()
        made.append((url, kwargs, engine))
        return engine
    monkeypatch.setattr(db, "create_async_engine", create)
    monkeypatch.setattr(db, "_engines", {})
    control = db.get_control_engine()
    token = select_environment("test")
    try:
        readonly = db.get_engine()
    finally:
        reset_environment(token)
    assert control is not readonly
    assert "default_transaction_read_only=on" not in made[0][1]["connect_args"]["options"]
    assert "default_transaction_read_only=on" in made[1][1]["connect_args"]["options"]
    assert made[1][1]["max_overflow"] == 0


def test_api_only_target_has_no_database_or_redis_fallback(monkeypatch):
    from app import health_client, redis_probe
    config = target()
    config.pop("ADMIN_REDIS_URL")
    monkeypatch.setattr(control_settings, "ADMIN_TARGETS", {"test": config})
    token = select_environment("test")
    try:
        assert settings.ADMIN_REDIS_URL == ""
        assert asyncio.run(health_client._check_redis())["configured"] is False
        assert asyncio.run(health_client._check_postgres())["configured"] is False
        for check in (redis_probe.streams_overview, redis_probe.gemini_quota, redis_probe.cache_stats):
            assert asyncio.run(check()) == {"error": "not_configured", "configured": False}
    finally:
        reset_environment(token)
