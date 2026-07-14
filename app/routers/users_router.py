"""회원 조회 라우터 — user-BFF `/internal/admin/users` 위임.

목록은 마스킹된 요약, 상세는 원문 이메일(상세 열람은 audit 기록). 전 라우트
require_operator 보호.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app import audit, bff_client
from app.routers.proxy_util import proxied
from app.security import require_operator

router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
    dependencies=[Depends(require_operator)],
)


@router.get("")
async def list_users(
    query: str | None = Query(None),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
) -> dict:
    """회원 목록(이메일 마스킹). BFF 위임."""
    return await proxied(bff_client.list_users(query, page, size))


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    request: Request,
    operator: str = Depends(require_operator),
) -> dict:
    """회원 상세(원문 이메일). 열람 자체를 audit 에 기록한다(결정 #7)."""
    result = await proxied(bff_client.get_user(user_id))
    await audit.record(
        operator,
        "users.view-detail",
        target_service="user",
        target_schema="user_service",
        target_table="users",
        target_id=str(user_id),
        request_ip=request.client.host if request.client else None,
    )
    return result
