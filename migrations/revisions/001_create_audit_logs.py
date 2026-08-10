# flake8: noqa: E501
"""create admin_data.audit_logs.

Revision ID: 0001_create_audit_logs
Revises:
Create Date: 2026-07-13

운영자 행위 감사 로그를 영속 저장하는 admin_data.audit_logs 테이블을 만든다
(SR-SYS-006 / SR-ADMIN-007 실현). 모든 운영 액션(격자 토글·KMA 강제갱신·
금지구역 CRUD·DLQ 재처리·외부 API 수동 프로브·회원 상세 열람)이 실행 후
본 테이블에 1행을 남긴다.

경계 원칙: admin 의 쓰기는 admin_data 단일 스키마 트랜잭션으로
한정한다. target_* 는 타 스키마/서비스 대상을 외래키 없이 논리 텍스트로
참조한다(cross-schema FK 없음).
"""
from __future__ import annotations

from alembic import op

# Alembic revision 체인 식별자. admin_data 마이그레이션의 최초 revision.
revision: str = "0001_create_audit_logs"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """audit_logs 테이블과 조회 인덱스를 생성한다.

    admin_data 스키마는 infra 가 생성·소유(00-create-schemas.sql + 10-admin.sh).
    map_admin 은 DB 레벨 CREATE 권한이 없으므로 여기서 스키마를 만들지 않고,
    소유한 admin_data 안에 테이블만 생성한다.
    """
    # actor        : 액션을 수행한 운영자 username(세션 계정). 익명 불가.
    # action       : 액션 종류(예: "grids.toggle", "kma.run-now",
    #                "forbidden-zones.create", "dlq.reprocess",
    #                "external.probe", "users.view-detail").
    # target_*     : 대상 식별(논리 텍스트 참조, FK 없음). 없으면 NULL.
    # params_json  : 요청 파라미터 스냅샷.
    # before_json  : 변경 전 상태(멱등/토글류에서 채움, 그 외 NULL).
    # after_json   : 변경 후 상태(그 외 NULL).
    # status       : "ok" | "error" | "denied" 등 결과.
    # request_ip   : 요청 클라이언트 IP(감사 추적용).
    op.execute(
        """
        CREATE TABLE admin_data.audit_logs (
          id              BIGSERIAL PRIMARY KEY,
          actor           TEXT NOT NULL,
          action          TEXT NOT NULL,
          target_service  TEXT,
          target_schema   TEXT,
          target_table    TEXT,
          target_id       TEXT,
          params_json     JSONB,
          before_json     JSONB,
          after_json      JSONB,
          status          TEXT NOT NULL,
          request_ip      TEXT,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # 최근순 조회(감사 화면 기본 정렬)용.
    op.execute(
        "CREATE INDEX ix_audit_logs_created_at "
        "ON admin_data.audit_logs (created_at DESC)"
    )
    # 운영자별/액션별 필터용 보조 인덱스.
    op.execute("CREATE INDEX ix_audit_logs_actor ON admin_data.audit_logs (actor)")
    op.execute("CREATE INDEX ix_audit_logs_action ON admin_data.audit_logs (action)")


def downgrade() -> None:
    """upgrade 의 역연산. 테이블만 제거하고 스키마는 남겨 둔다."""
    op.execute("DROP TABLE IF EXISTS admin_data.audit_logs")
