import os
from uuid import uuid4
os.environ.setdefault("ADMIN_DATABASE_URL", "postgresql+psycopg://map_admin:x@localhost:5432/map")

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import accounts, audit
from app.config import control_settings
from app.main import app
from app.routers import moderation_router as route
from app.upstream import UpstreamError, UpstreamUnavailable


@pytest.fixture
def harness(monkeypatch):
    app.dependency_overrides.clear()
    state = {"role": "owner", "environments": ["test"], "calls": [], "audit": []}
    async def session(_): return "private-operator-name"
    async def permissions(_): return {"id": 17, "role": state["role"], "allowed_environments": state["environments"]}
    async def record(actor, action, **kwargs):
        state["audit"].append((actor, action, kwargs)); return len(state["audit"])
    async def finish(*args): pass
    async def request(method, url, **kwargs):
        state["calls"].append((method, url, kwargs))
        if method == "POST": return receipt()
        if url.endswith(str(REPORT)): return {"report": receipt(), "description": "synthetic private review", "current_message": "synthetic chat", "actions": []}
        return [receipt()]
    monkeypatch.setattr(accounts, "operator_for_session", session)
    monkeypatch.setattr(accounts, "permissions", permissions)
    monkeypatch.setattr(audit, "record", record)
    monkeypatch.setattr(audit, "finish", finish)
    monkeypatch.setattr(route, "request_json", request)
    yield TestClient(app), state
    app.dependency_overrides.clear()


REPORT = uuid4()
HEADERS = {"X-Map-Environment": "test"}
BASE = "/api/v1/moderation/reports"
def receipt():
    return {"report_id": str(REPORT), "status": "OPEN", "content_type": "CHAT_MESSAGE", "reason": "OTHER",
            "resolution": None, "created_at": "2026-09-07T00:00:00Z", "updated_at": "2026-09-07T00:00:00Z"}


def test_explicit_environment_required_for_even_owner_reads(harness):
    client, state = harness
    assert client.get(BASE).status_code == 403
    assert client.get(BASE + "?environment=test").status_code == 403
    assert not state["calls"]
    assert client.get(BASE, headers=HEADERS).status_code == 200
    assert client.get(BASE, headers={"X-Map-Environment": "unknown"}).status_code == 400


def test_viewer_metadata_only_operator_review_and_owner_enforcement(harness):
    client, state = harness
    state["role"] = "viewer"
    assert client.get(BASE, headers=HEADERS).status_code == 200
    assert client.get(BASE + f"/{REPORT}", headers=HEADERS).status_code == 403
    state["role"] = "operator"
    detail = client.get(BASE + f"/{REPORT}", headers=HEADERS)
    assert detail.status_code == 200 and detail.headers["cache-control"] == "no-store"
    action = {"action_id": str(uuid4()), "action": "HIDE_CHAT_MESSAGE"}
    assert client.post(BASE + f"/{REPORT}/actions", headers=HEADERS, json=action).status_code == 403
    action["action"] = "REVIEW"
    assert client.post(BASE + f"/{REPORT}/actions", headers=HEADERS, json=action).status_code == 200
    state["role"] = "owner"; action["action"] = "HIDE_CHAT_MESSAGE"
    assert client.post(BASE + f"/{REPORT}/actions", headers=HEADERS, json=action).status_code == 200
    assert state["calls"][-1][2]["admin_actor"] == "admin_17"
    assert all(record[0] == "admin_17" for record in state["audit"])
    assert "synthetic private" not in str(state["audit"]) and "synthetic chat" not in str(state["audit"])


def test_target_scope_cannot_be_bypassed_by_owner_header_or_query(harness, monkeypatch):
    client, state = harness
    state["role"] = "operator"; state["environments"] = ["prod"]
    assert client.get(BASE, headers=HEADERS).status_code == 403
    assert not state["calls"]
    monkeypatch.setattr(control_settings, "ADMIN_TARGETS", {"prod": {
        "USER_BASE_URL": "https://private-prod.example", "HUB_BASE_URL": "https://private-hub.example",
        "AGENT_BASE_URL": "https://private-agent.example", "INTERNAL_SERVICE_TOKEN": "synthetic-prod-token"}})
    assert client.get(BASE, headers={"X-Map-Environment": "prod"}).status_code == 200
    assert state["calls"][-1][1].startswith("https://private-prod.example/internal/")


def test_audit_outage_stops_content_disclosure_and_actions(harness, monkeypatch):
    client, state = harness
    async def unavailable(*a, **k): raise HTTPException(503, "audit unavailable")
    monkeypatch.setattr(audit, "record", unavailable)
    assert client.get(BASE + f"/{REPORT}", headers=HEADERS).status_code == 503
    assert client.post(BASE + f"/{REPORT}/actions", headers=HEADERS,
                       json={"action_id": str(uuid4()), "action": "REVIEW"}).status_code == 503
    assert not state["calls"]


@pytest.mark.parametrize("action,hours,expected", [("RESTRICT_CHAT",None,400),("RESTRICT_CHAT",0,422),
    ("RESTRICT_CHAT",721,422),("REVIEW",24,400),("RESTRICT_CHAT",24,200),("LIFT_CHAT_RESTRICTION",None,200)])
def test_action_shape_and_bounds(harness, action, hours, expected):
    client, state = harness
    body = {"action_id": str(uuid4()), "action": action}
    if hours is not None: body["restriction_hours"] = hours
    result = client.post(BASE + f"/{REPORT}/actions", headers=HEADERS, json=body)
    assert result.status_code == expected
    if expected != 200: assert not state["calls"]


def test_error_body_and_private_upstream_address_are_never_reflected(harness, monkeypatch):
    client, _ = harness
    async def private_error(*a, **k): raise UpstreamError(409, {"description":"private raw content"})
    monkeypatch.setattr(route, "request_json", private_error)
    response = client.get(BASE, headers=HEADERS)
    assert response.status_code == 409 and "private raw" not in response.text
    async def private_network(*a, **k): raise UpstreamUnavailable("https://private-host/secret")
    monkeypatch.setattr(route, "request_json", private_network)
    response = client.get(BASE, headers=HEADERS)
    assert response.status_code == 502 and "private-host" not in response.text


def test_mutation_requires_cookie_auth_and_custom_header_not_cross_site_form(harness, monkeypatch):
    client, state = harness
    body={"action_id":str(uuid4()),"action":"REVIEW"}
    assert client.post(BASE+f"/{REPORT}/actions",json=body).status_code==403
    async def anonymous(_): return None
    monkeypatch.setattr(accounts,"operator_for_session",anonymous)
    assert client.post(BASE+f"/{REPORT}/actions",headers=HEADERS,json=body).status_code==401
    assert not state["calls"]


def test_malformed_upstream_content_is_not_exposed_by_validation_errors(harness, monkeypatch):
    client, _ = harness
    async def malformed(*a, **k): return {"description": "private unexpected content"}
    monkeypatch.setattr(route, "request_json", malformed)
    result=client.get(BASE+f"/{REPORT}",headers=HEADERS)
    assert result.status_code==502 and "private unexpected" not in result.text
    result=client.get(BASE,headers=HEADERS)
    assert result.status_code==502 and "private unexpected" not in result.text
