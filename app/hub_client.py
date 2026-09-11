"""hub `/internal` 위임 클라이언트 (KMA 강제갱신·격자 토글·금지구역 CRUD).

admin 은 hub_data 를 직접 쓰지 않고(경계 B9), hub 의 /internal/* 로 위임한다.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.upstream import request_hub_admin_json as request_json


def _base() -> str:
    return settings.HUB_BASE_URL.rstrip("/")


async def kma_run_now(which: str) -> Any:
    return await request_json(
        "POST", f"{_base()}/internal/kma/run-now", params={"which": which}
    )


async def toggle_grid(grid_id: int, is_active: bool) -> Any:
    return await request_json(
        "PATCH", f"{_base()}/internal/grids/{grid_id}",
        json={"is_active": is_active},
    )


async def list_forbidden_zones() -> Any:
    return await request_json("GET", f"{_base()}/internal/forbidden-zones")


async def get_forbidden_zone(zone_id: int) -> Any:
    return await request_json(
        "GET", f"{_base()}/internal/forbidden-zones/{zone_id}"
    )


async def create_forbidden_zone(body: dict[str, Any]) -> Any:
    return await request_json(
        "POST", f"{_base()}/internal/forbidden-zones", json=body
    )


async def update_forbidden_zone(zone_id: int, body: dict[str, Any]) -> Any:
    return await request_json(
        "PUT", f"{_base()}/internal/forbidden-zones/{zone_id}", json=body
    )


async def delete_forbidden_zone(zone_id: int) -> Any:
    return await request_json(
        "DELETE", f"{_base()}/internal/forbidden-zones/{zone_id}"
    )
