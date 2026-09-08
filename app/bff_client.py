"""user-BFF `/internal/admin` 위임 클라이언트 (회원/추천작업/DLQ).

admin 은 user_service 를 직접 조회하지 않고(경계 B9), user-BFF 의
/internal/admin/* 로 위임한다. 응답을 그대로 패스스루한다.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.upstream import request_user_admin_json as request_json


def _base() -> str:
    return settings.USER_BASE_URL.rstrip("/")


async def list_users(query: str | None, page: int, size: int) -> Any:
    params: dict[str, Any] = {"page": page, "size": size}
    if query:
        params["query"] = query
    return await request_json(
        "GET", f"{_base()}/internal/admin/users", params=params
    )


async def get_user(user_id: int) -> Any:
    return await request_json(
        "GET", f"{_base()}/internal/admin/users/{user_id}"
    )


async def job_stats() -> Any:
    return await request_json(
        "GET", f"{_base()}/internal/admin/recommend-jobs/stats"
    )


async def list_jobs(status: str | None, page: int, size: int) -> Any:
    params: dict[str, Any] = {"page": page, "size": size}
    if status:
        params["status"] = status
    return await request_json(
        "GET", f"{_base()}/internal/admin/recommend-jobs", params=params
    )


async def list_dlq(limit: int) -> Any:
    return await request_json(
        "GET", f"{_base()}/internal/admin/dlq", params={"limit": limit}
    )


async def dlq_reprocess(ids: list[str]) -> Any:
    return await request_json(
        "POST", f"{_base()}/internal/admin/dlq/reprocess", json={"ids": ids}
    )


async def dlq_discard(ids: list[str]) -> Any:
    return await request_json(
        "POST", f"{_base()}/internal/admin/dlq/discard", json={"ids": ids}
    )
