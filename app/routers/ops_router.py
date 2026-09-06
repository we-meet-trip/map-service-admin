"""운영 데이터 라우터 — 헬스·폴링·예보·장소·Gemini·모니터링·스트림·외부API.

전 라우트 require_operator 보호. 외부 API 프로브는 실쿼터 소모가 있으므로
GET 자동 폴링에 섞지 않고 명시적 POST 프로브로만 수행하며 audit 를 남긴다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app import (
    audit,
    external_status,
    gemini_client,
    health_client,
    redis_probe,
    repo,
)
from app.config import settings
from app.security import require_operator

router = APIRouter(
    prefix="/api/v1/ops",
    tags=["ops"],
    dependencies=[Depends(require_operator)],
)


@router.get("/health")
async def ops_health() -> dict:
    """서비스+인프라+라우팅 헬스 롤업."""
    return {"services": await health_client.rollup()}


@router.get("/polling")
async def ops_polling() -> dict:
    """KMA 폴링 현황(격자·예보 최신 발표분·행수)."""
    return await repo.polling_status()


@router.get("/forecast-rows")
async def ops_forecast_rows() -> dict:
    """예보 3테이블 행수·만료시각 요약."""
    return {"tables": await repo.forecast_rows()}


@router.get("/places-stats")
async def ops_places_stats() -> dict:
    """장소 후보 출처별 집계."""
    return await repo.places_stats()


@router.get("/gemini")
async def ops_gemini() -> dict:
    """Gemini 연결 상태(models.list) + 일일 쿼터(Redis DB3)."""
    conn = await gemini_client.check_gemini()
    quota = await redis_probe.gemini_quota()
    return {"connection": conn, "quota": quota}


@router.get("/streams")
async def ops_streams() -> dict:
    """추천 잡 스트림/DLQ/PEL 요약(Redis DB2)."""
    return await redis_probe.streams_overview()


@router.get("/external")
async def ops_external() -> dict:
    """외부 API 6종 상태(configured/캐시/쿼터). 라이브 호출 없음."""
    return await external_status.status_snapshot()


@router.post("/external/{provider}/probe")
async def ops_external_probe(
    provider: str,
    request: Request,
    operator: str = Depends(require_operator),
) -> dict:
    """외부 API provider 연결 프로브(1회). 실행 결과를 audit 에 기록한다."""
    if provider not in external_status.PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown provider: {provider}",
        )
    result = await external_status.probe(provider)
    audit_id = await audit.record(
        operator,
        "external.probe",
        target_service=provider,
        target_id=provider,
        after=result,
        status="ok" if result.get("ok") else "error",
        request_ip=request.client.host if request.client else None,
    )
    return {**result, "audit_id": audit_id}


@router.get("/monitoring")
async def ops_monitoring() -> dict:
    """외부 모니터링 연동 슬롯 목록(Grafana 등, config 기반)."""
    return {"panels": [p.model_dump() for p in settings.MONITORING_PANELS]}


@router.get("/overview")
async def ops_overview() -> dict:
    """대시보드 첫 화면용 집계(헬스+폴링+Gemini+스트림). 섹션별 실패 격리."""
    out: dict = {"errors": {}}
    out["health"] = await health_client.rollup()
    for key, coro in (
        ("polling", repo.polling_status()),
        ("places", repo.places_stats()),
    ):
        try:
            out[key] = await coro
        except Exception as exc:  # DB 미가용 등 → 섹션만 에러
            out[key] = None
            out["errors"][key] = type(exc).__name__
    out["gemini_quota"] = await redis_probe.gemini_quota()
    out["streams"] = await redis_probe.streams_overview()
    for key in ("gemini_quota", "streams"):
        if isinstance(out[key], dict) and out[key].get("error"):
            out["errors"][key] = str(out[key]["error"])
            out[key] = None
    return out
