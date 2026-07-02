"""hub_data 읽기전용 접근 레이어 (cut 1).

map_admin 역할(hub_data SELECT 권한만)로 접속하는 SQLAlchemy async 엔진을
프로세스 단위 싱글톤으로 보유한다. admin 은 어떤 스키마에도 쓰지 않으며,
모든 쿼리는 `hub_data.<table>` 로 완전수식(fully-qualified)하여 search_path
설정에 의존하지 않는다.

hub/app/db/hub_db.py 의 엔진 구성 규약(pool 5+5, pre_ping, future)을 미러링한다.

호출 관계:
  - app.repo 의 조회 함수가 get_engine().connect() 로 SELECT 실행
  - app.main 의 lifespan 종료 시 dispose_engine() 호출
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """읽기전용 async 엔진 싱글톤 접근자.

    최초 호출 시 settings.ADMIN_DATABASE_URL(map_admin DSN)로 엔진을 만든다.
    map_admin 은 hub_data 에 SELECT 권한만 가지므로, 실수로 쓰기 쿼리를
    보내더라도 DB 권한 계층에서 거부된다(이중 안전장치는 역할 권한).
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.ADMIN_DATABASE_URL,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


async def dispose_engine() -> None:
    """엔진과 풀을 정리한다. app.main lifespan 종료 시 1회 호출."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
