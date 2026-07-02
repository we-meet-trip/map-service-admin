"""서비스 헬스 롤업 (cut 1).

user/agent/hub 의 헬스 엔드포인트를 httpx 로 호출해 up/down·지연을 모은다.
map-net 안에서는 컨테이너명+컨테이너포트로 도달한다:
  - user  : {USER_BASE_URL}/actuator/health  (Spring, {"status":"UP"})
  - agent : {AGENT_BASE_URL}/health           (FastAPI, {"status":"ok"})
  - hub   : {HUB_BASE_URL}/health             (FastAPI, {"status":"ok"})

다운스트림이 죽어 있어도 예외로 전파하지 않고 ok=false 로 집계한다
(모니터링 화면이 부분 장애에도 항상 렌더되도록).
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import settings

# (표시명, base_url, health path, 정상 판정 함수)
_TARGETS: list[tuple[str, str, str]] = [
    ("user", settings.USER_BASE_URL, "/actuator/health"),
    ("agent", settings.AGENT_BASE_URL, "/health"),
    ("hub", settings.HUB_BASE_URL, "/health"),
]


def _is_up(service: str, body: Any) -> bool:
    """서비스별 헬스 응답 본문에서 정상 여부를 판정.

    Spring(user)은 {"status":"UP"}, FastAPI(agent/hub)는 {"status":"ok"}.
    형식이 예상과 달라도 200 이면 최소 reachable 로 간주하되 status 필드가
    있으면 그것을 우선한다.
    """
    if isinstance(body, dict):
        status = str(body.get("status", "")).lower()
        if status in ("up", "ok"):
            return True
        if status:  # status 필드가 있는데 up/ok 가 아니면 down
            return False
    return True  # 200 이지만 형식 미상 → reachable 로 처리


async def _check(
    client: httpx.AsyncClient, name: str, base: str, path: str
) -> dict[str, Any]:
    """단일 서비스 헬스 체크. 예외는 삼켜 ok=false 로 반환."""
    url = f"{base.rstrip('/')}{path}"
    try:
        resp = await client.get(url, timeout=settings.HEALTH_TIMEOUT_SEC)
        latency_ms = int(resp.elapsed.total_seconds() * 1000)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        ok = resp.status_code == 200 and _is_up(name, body)
        return {
            "service": name,
            "url": url,
            "ok": ok,
            "http_status": resp.status_code,
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # 연결 실패/타임아웃 등 → down
        return {
            "service": name,
            "url": url,
            "ok": False,
            "http_status": None,
            "latency_ms": None,
            "error": type(exc).__name__,
        }


async def rollup() -> list[dict[str, Any]]:
    """user/agent/hub 헬스를 동시에 조회해 리스트로 반환."""
    async with httpx.AsyncClient() as client:
        return list(
            await asyncio.gather(
                *(_check(client, n, b, p) for (n, b, p) in _TARGETS)
            )
        )
