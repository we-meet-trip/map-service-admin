"""운영자 인증 — 서버측 세션(HttpOnly 쿠키) 의존성 (cut 2).

admin_accounts(bcrypt) + admin_sessions 기반. 초기 "단일 공유 HTTP Basic" 안은
폐기되었다(§0-B-3). require_operator 는 요청 쿠키의 세션을 검증해 운영자
username 을 반환하고, 무효면 401 을 던진다. 감사 로그의 actor 가 이 username 이다.

전제: admin API 는 loopback(8002) 바인딩. SPA(admin-web)는 nginx same-origin
프록시로 접근하며, dev 는 CORS + credentials 로 쿠키를 주고받는다.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app import accounts, audit
from app.config import settings, environment_name


async def require_operator(request: Request) -> str:
    """세션 쿠키를 검증하고 운영자 username 을 반환한다.

    쿠키가 없거나 세션이 만료/무효면 401. 감사·라우터에서 actor 로 쓰인다.
    """
    session_id = request.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    operator = await accounts.operator_for_session(session_id)
    if operator is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    permissions = await accounts.permissions(operator)
    if permissions is None:
        raise HTTPException(401, "authentication required")
    role = permissions["role"]
    control_request = request.url.path.startswith("/api/v1/auth/") or request.url.path == "/api/v1/environments"
    if not control_request and role != "owner" and environment_name() not in permissions["allowed_environments"]:
        raise HTTPException(403, "environment access denied")
    request.state.operator_permissions = permissions
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if role == "viewer":
            raise HTTPException(403, "read-only operator")
        if request.headers.get("X-Map-Environment") != environment_name():
            raise HTTPException(403, "explicit environment header required")
        # 서비스 액션보다 먼저 감사 저장 성공을 확인한다.
        actor = f"admin_{int(permissions['id'])}" if request.url.path.startswith("/api/v1/moderation/") else operator
        request.state.audit_id = await audit.record(actor, "request.started",
            target_service="admin", target_id=request.url.path,
            params={"method": request.method}, status="started")
    return operator


async def require_owner(request: Request, operator: str = Depends(require_operator)) -> str:
    permissions = getattr(request.state, "operator_permissions", None) or await accounts.permissions(operator)
    if permissions is None or permissions["role"] != "owner":
        raise HTTPException(403, "owner access required")
    return operator
