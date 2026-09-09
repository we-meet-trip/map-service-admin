import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app import upstream
from app.routers.proxy_util import proxied


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429, 500, 503, 307])
def test_failure_body_is_never_forwarded(monkeypatch, status):
    marker = "private-user-location-and-serviceKey=synthetic-secret"
    factory = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=marker))
    monkeypatch.setattr(upstream.httpx, "AsyncClient", lambda **kwargs: factory(transport=transport, **kwargs))
    with pytest.raises(HTTPException) as failure:
        asyncio.run(proxied(upstream.request_json("GET", "http://synthetic.invalid/ordinary")))
    assert marker not in str(failure.value.detail)
    assert set(failure.value.detail) == {"code", "message"}
    assert failure.value.status_code == (502 if status == 307 else status)


def test_malformed_success_does_not_expose_body(monkeypatch):
    factory = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="synthetic-private-body"))
    monkeypatch.setattr(upstream.httpx, "AsyncClient", lambda **kwargs: factory(transport=transport, **kwargs))
    with pytest.raises(HTTPException) as failure:
        asyncio.run(proxied(upstream.request_json("GET", "http://synthetic.invalid/ordinary")))
    assert failure.value.status_code == 502
    assert failure.value.detail["code"] == "upstream_unavailable"
    assert "synthetic-private-body" not in str(failure.value.detail)


def test_exception_directly_created_by_caller_is_also_sanitized():
    async def failed():
        raise upstream.UpstreamError(409, {"detail": "synthetic-private-body"})
    with pytest.raises(HTTPException) as failure:
        asyncio.run(proxied(failed()))
    assert failure.value.detail["code"] == "upstream_conflict"
    assert "synthetic-private-body" not in str(failure.value.detail)
