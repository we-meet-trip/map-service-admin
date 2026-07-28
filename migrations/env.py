"""Alembic 환경 진입점 (map-service-admin, cut 2).

Alembic CLI(`alembic upgrade`/`downgrade`) 가 임포트하는 모듈이며,
hub/migrations/env.py 의 규약을 그대로 미러링하되 대상 스키마만 admin_data 다.

책임:
  1) alembic.ini 의 로깅 설정 적용
  2) 환경변수 ADMIN_DATABASE_URL(map_admin DSN)을 읽어 동기 드라이버 명세로
     치환 후 Alembic 의 sqlalchemy.url 옵션으로 주입
  3) offline / online 모드 분기 실행
  4) online 모드 시작 시 admin_data 스키마 보장 + alembic_version 테이블을
     admin_data 스키마 아래에 둠(다른 서비스 마이그레이션과 충돌 방지)

주의: ADMIN_DATABASE_URL 은 `postgresql+psycopg://...`(psycopg3) 형태로,
psycopg 드라이버는 sync/async 겸용이다. create_engine 은 동기로 동작하므로
async 토큰(+asyncpg/+psycopg_async)만 동기형으로 정규화한다.

revision 파일은 app 코드를 임포트하지 않으므로 target_metadata 는 None
(autogenerate 미사용, 모든 revision 은 op.execute raw SQL).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

dsn = os.environ.get("ADMIN_DATABASE_URL")
if not dsn:
    raise RuntimeError("ADMIN_DATABASE_URL 환경변수가 설정되지 않았다.")
# 동기 엔진용으로 async 드라이버 토큰만 정규화한다. psycopg3(+psycopg)는
# sync/async 겸용이라 그대로 두면 create_engine 이 동기로 사용한다.
sync_dsn = (
    dsn.replace("+psycopg_async", "+psycopg")
       .replace("postgresql+asyncpg", "postgresql+psycopg")
)
config.set_main_option("sqlalchemy.url", sync_dsn)

target_metadata = None

_VERSION_SCHEMA = "admin_data"


def run_migrations_offline() -> None:
    """offline 모드 — DB 접속 없이 SQL 문만 생성/실행한다.

    version_table 은 admin_data 스키마 아래에 두어 hub/agent/user 의
    마이그레이션과 충돌하지 않게 한다.
    """
    context.configure(
        url=sync_dsn,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version",
        version_table_schema=_VERSION_SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """online 모드 — 실제 DB 에 접속해 마이그레이션을 실행한다.

    동작:
      1) NullPool 임시 엔진으로 단일 connection 사용
      2) 트랜잭션 시작 직후 admin_data 스키마 보장(없으면 생성)
      3) alembic_version 을 admin_data 스키마 안에 두도록 설정
      4) 등록된 revision 순차 실행

    admin_data 스키마는 infra 가 생성·소유 이전한다(00-create-schemas.sql +
    10-admin.sh 의 ALTER SCHEMA ... OWNER TO map_admin). map_admin 은 DB 레벨
    CREATE 권한이 없으므로(최소 권한) 여기서 CREATE SCHEMA 를 하지 않는다 —
    이미 소유한 admin_data 안에 테이블만 생성한다.
    """
    engine = create_engine(sync_dsn, poolclass=pool.NullPool, future=True)
    with engine.begin() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version",
            version_table_schema=_VERSION_SCHEMA,
            include_schemas=True,
        )
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
