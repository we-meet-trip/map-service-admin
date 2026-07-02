"""Gemini 연결 상태 점검 (cut 1.5).

Gemini(generateContent)는 agent 소유이지만, 운영자가 "연결/키가 살아있는가"
를 볼 수 있도록 admin 이 **무료 메타 호출**(models.list)로 도달성+키 유효성만
확인한다. 생성 호출을 하지 않아 RPD/RPM 생성 quota 를 소모하지 않는다.

키 소유: admin 이 공유 .env 의 GEMINI_API_KEY 를 읽는다(사용자 확정). 미설정
이면 'configured=false' 로 표시한다. 예외/타임아웃은 흡수해 화면이 항상 렌더된다.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


async def check_gemini() -> dict[str, Any]:
    """Gemini models.list 로 연결 상태를 점검해 요약 dict 반환.

    반환 필드:
      configured : GEMINI_API_KEY 설정 여부
      ok         : 200 응답(연결+키 유효)
      http_status: 응답 코드(도달했으나 실패 시 401/403/400 등)
      latency_ms : 왕복 지연
      model_count: 200 일 때 반환된 모델 수
      detail     : 실패 요약(에러 유형 또는 상태 설명)
    """
    key = settings.GEMINI_API_KEY.get_secret_value()
    if not key:
        return {
            "configured": False,
            "ok": False,
            "detail": "GEMINI_API_KEY 미설정 (agent .env 공유)",
        }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                settings.GEMINI_MODELS_URL,
                params={"key": key},
                timeout=settings.GEMINI_TIMEOUT_SEC,
            )
        latency_ms = int(resp.elapsed.total_seconds() * 1000)
        if resp.status_code == 200:
            try:
                models = resp.json().get("models", [])
            except Exception:
                models = []
            return {
                "configured": True,
                "ok": True,
                "http_status": 200,
                "latency_ms": latency_ms,
                "model_count": len(models),
            }
        # 도달했으나 키 무효/권한/쿼터 등
        return {
            "configured": True,
            "ok": False,
            "http_status": resp.status_code,
            "latency_ms": latency_ms,
            "detail": f"HTTP {resp.status_code} (연결됨, 키/권한 확인 필요)",
        }
    except Exception as exc:  # DNS/연결 실패/타임아웃 → 미도달
        return {
            "configured": True,
            "ok": False,
            "http_status": None,
            "detail": f"미도달: {type(exc).__name__}",
        }
