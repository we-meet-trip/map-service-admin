"""Run only against a newly migrated, isolated database; never a shared server."""
import asyncio
import os
import uuid

import pytest
from sqlalchemy import text

os.environ.setdefault("ADMIN_DATABASE_URL", "postgresql+psycopg://map_admin:x@localhost:5432/map")

from app import accounts, audit
from app.config import control_settings, reset_environment, select_environment
from app.db import dispose_engine, get_control_engine


@pytest.mark.skipif(not os.getenv("MAP_ADMIN_ISOLATED_TEST_DATABASE_URL"), reason="isolated PostgreSQL not configured")
def test_permissions_sessions_rate_limit_and_environment_audit(monkeypatch):
    monkeypatch.setattr(control_settings, "ADMIN_DATABASE_URL", os.environ["MAP_ADMIN_ISOLATED_TEST_DATABASE_URL"])
    monkeypatch.setattr(control_settings, "ADMIN_LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(control_settings, "ADMIN_TARGETS", {"prod": {
        "ADMIN_DATABASE_URL": control_settings.ADMIN_DATABASE_URL,
        "ADMIN_REDIS_URL": "redis://not-used:6379", "USER_BASE_URL": "http://not-used:8080",
        "AGENT_BASE_URL": "http://not-used:8000", "HUB_BASE_URL": "http://not-used:8000",
        "INTERNAL_SERVICE_TOKEN": "isolated-test-only",
    }})

    async def check():
        suffix = uuid.uuid4().hex
        username = "operator-" + suffix
        account_id = await accounts.create_account(username, "isolated-test-password", "operator", ["test"])
        assert await accounts.authenticate(username, "wrong") is None
        assert await accounts.authenticate(username, "isolated-test-password") == account_id
        assert (await accounts.permissions(username))["allowed_environments"] == ["test"]
        first, _ = await accounts.create_session(account_id)
        second, _ = await accounts.create_session(account_id)
        assert await accounts.operator_for_session(first) == username
        await accounts.update_account(account_id, active=True, role="viewer", environments=["test"], password=None)
        assert await accounts.operator_for_session(first) is None
        assert await accounts.operator_for_session(second) is None
        assert (await accounts.permissions(username))["role"] == "viewer"

        # Multiple workers share one database cap; no in-process counter bypass.
        results = await asyncio.gather(*(accounts.login_allowed(username, suffix) for _ in range(8)))
        assert sum(results) == 3
        request_id = await audit.record(username, "request.started", status="started")
        await audit.finish(request_id, 409)
        token = select_environment("prod")
        try:
            await audit.record(username, "test.prod-only")
            assert {r["action"] for r in (await audit.list_logs(actor=username))["items"]} == {"test.prod-only"}
        finally:
            reset_environment(token)
        rows = (await audit.list_logs(actor=username))["items"]
        assert len(rows) == 1
        assert rows[0]["status"] == "error"
        assert rows[0]["after_json"] == {"http_status": 409}

        async with get_control_engine().connect() as conn:
            owners = (await conn.execute(text("SELECT id FROM admin_data.admin_accounts WHERE is_active AND role='owner'"))).scalars().all()
        assert owners, "fixture must contain its migrated owner"
        if len(owners) == 1:
            with pytest.raises(ValueError, match="마지막"):
                await accounts.update_account(owners[0], active=False, role="viewer", environments=[], password=None)
        await dispose_engine()

    asyncio.run(check())
