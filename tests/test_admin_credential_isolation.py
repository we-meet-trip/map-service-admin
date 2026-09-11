import asyncio
import httpx
import pytest
from pydantic import SecretStr
from app import bff_client, hub_client, upstream
from app.config import control_settings, select_environment, reset_environment


@pytest.fixture
def transport(monkeypatch):
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=[])
    factory=httpx.AsyncClient
    monkeypatch.setattr(upstream.httpx,"AsyncClient",lambda **kwargs: factory(transport=httpx.MockTransport(respond),**kwargs))
    monkeypatch.setattr(control_settings,"INTERNAL_SERVICE_TOKEN",SecretStr("synthetic-serving"))
    monkeypatch.setattr(control_settings,"USER_ADMIN_INTERNAL_TOKEN",SecretStr("synthetic-admin"))
    monkeypatch.setattr(control_settings,"HUB_ADMIN_INTERNAL_TOKEN",SecretStr("synthetic-hub-admin"))
    return calls


def test_all_bff_operations_use_dedicated_management_credential(transport):
    async def run():
        await bff_client.list_users(None,0,10)
        await bff_client.get_user(1)
        await bff_client.job_stats()
        await bff_client.list_jobs(None,0,10)
        await bff_client.list_dlq(10)
        await bff_client.dlq_reprocess(["synthetic"])
        await bff_client.dlq_discard(["synthetic"])
    asyncio.run(run())
    assert len(transport)==7
    assert all(r.headers["X-Internal-Token"]=="synthetic-admin" for r in transport)


def test_all_hub_operations_use_dedicated_management_credential(transport):
    async def run():
        await hub_client.kma_run_now("short")
        await hub_client.toggle_grid(1, True)
        await hub_client.list_forbidden_zones()
        await hub_client.get_forbidden_zone(1)
        await hub_client.create_forbidden_zone({})
        await hub_client.update_forbidden_zone(1, {})
        await hub_client.delete_forbidden_zone(1)
    asyncio.run(run())
    assert len(transport) == 7
    assert all(r.headers["X-Internal-Token"] == "synthetic-hub-admin" for r in transport)


@pytest.mark.parametrize("token", ["", " ", "synthetic-serving", "synthetic-admin"])
def test_hub_missing_or_shared_token_never_opens_network(transport, monkeypatch, token):
    monkeypatch.setattr(control_settings, "HUB_ADMIN_INTERNAL_TOKEN", SecretStr(token))
    with pytest.raises(upstream.UpstreamUnavailable):
        asyncio.run(hub_client.list_forbidden_zones())
    assert not transport


@pytest.mark.parametrize("path", ["/public", "/internal/kma/other", "/internal/grids/1/extra",
                                  "/internal/forbidden-zones/../ordinary", "/internal/forbidden-zones#fragment"])
def test_hub_credential_never_leaves_explicit_paths(transport, path):
    with pytest.raises(upstream.UpstreamUnavailable):
        asyncio.run(upstream.request_hub_admin_json("GET", control_settings.HUB_BASE_URL + path))
    assert not transport


def test_plain_helper_cannot_call_hub_management_path(transport):
    with pytest.raises(upstream.UpstreamUnavailable):
        asyncio.run(upstream.request_json("GET", control_settings.HUB_BASE_URL + "/internal/forbidden-zones"))
    assert not transport


def test_target_cannot_inherit_control_hub_management_credential(transport, monkeypatch):
    monkeypatch.setattr(control_settings, "ADMIN_TARGETS", {"prod": {
        "USER_BASE_URL": "https://prod.example/user", "HUB_BASE_URL": "https://prod.example/hub",
        "AGENT_BASE_URL": "https://prod.example/agent", "INTERNAL_SERVICE_TOKEN": "synthetic-prod-serving"}})
    context = select_environment("prod")
    try:
        with pytest.raises(upstream.UpstreamUnavailable):
            asyncio.run(hub_client.list_forbidden_zones())
        assert not transport
    finally:
        reset_environment(context)


