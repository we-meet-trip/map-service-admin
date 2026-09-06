"""서비스·인프라 헬스 롤업 (cut 2).

HTTP 서비스(user/agent/hub) + 인프라(postgres/redis) + 라우팅(osrm-foot/
osrm-bicycle)의 up/down·지연을 모은다. 다운스트림이 죽어 있어도 예외로
전파하지 않고 ok=false 로 집계한다(모니터링 화면이 부분 장애에도 렌더).

  - user  : {USER_BASE_URL}/actuator/health  (Spring, {"status":"UP"})
  - agent : {AGENT_BASE_URL}/health           (FastAPI, {"status":"ok"})
  - hub   : {HUB_BASE_URL}/health             (FastAPI, {"status":"ok"})
  - postgres : SELECT 1 (map_admin 엔진)
  - redis    : PING (ADMIN_REDIS_URL DB0)
  - osrm-*   : /nearest/v1/driving (base URL 설정 시에만; OSRM 은 /health 미제공)
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text

from app.config import settings
from app.db import get_engine

# (표시명, base_url, health path)
def _http_targets() -> list[tuple[str, str, str]]:
    return [
    ("user", settings.USER_BASE_URL, "/actuator/health"),
    ("agent", settings.AGENT_BASE_URL, "/health/ready"),
    ("hub", settings.HUB_BASE_URL, "/health/ready"),
]


def _is_up(body: Any) -> bool:
    """헬스 응답 본문에서 정상 여부 판정. Spring UP / FastAPI ok."""
    if isinstance(body, dict):
        status = str(body.get("status", "")).lower()
        if status in ("up", "ok"):
            return True
        if status:
            return False
    return False


async def _check_http(
    client: httpx.AsyncClient, name: str, base: str, path: str
) -> dict[str, Any]:
    """단일 HTTP 서비스 헬스 체크. 예외는 삼켜 ok=false."""
    url = f"{base.rstrip('/')}{path}"
    try:
        resp = await client.get(url, timeout=settings.HEALTH_TIMEOUT_SEC)
        latency_ms = int(resp.elapsed.total_seconds() * 1000)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return {
            "service": name,
            "kind": "service",
            "url": url,
            "ok": resp.status_code == 200 and _is_up(body),
            "http_status": resp.status_code,
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        return {
            "service": name, "kind": "service", "url": url, "ok": False,
            "http_status": None, "latency_ms": None,
            "error": type(exc).__name__,
        }


async def _check_postgres() -> dict[str, Any]:
    """postgres 헬스: SELECT 1 왕복 시간."""
    started = time.perf_counter()
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {
            "service": "postgres", "kind": "infra", "ok": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        return {
            "service": "postgres", "kind": "infra", "ok": False,
            "latency_ms": None, "error": type(exc).__name__,
        }


async def _check_redis() -> dict[str, Any]:
    """redis 헬스: PING 왕복 시간(DB0)."""
    started = time.perf_counter()
    r = aioredis.from_url(
        settings.ADMIN_REDIS_URL,
        socket_timeout=settings.REDIS_TIMEOUT_SEC,
        socket_connect_timeout=settings.REDIS_TIMEOUT_SEC,
    )
    try:
        await r.ping()
        return {
            "service": "redis", "kind": "infra", "ok": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        return {
            "service": "redis", "kind": "infra", "ok": False,
            "latency_ms": None, "error": type(exc).__name__,
        }
    finally:
        await r.aclose()


async def _check_osrm(
    client: httpx.AsyncClient, name: str, base: str
) -> dict[str, Any]:
    """OSRM 헬스: /nearest 1좌표 쿼리(비용 최소). base 미설정이면 unconfigured."""
    if not base:
        return {"service": name, "kind": "routing", "ok": None,
                "configured": False, "latency_ms": None}
    url = f"{base.rstrip('/')}/nearest/v1/driving/126.9780,37.5665?number=1"
    try:
        resp = await client.get(url, timeout=settings.HEALTH_TIMEOUT_SEC)
        latency_ms = int(resp.elapsed.total_seconds() * 1000)
        ok = False
        try:
            ok = resp.status_code == 200 and resp.json().get("code") == "Ok"
        except Exception:
            ok = False
        return {
            "service": name, "kind": "routing", "configured": True,
            "url": url, "ok": ok, "http_status": resp.status_code,
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        return {
            "service": name, "kind": "routing", "configured": True, "url": url,
            "ok": False, "http_status": None, "latency_ms": None,
            "error": type(exc).__name__,
        }


async def rollup() -> list[dict[str, Any]]:
    """전 대상(서비스 3 + 인프라 2 + 라우팅 2)을 동시 조회해 리스트로 반환."""
    async with httpx.AsyncClient() as client:
        http_checks = [
            _check_http(client, n, b, p) for (n, b, p) in _http_targets()
        ]
        osrm_checks = [
            _check_osrm(client, "osrm-foot", settings.OSRM_FOOT_BASE_URL),
            _check_osrm(
                client, "osrm-bicycle", settings.OSRM_BICYCLE_BASE_URL
            ),
        ]
        results = await asyncio.gather(
            *http_checks,
            _check_postgres(),
            _check_redis(),
            *osrm_checks,
        )
    return list(results)
