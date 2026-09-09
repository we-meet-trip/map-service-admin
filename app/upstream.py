"""내부 위임 호출 공통 헬퍼 (hub/BFF `/internal`).

admin 은 hub_data 쓰기·회원/잡/DLQ 조작을 소유 서비스 `/internal` 로 위임한다
(경계 B9). 본 모듈은 X-Internal-Token 부착 + 상태코드 전파 + 연결오류 매핑을
담당한다.

에러 규약:
  - 업스트림 2xx  → 파싱된 JSON 반환
  - 업스트림 4xx/5xx → 상태코드와 고정 진단 코드/안내만 전달
  - 연결 실패/타임아웃 → UpstreamUnavailable (라우터가 502)
"""
from __future__ import annotations

from typing import Any
import secrets
import re

import httpx

from app.config import settings


class UpstreamError(Exception):
    """업스트림 실패. 원문에는 사용자 자료나 내부 자격이 포함될 수 있다."""

    def __init__(self, status_code: int, payload: Any) -> None:
        super().__init__(f"upstream returned {status_code}")
        self.status_code = status_code if 400 <= status_code <= 599 else 502
        code, message = {
            400: ("invalid_request", "요청 내용을 확인해 주세요."),
            401: ("upstream_unauthorized", "대상 서비스의 관리 인증을 확인해 주세요."),
            403: ("upstream_forbidden", "대상 서비스에서 이 작업을 허용하지 않았습니다."),
            404: ("upstream_not_found", "대상 항목을 찾을 수 없습니다."),
            409: ("upstream_conflict", "대상 상태가 변경되었습니다. 새로고침 후 확인해 주세요."),
            422: ("invalid_request", "입력 형식과 필수 항목을 확인해 주세요."),
            429: ("upstream_rate_limited", "대상 서비스의 요청 한도에 도달했습니다."),
        }.get(self.status_code, ("upstream_failed", "대상 서비스에서 요청을 처리하지 못했습니다."))
        self.payload = {"code": code, "message": message}


class UpstreamUnavailable(Exception):
    """업스트림 연결 실패/타임아웃(→ 502)."""


def _headers(*, user_admin: bool = False, hub_admin: bool = False) -> dict[str, str]:
    ordinary = settings.INTERNAL_SERVICE_TOKEN.get_secret_value()
    user_token = settings.USER_ADMIN_INTERNAL_TOKEN.get_secret_value()
    hub_token = settings.HUB_ADMIN_INTERNAL_TOKEN.get_secret_value()
    token = user_token if user_admin else hub_token if hub_admin else ordinary
    if user_admin or hub_admin:
        other = hub_token if user_admin else user_token
        if (user_admin and hub_admin) or not token.strip() or any(
            secrets.compare_digest(token.encode("utf-8"), value.encode("utf-8"))
            for value in (ordinary, other) if value
        ):
            raise UpstreamUnavailable("dedicated administration credential unavailable")
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


def _hub_admin_url(url: str) -> bool:
    candidate = httpx.URL(url)
    base = httpx.URL(settings.HUB_BASE_URL.rstrip("/") + "/internal/")
    return ((candidate.scheme, candidate.host, candidate.port) == (base.scheme, base.host, base.port)
            and candidate.path.startswith(base.path) and not candidate.userinfo and not candidate.fragment
            and "%" not in candidate.raw_path.decode("ascii")
            and re.fullmatch(r"kma/run-now|grids/[1-9][0-9]*|forbidden-zones(?:/[1-9][0-9]*)?",
                             candidate.path[len(base.path):]) is not None)


async def request_hub_admin_json(method: str, url: str, **kwargs) -> Any:
    """Hub 관리 전용 자격은 선택된 Hub의 명시된 관리 경로에만 보낸다."""
    if not _hub_admin_url(url):
        raise UpstreamUnavailable("invalid hub administration destination")
    return await request_json(method, url, _hub_admin=True, **kwargs)


async def request_json(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any | None = None,
    admin_actor: str | None = None,
    _user_admin: bool = False,
    _hub_admin: bool = False,
) -> Any:
    """내부 위임 호출. 2xx 면 JSON, 4xx/5xx 면 UpstreamError, 연결오류면
    UpstreamUnavailable 를 발생."""
    if _user_admin and not _user_admin_url(url):
        raise UpstreamUnavailable("invalid user administration destination")
    if not _user_admin and _user_admin_url(url):
        raise UpstreamUnavailable("user administration requires dedicated credential")
    if _hub_admin and not _hub_admin_url(url):
        raise UpstreamUnavailable("invalid hub administration destination")
    if not _hub_admin and _hub_admin_url(url):
        raise UpstreamUnavailable("hub administration requires dedicated credential")
    headers = _headers(user_admin=_user_admin, hub_admin=_hub_admin)
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
        raise UpstreamError(resp.status_code, None)

    if resp.status_code == 204 or not resp.content:
        return None
    try:
        return resp.json()
    except ValueError as exc:
        raise UpstreamUnavailable("invalid upstream response") from exc
