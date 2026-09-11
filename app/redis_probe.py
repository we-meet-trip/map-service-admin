"""Redis 진단 조회 (RO) — 스트림/DLQ/Gemini 쿼터/캐시 (cut 2).

admin 은 Redis 논리 DB 를 신규로 소유하지 않고, 기존 DB 를 진단 목적 RO 로
조회만 한다(§0-B-5 예외):
  - DB2 스트림: agent:jobs:done / agent:jobs:status / DLQ 길이, done 그룹 PEL
  - DB3 Gemini 쿼터: gemini:daily:{KST} 사용량 vs 상한, gemini:tokens 버킷
  - DB4 캐시: kakao:places:* / naver:blog:* / osrm:* 키 수(값 미접근)

모든 조회는 실패를 흡수해 error 키로 반환한다(모니터링이 부분 장애에도 렌더).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))


def _client(db: int) -> aioredis.Redis:
    """지정 논리 DB 로 접속하는 async Redis 클라이언트(decode_responses)."""
    base = settings.ADMIN_REDIS_URL.rstrip("/")
    return aioredis.from_url(
        f"{base}/{db}",
        decode_responses=True,
        socket_timeout=settings.REDIS_TIMEOUT_SEC,
        socket_connect_timeout=settings.REDIS_TIMEOUT_SEC,
    )


async def streams_overview() -> dict[str, Any]:
    """DB2 스트림 길이 + DLQ 길이 + done 그룹 PEL 요약."""
    if not settings.ADMIN_REDIS_URL:
        return {"error": "not_configured", "configured": False}
    r = _client(settings.REDIS_DB_STREAMS)
    try:
        done_len = await r.xlen(settings.STREAM_DONE)
        status_len = await r.xlen(settings.STREAM_STATUS)
        dlq_len = await r.xlen(settings.STREAM_DLQ)
        pending: dict[str, Any]
        try:
            summary = await r.xpending(
                settings.STREAM_DONE, settings.STREAM_GROUP
            )
            # redis-py: {'pending': n, 'min': id, 'max': id, 'consumers':[...]}
            s = summary if isinstance(summary, dict) else {}
            pending = {
                "pending": s.get("pending"),
                "min": s.get("min"),
                "max": s.get("max"),
            }
        except Exception as exc:  # NOGROUP 등
            pending = {"pending": None, "error": type(exc).__name__}
        return {
            "done": {"stream": settings.STREAM_DONE, "length": done_len},
            "status": {"stream": settings.STREAM_STATUS, "length": status_len},
            "dlq": {"stream": settings.STREAM_DLQ, "length": dlq_len},
            "group": settings.STREAM_GROUP,
            "pending": pending,
        }
    except Exception as exc:
        logger.warning("streams_overview failed: %s", type(exc).__name__)
        return {"error": type(exc).__name__}
    finally:
        await r.aclose()


async def gemini_quota() -> dict[str, Any]:
    """DB3 Gemini 일일 사용량(KST) vs 상한 + RPM 토큰 버킷 스냅샷."""
    if not settings.ADMIN_REDIS_URL:
        return {"error": "not_configured", "configured": False}
    r = _client(settings.REDIS_DB_RATELIMIT)
    try:
        today = datetime.now(_KST).strftime("%Y%m%d")
        daily_key = f"gemini:daily:{today}"
        used_raw = await r.get(daily_key)
        used = int(used_raw) if used_raw is not None else 0
        tokens = await r.hgetall("gemini:tokens")
        return {
            "date_kst": today,
            "daily_used": used,
            "daily_cap": settings.GEMINI_RPD_CAP,
            "daily_remaining": max(0, settings.GEMINI_RPD_CAP - used),
            "rpm_bucket": tokens or {},
        }
    except Exception as exc:
        logger.warning("gemini_quota failed: %s", type(exc).__name__)
        return {"error": type(exc).__name__}
    finally:
        await r.aclose()


async def _count_prefix(r: aioredis.Redis, pattern: str) -> int:
    """SCAN 으로 패턴 매칭 키 수를 센다(값 미접근, COUNT 500 배치)."""
    total = 0
    async for _ in r.scan_iter(match=pattern, count=500):
        total += 1
    return total


async def cache_stats() -> dict[str, Any]:
    """DB4 외부 API 캐시 키 수(kakao/naver/osrm)."""
    if not settings.ADMIN_REDIS_URL:
        return {"error": "not_configured", "configured": False}
    r = _client(settings.REDIS_DB_CACHE)
    try:
        return {
            "kakao_places": await _count_prefix(r, "kakao:places:*"),
            "naver_blog": await _count_prefix(r, "naver:blog:*"),
            "osrm": await _count_prefix(r, "osrm:*"),
        }
    except Exception as exc:
        logger.warning("cache_stats failed: %s", type(exc).__name__)
        return {"error": type(exc).__name__}
    finally:
        await r.aclose()
