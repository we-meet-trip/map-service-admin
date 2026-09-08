"""내부 위임 호출 공통 헬퍼 (hub/BFF `/internal`).

admin 은 hub_data 쓰기·회원/잡/DLQ 조작을 소유 서비스 `/internal` 로 위임한다
(경계 B9). 본 모듈은 X-Internal-Token 부착 + 상태코드 전파 + 연결오류 매핑을
담당한다.

에러 규약:
  - 업스트림 2xx  → 파싱된 JSON 반환
  - 업스트림 4xx/5xx → UpstreamError(status_code, payload) (라우터가 그대로 전파)
  - 연결 실패/타임아웃 → UpstreamUnavailable (라우터가 502)
"""
from __future__ import annotations

from typing import Any
import secrets
import re

import httpx

from app.config import settings


class UpstreamError(Exception):
    """업스트림이 4xx/5xx 를 반환한 경우(상태코드·본문 보존)."""

    def __init__(self, status_code: int, payload: Any) -> None:
        super().__init__(f"upstream returned {status_code}")
        self.status_code = status_code
        self.payload = payload


class UpstreamUnavailable(Exception):
    """업스트림 연결 실패/타임아웃(→ 502)."""


def _headers(*, user_admin: bool = False) -> dict[str, str]:
    ordinary = settings.INTERNAL_SERVICE_TOKEN.get_secret_value()
    token = settings.USER_ADMIN_INTERNAL_TOKEN.get_secret_value() if user_admin else ordinary
    if user_admin and (not token.strip() or secrets.compare_digest(token.encode("utf-8"), ordinary.encode("utf-8"))):
        raise UpstreamUnavailable("dedicated user administration credential unavailable")
    return {"X-Internal-Token": token} if token else {}


def _user_admin_url(url: str) -> bool:
    candidate = httpx.URL(url)
    base = httpx.URL(settings.USER_BASE_URL.rstrip("/") + "/internal/admin/")
    return (candidate.scheme, candidate.host, candidate.port) == (base.scheme, base.host, base.port) and candidate.path.startswith(base.path) and not candidate.userinfo and not candidate.fragment and "%" not in candidate.raw_path.decode("ascii")


async def request_user_admin_json(method: str, url: str, **kwargs) -> Any:
    """The management secret is restricted to the selected User management endpoint."""
    if not _user_admin_url(url):
        raise UpstreamUnavailable("invalid user administration destination")
    return await request_json(method, url, _user_admin=True, **kwargs)


async def request_json(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any | None = None,
    admin_actor: str | None = None,
    _user_admin: bool = False,
) -> Any:
    """내부 위임 호출. 2xx 면 JSON, 4xx/5xx 면 UpstreamError, 연결오류면
    UpstreamUnavailable 를 발생."""
    if _user_admin and not _user_admin_url(url):
        raise UpstreamUnavailable("invalid user administration destination")
    if not _user_admin and _user_admin_url(url):
        raise UpstreamUnavailable("user administration requires dedicated credential")
    headers = _headers(user_admin=_user_admin)
    if admin_actor is not None:
        if not re.fullmatch(r"admin_[1-9][0-9]*", admin_actor):
            raise ValueError("invalid opaque admin actor")
        headers["X-Admin-Actor"] = admin_actor
    try:
        async with httpx.AsyncClient(
            timeout=settings.INTERNAL_TIMEOUT_SEC, follow_redirects=False
        ) as client:
            resp = await client.request(
                method, url, params=params, json=json, headers=headers
            )
    except httpx.HTTPError as exc:
        raise UpstreamUnavailable(type(exc).__name__) from exc

    if resp.status_code >= 300:
        try:
            payload = resp.json()
        except Exception:
            payload = {"detail": resp.text}
        raise UpstreamError(resp.status_code, payload)

    if resp.status_code == 204 or not resp.content:
        return None
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}
