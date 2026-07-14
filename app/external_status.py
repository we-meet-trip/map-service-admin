"""외부 API 상태·수동 프로브 (cut 2).

6종 provider(KMA·Kakao·Naver·Durunubi·OSRM·Gemini)의 상태를 표시하고,
운영자가 명시적으로 요청할 때만 연결 프로브를 수행한다(자동 폴링 금지 —
실쿼터 소모 방지). 키 값은 마스킹해서만 노출한다.

  - status_snapshot(): 라이브 호출 없이 configured/캐시/쿼터만 반환
  - probe(provider): 해당 provider 에 최소 연결 요청 1회(라우터가 audit 기록)

hub 의 엔드포인트/인증 규약(serviceKey 쿼리, KakaoAK/Naver 헤더)을 미러링한다.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app import gemini_client, redis_probe
from app.config import settings

logger = logging.getLogger(__name__)

PROVIDERS = ["kma", "kakao", "naver", "durunubi", "osrm", "gemini"]


def _mask(secret: str) -> str:
    """비밀값 마스킹: 앞4·뒤2만 노출. 짧으면 '***'. 빈 값은 '(unset)'."""
    if not secret:
        return "(unset)"
    if len(secret) <= 6:
        return "***"
    return f"{secret[:4]}…{secret[-2:]}"


async def status_snapshot() -> dict[str, Any]:
    """라이브 호출 없이 provider 별 상태(configured/키마스킹) + 캐시/쿼터."""
    kakao = settings.KAKAO_REST_API_KEY.get_secret_value()
    kma = settings.KMA_SERVICE_KEY.get_secret_value()
    tour = settings.TOUR_API_SERVICE_KEY.get_secret_value()
    nid = settings.NAVER_CLIENT_ID.get_secret_value()
    nsec = settings.NAVER_CLIENT_SECRET.get_secret_value()
    gem = settings.GEMINI_API_KEY.get_secret_value()

    cache = await redis_probe.cache_stats()
    quota = await redis_probe.gemini_quota()

    providers = [
        {
            "provider": "kma", "label": "기상청 단기/중기예보",
            "configured": bool(kma), "key_masked": _mask(kma),
        },
        {
            "provider": "kakao", "label": "카카오 로컬(장소)",
            "configured": bool(kakao), "key_masked": _mask(kakao),
            "cache_keys": cache.get("kakao_places"),
        },
        {
            "provider": "naver", "label": "네이버 블로그(리뷰)",
            "configured": bool(nid and nsec), "key_masked": _mask(nid),
            "cache_keys": cache.get("naver_blog"),
        },
        {
            "provider": "durunubi", "label": "두루누비(코스)",
            "configured": bool(tour), "key_masked": _mask(tour),
        },
        {
            "provider": "osrm", "label": "OSRM 라우팅",
            "configured": bool(settings.OSRM_FOOT_BASE_URL),
            "cache_keys": cache.get("osrm"),
        },
        {
            "provider": "gemini", "label": "Gemini LLM",
            "configured": bool(gem), "key_masked": _mask(gem),
            "quota": quota,
        },
    ]
    return {"providers": providers}


async def probe(provider: str) -> dict[str, Any]:
    """provider 에 최소 연결 요청 1회. {provider, ok, latency_ms, detail}."""
    if provider not in PROVIDERS:
        return {
            "provider": provider, "ok": False, "detail": "unknown provider",
        }
    started = time.perf_counter()
    try:
        if provider == "gemini":
            res = await gemini_client.check_gemini()
            ok = bool(res.get("ok"))
            detail = res
        else:
            async with httpx.AsyncClient(
                timeout=settings.EXTERNAL_PROBE_TIMEOUT_SEC
            ) as client:
                ok, detail = await _probe_http(client, provider)
    except Exception as exc:
        ok, detail = False, {"error": type(exc).__name__, "msg": str(exc)}
    return {
        "provider": provider,
        "ok": ok,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "detail": detail,
    }


async def _probe_http(
    client: httpx.AsyncClient, provider: str
) -> tuple[bool, Any]:
    """provider 별 최소 HTTP 프로브. (ok, detail) 반환."""
    if provider == "kakao":
        return await _probe_kakao(client)
    if provider == "naver":
        return await _probe_naver(client)
    if provider == "kma":
        return await _probe_kma(client)
    if provider == "durunubi":
        return await _probe_durunubi(client)
    if provider == "osrm":
        return await _probe_osrm(client)
    return False, {"error": "no probe"}


async def _probe_kakao(client: httpx.AsyncClient) -> tuple[bool, Any]:
    key = settings.KAKAO_REST_API_KEY.get_secret_value()
    if not key:
        return False, {"error": "KAKAO_REST_API_KEY unset"}
    resp = await client.get(
        "https://dapi.kakao.com/v2/local/search/keyword.json",
        params={"query": "서울", "size": 1},
        headers={"Authorization": f"KakaoAK {key}"},
    )
    return resp.status_code == 200, {"http_status": resp.status_code}


async def _probe_naver(client: httpx.AsyncClient) -> tuple[bool, Any]:
    nid = settings.NAVER_CLIENT_ID.get_secret_value()
    nsec = settings.NAVER_CLIENT_SECRET.get_secret_value()
    if not (nid and nsec):
        return False, {"error": "NAVER credentials unset"}
    resp = await client.get(
        "https://openapi.naver.com/v1/search/blog.json",
        params={"query": "서울", "display": 1},
        headers={"X-Naver-Client-Id": nid, "X-Naver-Client-Secret": nsec},
    )
    return resp.status_code == 200, {"http_status": resp.status_code}


async def _probe_kma(client: httpx.AsyncClient) -> tuple[bool, Any]:
    key = settings.KMA_SERVICE_KEY.get_secret_value()
    if not key:
        return False, {"error": "KMA_SERVICE_KEY unset"}
    # 어제 05시 발표분을 조회. NO_DATA(03)도 키 정상으로 간주(연결/키 검증 목적).
    from datetime import datetime, timedelta, timezone

    base = datetime.now(timezone(timedelta(hours=9))) - timedelta(days=1)
    resp = await client.get(
        "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/"
        "getVilageFcst",
        params={
            "serviceKey": key, "dataType": "JSON", "numOfRows": 1,
            "pageNo": 1, "base_date": base.strftime("%Y%m%d"),
            "base_time": "0500", "nx": 60, "ny": 127,
        },
    )
    code = None
    try:
        code = resp.json()["response"]["header"]["resultCode"]
    except Exception:
        code = None
    # 00=정상, 03=NO_DATA → 키/연결 OK. 그 외(인증오류 등)는 실패.
    ok = resp.status_code == 200 and code in ("00", "03")
    return ok, {"http_status": resp.status_code, "resultCode": code}


async def _probe_durunubi(client: httpx.AsyncClient) -> tuple[bool, Any]:
    key = settings.TOUR_API_SERVICE_KEY.get_secret_value()
    if not key:
        return False, {"error": "TOUR_API_SERVICE_KEY unset"}
    resp = await client.get(
        "https://apis.data.go.kr/B551011/Durunubi/routeList",
        params={
            "serviceKey": key, "MobileOS": "ETC",
            "MobileApp": "map-service", "_type": "json",
            "numOfRows": 1, "pageNo": 1,
        },
    )
    code = None
    try:
        code = resp.json()["response"]["header"]["resultCode"]
    except Exception:
        code = None
    ok = resp.status_code == 200 and code in ("0000", "00")
    return ok, {"http_status": resp.status_code, "resultCode": code}


async def _probe_osrm(client: httpx.AsyncClient) -> tuple[bool, Any]:
    base = settings.OSRM_FOOT_BASE_URL
    if not base:
        return False, {"error": "OSRM_FOOT_BASE_URL unset"}
    resp = await client.get(
        f"{base.rstrip('/')}/nearest/v1/driving/126.9780,37.5665?number=1"
    )
    ok = False
    try:
        ok = resp.status_code == 200 and resp.json().get("code") == "Ok"
    except Exception:
        ok = False
    return ok, {"http_status": resp.status_code}
