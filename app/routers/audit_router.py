"""감사 로그 조회 라우터 (admin_data.audit_logs).

GET /api/v1/audit?actor=&action=&from=&to=&page=&size=
require_operator 보호. 최신순 페이지네이션.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app import audit
from app.config import settings
from app.security import require_operator

router = APIRouter(
    prefix="/api/v1/audit",
    tags=["audit"],
    dependencies=[Depends(require_operator)],
)


@router.get("")
async def list_audit(
    actor: str | None = Query(None),
    action: str | None = Query(None),
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
) -> dict:
    """감사 로그 조회(필터 + 페이지네이션)."""
    limit = min(limit, settings.DB_PAGE_SIZE_MAX)
    return await audit.list_logs(
        actor=actor,
        action=action,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )
