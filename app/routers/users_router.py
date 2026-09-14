"""회원 조회 라우터 — user-BFF `/internal/admin/users` 위임.

목록은 마스킹된 요약, 상세는 원문 이메일이다. 목록·상세 열람을 모두 audit 에
기록한다 — 개인정보 취급자의 접속 기록은 보관 의무가 있는 자료다. 원문 이메일
상세는 읽기전용 운영자에게 주지 않는다. 전 라우트 require_operator 보호.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app import audit, bff_client
from app.routers.proxy_util import proxied
from app.security import require_operator


def _request_ip(request: Request) -> str | None:
    """요청을 받은 주소. 관문을 거치면 관문 주소이며 운영자 주소가 아니다."""
    return request.client.host if request.client else None

router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
    dependencies=[Depends(require_operator)],
)


@router.get("")
async def list_users(
    request: Request,
    query: str | None = Query(None),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    operator: str = Depends(require_operator),
) -> dict:
    """회원 목록(이메일 마스킹). BFF 위임. 열람 자체를 audit 에 기록한다."""
    result = await proxied(bff_client.list_users(query, page, size))
    await audit.record(
        operator,
        "users.list",
        target_service="user",
        target_schema="user_service",
        target_table="users",
        # 검색어 자체는 남기지 않는다 — 이메일이나 이름이 그대로 들어온다.
        params={"searched": query is not None, "page": page, "size": size},
        request_ip=_request_ip(request),
    )
    return result


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    request: Request,
    operator: str = Depends(require_operator),
) -> dict:
    """회원 상세(원문 이메일). 열람 자체를 audit 에 기록한다(결정 #7).

    읽기전용 운영자는 마스킹된 목록까지만 본다. 원문 이메일은 변경 권한과
    같은 등급으로 다룬다.
    """
    permissions = getattr(request.state, "operator_permissions", None) or {}
    if permissions.get("role") == "viewer":
        raise HTTPException(403, "read-only operator")
    result = await proxied(bff_client.get_user(user_id))
    await audit.record(
        operator,
        "users.view-detail",
        target_service="user",
        target_schema="user_service",
        target_table="users",
        target_id=str(user_id),
        request_ip=_request_ip(request),
    )
    return result
