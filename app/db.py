"""Independent control RW and target RO pools; no cross-role DSN fallback."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings, control_settings

_engines: dict[tuple[bool, str], AsyncEngine] = {}


def get_engine(*, control: bool = False) -> AsyncEngine:
    config = control_settings if control else settings
    url = (control_settings.ADMIN_CONTROL_DATABASE_URL or control_settings.ADMIN_DATABASE_URL) if control else config.ADMIN_DATABASE_URL
    if not url:
        raise HTTPException(503, "control database unavailable" if control else "target database not configured")
    key = (control, url)
    if key not in _engines:
        timeout_ms = max(1, int(config.DB_TIMEOUT_SEC * 1000))
        options = f"-c statement_timeout={timeout_ms} -c lock_timeout={timeout_ms}"
        if not control:
            options += " -c default_transaction_read_only=on"
        _engines[key] = create_async_engine(
            url, pool_size=3 if control else 2, max_overflow=0,
            pool_timeout=config.DB_TIMEOUT_SEC, pool_pre_ping=True, future=True,
            connect_args={"options": options, "connect_timeout": max(1, int(config.DB_TIMEOUT_SEC))},
        )
    return _engines[key]


def get_control_engine() -> AsyncEngine:
    return get_engine(control=True)


async def dispose_engine() -> None:
    """엔진과 풀을 정리한다. app.main lifespan 종료 시 1회 호출."""
    for engine in _engines.values():
        await engine.dispose()
    _engines.clear()
