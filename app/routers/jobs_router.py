"""추천 작업/DLQ 조회 라우터 — user-BFF `/internal/admin` 위임(읽기).

DLQ 재처리/폐기(쓰기 액션)는 actions_router 에서 audit 와 함께 처리한다.
전 라우트 require_operator 보호.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app import bff_client
from app.routers.proxy_util import proxied
from app.security import require_operator

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_operator)],
)


@router.get("/stats")
async def job_stats() -> dict:
    """추천 작업 상태별 통계. BFF 위임."""
    return await proxied(bff_client.job_stats())


@router.get("")
async def list_jobs(
    status: str | None = Query(None),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
) -> dict:
    """추천 작업 목록(payload 제외). BFF 위임."""
    return await proxied(bff_client.list_jobs(status, page, size))


@router.get("/dlq")
async def list_dlq(limit: int = Query(50, ge=1, le=500)) -> list:
    """DLQ 최근 항목(최신순). BFF 위임."""
    return await proxied(bff_client.list_dlq(limit))
