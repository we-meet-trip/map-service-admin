"""인증 라우터 — 로그인/로그아웃/현재 운영자 (cut 2 세션).

POST /api/v1/auth/login  — 자격 검증 후 세션 쿠키 발급
POST /api/v1/auth/logout — 세션 삭제 + 쿠키 제거
GET  /api/v1/auth/me     — 현재 운영자(require_operator)
"""
from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel

from app import accounts
from app.config import settings
from app.security import require_operator

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _set_session_cookie(response: Response, session_id: str) -> None:
    """세션 쿠키를 HttpOnly·SameSite=Lax 로 설정."""
    response.set_cookie(
        key=settings.ADMIN_SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=settings.ADMIN_SESSION_COOKIE_SECURE,
        max_age=settings.ADMIN_SESSION_TTL_MIN * 60,
        path="/",
    )


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict[str, str]:
    """자격 검증 후 세션 발급. 실패 시 401."""
    account_id = await accounts.authenticate(body.username, body.password)
    if account_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    session_id, _ = await accounts.create_session(account_id)
    _set_session_cookie(response, session_id)
    return {"username": body.username}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> Response:
    """세션 삭제 + 쿠키 제거. 미로그인 상태여도 204."""
    session_id = request.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    await accounts.delete_session(session_id)
    response.delete_cookie(
        key=settings.ADMIN_SESSION_COOKIE_NAME, path="/"
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me")
async def me(operator: str = Depends(require_operator)) -> dict[str, str]:
    """현재 로그인한 운영자 username."""
    return {"username": operator}
