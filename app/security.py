"""운영자 인증 — 단일 공유 HTTP Basic (현 단계 간단히).

.env 의 ADMIN_BASIC_USER / ADMIN_BASIC_PASSWORD 한 쌍으로 대시보드·/docs·API
를 공통 보호한다. 계정 테이블/bcrypt/세션 없이 단일 자격만 사용한다
(cut 2에서 필요 시 admin_accounts·감사 actor 로 확장).

전제: admin 컨테이너는 127.0.0.1 loopback 에만 바인딩되며 운영자 로컬에서만
접근한다. 평문 HTTP Basic 은 이 loopback 전제 하에서만 허용한다.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

_basic = HTTPBasic()


def require_operator(
    credentials: HTTPBasicCredentials = Depends(_basic),
) -> str:
    """HTTP Basic 자격을 상수시간 비교로 검증하고 운영자명을 반환.

    실패 시 401 + WWW-Authenticate: Basic (브라우저 로그인 프롬프트 유도).
    사용자명·비밀번호 모두 secrets.compare_digest 로 타이밍 공격을 방지한다.
    """
    expected_user = settings.ADMIN_BASIC_USER
    expected_pw = settings.ADMIN_BASIC_PASSWORD.get_secret_value()

    user_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"), expected_user.encode("utf-8")
    )
    pw_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"), expected_pw.encode("utf-8")
    )
    if not (user_ok and pw_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid operator credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
