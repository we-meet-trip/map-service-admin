"""운영 감사 로그 (admin_data.audit_logs).

모든 운영 액션(격자 토글·KMA 강제갱신·금지구역 CRUD·DLQ 재처리·외부 API
수동 프로브·회원 상세 열람)의 환경과 결과를 중앙 저장소에 기록한다.
변경 요청은 실행 전 시작 기록을 남기며, 감사 저장 실패는 503을 반환한다.

호출 관계:
  - app.routers.actions_router / users_router / ops_router 의 각 액션 후 record
  - app.routers.audit_router → list_logs
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.db import get_control_engine as get_engine
from app.config import environment_name, control_settings
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _dumps(value: Any) -> str | None:
    """dict/list 를 JSON 문자열로. None 은 None(→ SQL NULL)."""
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"_unserializable": str(value)})


async def record(
    actor: str,
    action: str,
    *,
    target_service: str | None = None,
    target_schema: str | None = None,
    target_table: str | None = None,
    target_id: str | None = None,
    params: Any = None,
    before: Any = None,
    after: Any = None,
    status: str = "ok",
    request_ip: str | None = None,
) -> int:
    """audit_logs 에 1행 INSERT 하고 id 를 반환한다(실패 시 503).

    params/before/after 는 dict/list 를 받아 JSONB 로 저장한다.
    """
    sql = text(
        """
        INSERT INTO admin_data.audit_logs
          (actor, action, target_service, target_schema, target_table,
           target_id, params_json, before_json, after_json, status, request_ip)
        VALUES
          (:actor, :action, :tsvc, :tsch, :ttab, :tid,
           CAST(:params AS jsonb), CAST(:before AS jsonb),
           CAST(:after AS jsonb), :status, :ip)
        RETURNING id
        """
    )
    try:
        async with get_engine().begin() as conn:
            new_id = (
                await conn.execute(
                    sql,
                    {
                        "actor": actor,
                        "action": action,
                        "tsvc": f"{environment_name()}:{target_service or 'admin'}",
                        "tsch": target_schema,
                        "ttab": target_table,
                        "tid": target_id,
                        "params": _dumps(params),
                        "before": _dumps(before),
                        "after": _dumps(after),
                        "status": status,
                        "ip": request_ip,
                    },
                )
            ).scalar_one()
        return int(new_id)
    except Exception as exc:
        logger.error("audit record failed action=%s error=%s", action, type(exc).__name__)
        raise HTTPException(503, "audit unavailable; check operation status before retry") from exc


async def list_logs(
    *,
    actor: str | None = None,
    action: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """감사 로그 조회(필터 + 페이지네이션, 최신순)."""
    # 중앙 계정/감사 DB를 공유해도 다른 환경의 사용자 정보는 보이지 않는다.
    conds = ["(split_part(target_service, ':', 1) = :env OR (:legacy AND position(':' in coalesce(target_service,'')) = 0))"]
    params: dict[str, Any] = {"lim": limit, "off": offset,
        "env": environment_name(), "legacy": environment_name() == control_settings.ADMIN_ENVIRONMENT}
    if actor:
        conds.append("actor = :actor")
        params["actor"] = actor
    if action:
        conds.append("action = :action")
        params["action"] = action
    if from_ts is not None:
        conds.append("created_at >= :from_ts")
        params["from_ts"] = from_ts
    if to_ts is not None:
        conds.append("created_at <= :to_ts")
        params["to_ts"] = to_ts
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    async with get_engine().connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, actor, action, target_service, target_schema, "
                    "target_table, target_id, params_json, before_json, "
                    "after_json, status, request_ip, created_at "
                    f"FROM admin_data.audit_logs{where} "
                    "ORDER BY created_at DESC, id DESC LIMIT :lim OFFSET :off"
                ),
                params,
            )
        ).mappings().all()
        total = (
            await conn.execute(
                text(f"SELECT count(*) FROM admin_data.audit_logs{where}"),
                {k: v for k, v in params.items() if k not in ("lim", "off")},
            )
        ).scalar_one()
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def finish(request_id: int, http_status: int) -> None:
    """실행 전 기록에 최종 HTTP 결과를 연결한다. 응답 본문/비밀은 저장하지 않는다."""
    try:
        async with get_engine().begin() as conn:
            await conn.execute(text("UPDATE admin_data.audit_logs SET status=:status, after_json=CAST(:result AS jsonb) WHERE id=:id"),
                {"id": request_id, "status": "ok" if http_status < 400 else "error",
                 "result": json.dumps({"http_status": http_status})})
    except Exception as exc:
        logger.error("audit completion failed error=%s", type(exc).__name__)
        raise HTTPException(503, "audit unavailable; check operation status before retry") from exc