@pytest.mark.parametrize("token",[""," ","synthetic-serving"])
def test_missing_or_reused_admin_secret_never_opens_network(transport,monkeypatch,token):
    monkeypatch.setattr(control_settings,"USER_ADMIN_INTERNAL_TOKEN",SecretStr(token))
    with pytest.raises(upstream.UpstreamUnavailable): asyncio.run(bff_client.job_stats())
    assert not transport
    asyncio.run(upstream.request_json("GET",control_settings.HUB_BASE_URL+"/internal/admin/grids"))
    assert transport[0].headers["X-Internal-Token"]=="synthetic-serving"


def test_target_specific_secret_is_not_inherited_even_for_default_override(transport,monkeypatch):
    target={"USER_BASE_URL":"https://private.example/user","HUB_BASE_URL":"https://private.example/hub",
            "AGENT_BASE_URL":"https://private.example/agent","INTERNAL_SERVICE_TOKEN":"synthetic-target-serving"}
    monkeypatch.setattr(control_settings,"ADMIN_TARGETS",{"test":target})
    context=select_environment("test")
    try:
        with pytest.raises(upstream.UpstreamUnavailable): asyncio.run(bff_client.job_stats())
        assert not transport
    finally: reset_environment(context)
    target["USER_ADMIN_INTERNAL_TOKEN"]="synthetic-target-admin"
    context=select_environment("test")
    try:
        asyncio.run(bff_client.job_stats())
        assert transport[0].headers["X-Internal-Token"]=="synthetic-target-admin"
        assert str(transport[0].url).startswith("https://private.example/user/internal/admin/")
    finally: reset_environment(context)


@pytest.mark.parametrize("url",["https://other.example/internal/admin/users","http://user:8080/api/v1/users",
    "http://user:8080/internal/adminx/users","http://user:8080/internal/admin/../public",
    "http://user:8080/internal/admin/users#fragment","http://x@user:8080/internal/admin/users"])
def test_management_secret_is_restricted_to_selected_destination(transport,url):
    with pytest.raises(upstream.UpstreamUnavailable): asyncio.run(upstream.request_user_admin_json("GET",url))
    assert not transport


def test_plain_helper_cannot_accidentally_send_serving_secret_to_admin_path(transport):
    with pytest.raises(upstream.UpstreamUnavailable):
        asyncio.run(upstream.request_json("GET",control_settings.USER_BASE_URL+"/internal/admin/users"))
    assert not transport


def test_redirect_does_not_forward_management_credential(monkeypatch):
    calls=[]
    def redirect(request):
        calls.append(request)
        return httpx.Response(307,headers={"Location":"https://untrusted.example/"})
    factory=httpx.AsyncClient
    monkeypatch.setattr(upstream.httpx,"AsyncClient",lambda **kwargs: factory(transport=httpx.MockTransport(redirect),**kwargs))
    monkeypatch.setattr(control_settings,"USER_ADMIN_INTERNAL_TOKEN",SecretStr("synthetic-admin"))
    with pytest.raises(upstream.UpstreamError): asyncio.run(bff_client.job_stats())
    assert len(calls)==1


def test_moderation_delegation_uses_selected_management_credential(transport):
    from app.routers.moderation_router import delegated
    asyncio.run(delegated("GET", ""))
    assert len(transport)==1 and transport[0].headers["X-Internal-Token"]=="synthetic-admin"


def test_concurrent_environments_never_exchange_management_secrets(transport,monkeypatch):
    targets={name:{"USER_BASE_URL":f"https://{name}.example/user","HUB_BASE_URL":f"https://{name}.example/hub",
                  "AGENT_BASE_URL":f"https://{name}.example/agent","INTERNAL_SERVICE_TOKEN":f"synthetic-{name}-serving",
                  "USER_ADMIN_INTERNAL_TOKEN":f"synthetic-{name}-admin"} for name in ("test","prod")}
    monkeypatch.setattr(control_settings,"ADMIN_TARGETS",targets)
    async def request(name):
        context=select_environment(name)
        try:
            await asyncio.sleep(0)
            await bff_client.job_stats()
        finally: reset_environment(context)
    async def run(): await asyncio.gather(request("test"),request("prod"))
    asyncio.run(run())
    assert {r.url.host:r.headers["X-Internal-Token"] for r in transport}=={"test.example":"synthetic-test-admin","prod.example":"synthetic-prod-admin"}
