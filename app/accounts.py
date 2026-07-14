"""운영자 계정·세션 (admin_data) — bcrypt + 서버측 세션.

admin_accounts(bcrypt) 로 로그인하고 admin_sessions(HttpOnly 쿠키의 서버 대응
레코드)로 상태를 유지한다. 초기 "단일 공유 HTTP Basic" 안은 폐기되었다(§0-B-3).

호출 관계:
  - app.main lifespan → bootstrap_if_empty (최초 계정 시드)
  - app.routers.auth_router → authenticate / create_session / delete_session
  - app.security.require_operator → operator_for_session
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import text

from app.config import settings
from app.db import get_engine

logger = logging.getLogger(__name__)


def hash_password(plain: str) -> str:
    """bcrypt 해시(문자열) 생성."""
    return bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """bcrypt 검증. 해시 형식 오류 등은 False 로 흡수."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


async def bootstrap_if_empty() -> None:
    """admin_accounts 가 비어 있고 부트스트랩 자격이 설정돼 있으면 1회 시드한다.

    이미 계정이 하나라도 있으면 아무 것도 하지 않는다(멱등). 자격 미설정이면
    경고만 남기고 넘어간다(로그인 불가 상태 — 운영자가 자격을 채워야 한다).
    """
    user = settings.ADMIN_BOOTSTRAP_USER.strip()
    pw = settings.ADMIN_BOOTSTRAP_PASSWORD.get_secret_value()
    async with get_engine().begin() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM admin_data.admin_accounts")
            )
        ).scalar_one()
        if count > 0:
            return
        if not user or not pw:
            logger.warning(
                "admin_accounts empty and bootstrap creds not set — no "
                "operator can log in until an account exists"
            )
            return
        await conn.execute(
            text(
                "INSERT INTO admin_data.admin_accounts "
                "(username, password_hash) VALUES (:u, :h)"
            ),
            {"u": user, "h": hash_password(pw)},
        )
        logger.info("bootstrapped admin account username=%s", user)


async def authenticate(username: str, password: str) -> int | None:
    """자격 검증. 성공 시 account_id, 실패 시 None.

    비활성(is_active=false) 계정은 거부한다. 존재하지 않는 사용자도 더미 해시로
    검증해 사용자 존재 여부에 따른 타이밍 차이를 줄인다.
    """
    async with get_engine().connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id, password_hash, is_active "
                    "FROM admin_data.admin_accounts WHERE username = :u"
                ),
                {"u": username},
            )
        ).mappings().first()
    if row is None:
        # 타이밍 완화용 더미 검증(항상 실패).
        verify_password(password, "$2b$12$" + "x" * 53)
        return None
    if not row["is_active"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return int(row["id"])


async def create_session(account_id: int) -> tuple[str, datetime]:
    """새 세션을 만들고 (session_id, expires_at) 를 반환한다."""
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ADMIN_SESSION_TTL_MIN
    )
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO admin_data.admin_sessions "
                "(session_id, account_id, expires_at) VALUES (:s, :a, :e)"
            ),
            {"s": session_id, "a": account_id, "e": expires_at},
        )
    return session_id, expires_at


async def operator_for_session(session_id: str | None) -> str | None:
    """유효 세션이면 운영자 username, 아니면 None.

    만료 세션은 조회 시 삭제한다(지연 정리). session_id 가 UUID 형식이 아니면
    조회하지 않고 None(잘못된 쿠키 방어).
    """
    if not session_id:
        return None
    try:
        uuid.UUID(session_id)
    except (ValueError, TypeError):
        return None
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT s.expires_at, a.username, a.is_active "
                    "FROM admin_data.admin_sessions s "
                    "JOIN admin_data.admin_accounts a ON a.id = s.account_id "
                    "WHERE s.session_id = :s"
                ),
                {"s": session_id},
            )
        ).mappings().first()
        if row is None:
            return None
        expired = row["expires_at"] <= datetime.now(timezone.utc)
        if expired or not row["is_active"]:
            await conn.execute(
                text(
                    "DELETE FROM admin_data.admin_sessions "
                    "WHERE session_id = :s"
                ),
                {"s": session_id},
            )
            return None
        return str(row["username"])


async def delete_session(session_id: str | None) -> None:
    """세션 삭제(로그아웃). None/형식오류는 무시."""
    if not session_id:
        return
    try:
        uuid.UUID(session_id)
    except (ValueError, TypeError):
        return
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM admin_data.admin_sessions WHERE session_id = :s"
            ),
            {"s": session_id},
        )
