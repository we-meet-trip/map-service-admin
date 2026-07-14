"""운영 액션 라우터 — hub/BFF 위임 + audit 기록 (cut 2).

모든 쓰기 액션은 소유 서비스 `/internal` 로 위임하고(경계 B9), 실행 후
admin_data.audit_logs 에 actor/params/before/after 를 기록한다. 전 라우트
require_operator 보호.

  POST   /api/v1/actions/kma/run-now?which=       (hub)
  PATCH  /api/v1/actions/grids/{grid_id}           (hub, before/after)
  GET/POST/PUT/DELETE /api/v1/actions/forbidden-zones[/{id}]  (hub)
  POST   /api/v1/actions/dlq/reprocess | /discard  (BFF)
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app import audit, bff_client, hub_client
from app.routers.proxy_util import proxied
from app.security import require_operator

router = APIRouter(
    prefix="/api/v1/actions",
    tags=["actions"],
    dependencies=[Depends(require_operator)],
)


class GridToggleBody(BaseModel):
    is_active: bool


class ForbiddenZoneBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=1000)
    geometry: dict[str, Any]


class DlqIdsBody(BaseModel):
    ids: list[str] = Field(..., min_length=1)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# --- KMA 강제 갱신 ---------------------------------------------------------


@router.post("/kma/run-now")
async def kma_run_now(
    request: Request,
    which: Literal["short", "mid", "housekeep"] = Query(...),
    operator: str = Depends(require_operator),
) -> dict:
    """KMA 폴링/하우스키핑 즉시 트리거(hub 위임). 409 중복은 그대로 전파."""
    result = await proxied(hub_client.kma_run_now(which))
    await audit.record(
        operator, "kma.run-now", target_service="hub",
        params={"which": which}, after=result, request_ip=_ip(request),
    )
    return result


# --- 구독 격자 토글 --------------------------------------------------------


@router.patch("/grids/{grid_id}")
async def toggle_grid(
    grid_id: int,
    body: GridToggleBody,
    request: Request,
    operator: str = Depends(require_operator),
) -> dict:
    """폴링 격자 활성/비활성 토글(hub 위임). before/after 를 audit 에 기록."""
    result = await proxied(hub_client.toggle_grid(grid_id, body.is_active))
    await audit.record(
        operator, "grids.toggle", target_service="hub",
        target_schema="hub_data", target_table="subscribed_grids",
        target_id=str(grid_id), params={"is_active": body.is_active},
        before=result.get("before"), after=result.get("after"),
        request_ip=_ip(request),
    )
    return result


# --- 금지구역 CRUD ---------------------------------------------------------


@router.get("/forbidden-zones")
async def list_zones() -> list:
    """금지구역 목록(hub 위임, 읽기 — audit 없음)."""
    return await proxied(hub_client.list_forbidden_zones())


@router.get("/forbidden-zones/{zone_id}")
async def get_zone(zone_id: int) -> dict:
    """금지구역 단건(hub 위임, 읽기)."""
    return await proxied(hub_client.get_forbidden_zone(zone_id))


@router.post("/forbidden-zones")
async def create_zone(
    body: ForbiddenZoneBody,
    request: Request,
    operator: str = Depends(require_operator),
) -> dict:
    """금지구역 생성(hub 위임)."""
    result = await proxied(
        hub_client.create_forbidden_zone(body.model_dump())
    )
    await audit.record(
        operator, "forbidden-zones.create", target_service="hub",
        target_schema="hub_data", target_table="forbidden_zones",
        target_id=str(result.get("zone_id")),
        params={"name": body.name}, after=result, request_ip=_ip(request),
    )
    return result


@router.put("/forbidden-zones/{zone_id}")
async def update_zone(
    zone_id: int,
    body: ForbiddenZoneBody,
    request: Request,
    operator: str = Depends(require_operator),
) -> dict:
    """금지구역 전체 교체(hub 위임)."""
    result = await proxied(
        hub_client.update_forbidden_zone(zone_id, body.model_dump())
    )
    await audit.record(
        operator, "forbidden-zones.update", target_service="hub",
        target_schema="hub_data", target_table="forbidden_zones",
        target_id=str(zone_id), params={"name": body.name},
        after=result, request_ip=_ip(request),
    )
    return result


@router.delete("/forbidden-zones/{zone_id}")
async def delete_zone(
    zone_id: int,
    request: Request,
    operator: str = Depends(require_operator),
) -> dict:
    """금지구역 삭제(hub 위임)."""
    result = await proxied(hub_client.delete_forbidden_zone(zone_id))
    await audit.record(
        operator, "forbidden-zones.delete", target_service="hub",
        target_schema="hub_data", target_table="forbidden_zones",
        target_id=str(zone_id), after=result, request_ip=_ip(request),
    )
    return result


# --- DLQ 재처리/폐기 -------------------------------------------------------


@router.post("/dlq/reprocess")
async def dlq_reprocess(
    body: DlqIdsBody,
    request: Request,
    operator: str = Depends(require_operator),
) -> dict:
    """DLQ 항목 재처리(BFF 위임)."""
    result = await proxied(bff_client.dlq_reprocess(body.ids))
    await audit.record(
        operator, "dlq.reprocess", target_service="user",
        params={"ids": body.ids}, after=result, request_ip=_ip(request),
    )
    return result


@router.post("/dlq/discard")
async def dlq_discard(
    body: DlqIdsBody,
    request: Request,
    operator: str = Depends(require_operator),
) -> dict:
    """DLQ 항목 폐기(BFF 위임)."""
    result = await proxied(bff_client.dlq_discard(body.ids))
    await audit.record(
        operator, "dlq.discard", target_service="user",
        params={"ids": body.ids}, after=result, request_ip=_ip(request),
    )
    return result
