"""위임 호출 결과를 HTTP 응답으로 매핑하는 헬퍼.

업스트림(hub/BFF)의 상태코드를 그대로 전파하고, 연결 실패는 502 로 매핑한다.
"""
from __future__ import annotations

from typing import Any, Awaitable

from fastapi import HTTPException, status

from app.upstream import UpstreamError, UpstreamUnavailable


async def proxied(awaitable: Awaitable[Any]) -> Any:
    """위임 코루틴을 await 하고 예외를 HTTPException 으로 변환."""
    try:
        return await awaitable
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.payload
        ) from exc
    except UpstreamUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "upstream_unavailable", "message": "대상 서비스에 연결할 수 없습니다."},
        ) from exc
