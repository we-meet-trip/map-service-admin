"""Environment-scoped report queue, audited review and owner-only enforcement.

No serving database access. The User service owns reports and enforces actions.
Audit stores opaque account IDs and enum metadata, never report/message content.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import audit
from app.config import environment_name, settings
from app.security import require_operator
from app.upstream import UpstreamError, UpstreamUnavailable, request_user_admin_json as request_json

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])
Status = Literal["OPEN", "IN_REVIEW", "ACTIONED", "DISMISSED"]
Action = Literal["REVIEW", "DISMISS", "RESOLVE", "HIDE_CHAT_MESSAGE", "RESTRICT_CHAT", "LIFT_CHAT_RESTRICTION"]
REVIEW_ACTIONS = {"REVIEW", "DISMISS", "RESOLVE"}


class ReportReceipt(BaseModel):
    report_id: UUID
    status: Status
    content_type: Literal["CHAT_MESSAGE", "TRIP", "VISION", "REVIEW_SUMMARY"]
    reason: str = Field(max_length=32)
    resolution: str | None = Field(default=None, max_length=24)
    created_at: datetime
    updated_at: datetime


class ActionReceipt(BaseModel):
    action_id: UUID
    action: Action
    admin_actor: str = Field(max_length=96)
    restriction_hours: int | None = None
    created_at: datetime


class ReportDetail(BaseModel):
    report: ReportReceipt
    description: str | None = Field(default=None, max_length=1000)
    room_id: int | None = None
    message_seq: int | None = None
    schedule_id: int | None = None
    recommend_job_id: UUID | None = None
    current_message: str | None = Field(default=None, max_length=10000)
    actions: list[ActionReceipt] = Field(default_factory=list, max_length=1000)


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: UUID
    action: Action
    restriction_hours: int | None = Field(default=None, ge=1, le=720)


async def scope(request: Request, operator: str = Depends(require_operator)) -> dict:
    # Reads also require explicit selection, including owners. No default/fallback.
    if request.headers.get("X-Map-Environment") != environment_name():
        raise HTTPException(403, "explicit environment header required")
    permissions = request.state.operator_permissions
    return {"actor": f"admin_{int(permissions['id'])}", "role": permissions["role"]}


async def delegated(method: str, path: str, **kwargs):
    try:
        return await request_json(method, settings.USER_BASE_URL.rstrip("/") + "/internal/admin/moderation/reports" + path, **kwargs)
    except UpstreamError as exc:
        # Upstream bodies may include report text. Never reflect them on errors.
        code = exc.status_code if exc.status_code in {400, 403, 404, 409, 429, 503} else 502
        raise HTTPException(code, "moderation request could not be completed; refresh its status before retry") from None
    except UpstreamUnavailable:
        raise HTTPException(502, "moderation service unavailable; refresh its status before retry") from None


@router.get("/reports", response_model=list[ReportReceipt])
async def queue(status: Status = "OPEN", limit: int = Query(50, ge=1, le=100),
                operator: dict = Depends(scope)):
    result = await delegated("GET", "", params={"status": status, "limit": limit})
    try:
        if not isinstance(result, list) or len(result) > limit:
            raise ValueError("invalid moderation list")
        return [ReportReceipt.model_validate(row) for row in result]
    except (ValidationError, ValueError):
        raise HTTPException(502, "invalid moderation response") from None


@router.get("/reports/{report_id}", response_model=ReportDetail)
async def detail(report_id: UUID, response: Response, operator: dict = Depends(scope)):
    if operator["role"] not in {"operator", "owner"}:
        raise HTTPException(403, "report review permission required")
    # Audit availability is checked before disclosing sensitive content.
    await audit.record(operator["actor"], "moderation.view-detail", target_service="user",
                       target_table="moderation_reports", target_id=str(report_id))
    response.headers["Cache-Control"] = "no-store"
    result = await delegated("GET", f"/{report_id}")
    try:
        return ReportDetail.model_validate(result)
    except ValidationError:
        raise HTTPException(502, "invalid moderation response") from None


@router.post("/reports/{report_id}/actions", response_model=ReportReceipt)
async def act(report_id: UUID, body: ActionBody, operator: dict = Depends(scope)):
    required = {"owner", "operator"} if body.action in REVIEW_ACTIONS else {"owner"}
    if operator["role"] not in required:
        raise HTTPException(403, "moderation action permission required")
    if (body.action == "RESTRICT_CHAT") != (body.restriction_hours is not None):
        raise HTTPException(400, "restriction hours are required only for RESTRICT_CHAT")
    await audit.record(operator["actor"], "moderation.action-requested", target_service="user",
                       target_table="moderation_reports", target_id=str(report_id),
                       params={"action_id": str(body.action_id), "action": body.action,
                               "restriction_hours": body.restriction_hours}, status="started")
    result = await delegated("POST", f"/{report_id}/actions",
                             json=body.model_dump(mode="json", exclude_none=True),
                             admin_actor=operator["actor"])
    # No response body is copied to the control audit, even if User adds fields later.
    await audit.record(operator["actor"], "moderation.action-completed", target_service="user",
                       target_table="moderation_reports", target_id=str(report_id),
                       params={"action_id": str(body.action_id), "action": body.action})
    try:
        return ReportReceipt.model_validate(result)
    except ValidationError:
        raise HTTPException(502, "invalid moderation response; refresh status before retry") from None
