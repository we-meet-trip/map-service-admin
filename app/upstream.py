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


def _headers() -> dict[str, str]:
    token = settings.INTERNAL_SERVICE_TOKEN.get_secret_value()
    return {"X-Internal-Token": token} if token else {}


async def request_json(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any | None = None,
) -> Any:
    """내부 위임 호출. 2xx 면 JSON, 4xx/5xx 면 UpstreamError, 연결오류면
    UpstreamUnavailable 를 발생."""
    try:
        async with httpx.AsyncClient(
            timeout=settings.INTERNAL_TIMEOUT_SEC
        ) as client:
            resp = await client.request(
                method, url, params=params, json=json, headers=_headers()
            )
    except httpx.HTTPError as exc:
        raise UpstreamUnavailable(str(exc)) from exc

    if resp.status_code >= 400:
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
