# flake8: noqa: E501
"""create admin_data.admin_accounts and admin_data.admin_sessions.

Revision ID: 0002_create_admin_accounts_sessions
Revises: 0001_create_audit_logs
Create Date: 2026-07-13

운영자 인증(SR-ADMIN-008)을 위한 계정·세션 테이블을 만든다.
  - admin_accounts : 운영자 계정(username + bcrypt password_hash).
  - admin_sessions : 서버측 세션(HttpOnly 쿠키의 서버 대응 레코드).

인증 방식(§0-B-3): 초기 "단일 공유 HTTP Basic" 안은 폐기되고, 계정 기반
세션 인증으로 대체되었다. 세션은 Redis 논리 DB 를 새로 쓰지 않고 본
DB 테이블에 저장한다(§8.3 Redis 예약 보존).

최초 계정은 admin 앱 기동 시 ADMIN_BOOTSTRAP_USER / ADMIN_BOOTSTRAP_PASSWORD
로 시드된다(admin_accounts 가 비어 있을 때만 1회). 마이그레이션은 스키마만
만들고 계정 데이터는 넣지 않는다(비밀번호를 마이그레이션에 평문/고정 해시로
박지 않기 위함).
"""
from __future__ import annotations

from alembic import op

# revision id 는 alembic_version.version_num(varchar(32)) 상한을 넘지 않도록
# 짧게 유지한다("0002_create_admin_accounts_sessions"=35자 초과 → 축약).
revision: str = "0002_admin_accounts_sessions"
down_revision: str | None = "0001_create_audit_logs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """admin_accounts / admin_sessions 테이블과 인덱스를 생성한다.

    admin_data 스키마는 infra 가 생성·소유(map_admin). 여기서는 테이블만 만든다.
    """
    # username      : 로그인 식별자(UNIQUE).
    # password_hash : bcrypt 해시(60자). 평문 저장 금지.
    # is_active     : 비활성 계정은 로그인 거부(감사 이력은 보존).
    op.execute(
        """
        CREATE TABLE admin_data.admin_accounts (
          id             BIGSERIAL PRIMARY KEY,
          username       TEXT NOT NULL UNIQUE,
          password_hash  TEXT NOT NULL,
          is_active      BOOLEAN NOT NULL DEFAULT TRUE,
          created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # session_id : 앱이 생성하는 고엔트로피 세션 토큰(UUID). 쿠키 값과 대응.
    # account_id : 소유 운영자 계정. 계정 삭제 시 세션도 함께 삭제(CASCADE).
    # expires_at : 만료 시각. 조회 시 now() 초과면 무효 처리 후 삭제.
    op.execute(
        """
        CREATE TABLE admin_data.admin_sessions (
          session_id  UUID PRIMARY KEY,
          account_id  BIGINT NOT NULL
                        REFERENCES admin_data.admin_accounts(id) ON DELETE CASCADE,
          expires_at  TIMESTAMPTZ NOT NULL,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # 만료 세션 정리(스윕)용 + 계정별 세션 조회용 보조 인덱스.
    op.execute(
        "CREATE INDEX ix_admin_sessions_expires_at "
        "ON admin_data.admin_sessions (expires_at)"
    )
    op.execute(
        "CREATE INDEX ix_admin_sessions_account_id "
        "ON admin_data.admin_sessions (account_id)"
    )


def downgrade() -> None:
    """upgrade 의 역연산. 세션(FK 종속) → 계정 순으로 제거."""
    op.execute("DROP TABLE IF EXISTS admin_data.admin_sessions")
    op.execute("DROP TABLE IF EXISTS admin_data.admin_accounts")
