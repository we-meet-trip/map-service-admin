"""DB 접근 레이어 (cut 2).

map_admin 역할로 접속하는 SQLAlchemy async 엔진을 프로세스 단위 싱글톤으로
보유한다. 권한 계층상 hub_data 는 SELECT 만, admin_data 는 소유(RW)이다.
따라서 hub_data 로의 쓰기는 DB 권한에서 거부되고(읽기전용 보장), 감사/계정/
세션 쓰기는 admin_data 에서만 이뤄진다. 모든 쿼리는 스키마 완전수식한다.

hub/app/db/hub_db.py 의 엔진 구성 규약(pool 5+5, pre_ping, future)을 미러링하되
statement_timeout 을 connect_args 로 반영해 느린 조회 상한을 둔다.

호출 관계:
  - app.repo(hub_data RO) · app.accounts/app.audit(admin_data RW)
  - app.main 의 lifespan 종료 시 dispose_engine() 호출
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """async 엔진 싱글톤 접근자.

    최초 호출 시 settings.ADMIN_DATABASE_URL(map_admin DSN)로 엔진을 만든다.
    statement_timeout(ms)을 libpq options 로 주입해 모든 문장에 상한을 건다.
    """
    global _engine
    if _engine is None:
        timeout_ms = int(settings.DB_TIMEOUT_SEC * 1000)
        _engine = create_async_engine(
            settings.ADMIN_DATABASE_URL,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            future=True,
            connect_args={"options": f"-c statement_timeout={timeout_ms}"},
        )
    return _engine


async def dispose_engine() -> None:
    """엔진과 풀을 정리한다. app.main lifespan 종료 시 1회 호출."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
