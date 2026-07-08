"""map-service-admin — 운영 모니터링 백엔드 (cut 1).

읽기전용 운영 모니터링 화면을 제공한다:
  - GET /            : HTML 대시보드(Jinja2). 폴링/예보/장소/헬스 표시.
  - GET /api/ops/*   : 위 데이터의 JSON.
  - GET /docs        : Swagger UI (Basic 보호).
  - GET /health      : liveness (인증 없음, compose healthcheck 용).

모든 운영자 접근은 단일 공유 HTTP Basic(app.security)으로 보호한다.
데이터는 hub_data 읽기전용 직접 조회(app.repo) + user/agent/hub 헬스
롤업(app.health_client). 다른 서비스에 쓰기/신규 엔드포인트 의존 없음.

hub/app/main.py 의 lifespan·/health 규약을 미러링한다.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app import gemini_client, health_client, repo
from app.config import settings
from app.db import dispose_engine
from app.security import require_operator

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_TEMPLATES = Jinja2Templates(directory=str(_TEMPLATE_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 수명주기 — 종료 시 DB 엔진 정리.

    엔진은 최초 쿼리에서 지연 생성되므로 startup 에서 별도 초기화는 없다.
    """
    logger.info("admin: startup")
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("admin: db disposed")


# 기본 /docs·/openapi 를 끄고, Basic 으로 보호한 커스텀 라우트로 대체한다.
app = FastAPI(
    title="map-service-admin",
    version="0.0.1-poc",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """liveness 헬스체크(인증 없음). compose/Dockerfile healthcheck 용.

    DB 를 건드리지 않는 순수 liveness 이므로, DB 미가용 상태여도 200 이다.
    실제 DB/다운스트림 상태는 대시보드/`/api/ops/*` 로 확인한다.
    """
    return {"status": "ok", "service": "admin"}


@app.get("/openapi.json", include_in_schema=False)
async def openapi(_: str = Depends(require_operator)) -> JSONResponse:
    """Basic 으로 보호한 OpenAPI 스키마."""
    return JSONResponse(
        get_openapi(title=app.title, version=app.version, routes=app.routes)
    )


@app.get("/docs", include_in_schema=False)
async def docs(_: str = Depends(require_operator)) -> HTMLResponse:
    """Basic 으로 보호한 Swagger UI."""
    return get_swagger_ui_html(
        openapi_url="/openapi.json", title=f"{app.title} · docs"
    )


# --- 읽기전용 운영 데이터 JSON (Basic 보호) ---


@app.get("/api/ops/polling")
async def api_polling(_: str = Depends(require_operator)) -> dict:
    """KMA 폴링 현황(활성/전체 격자, 예보별 최신 발표분·행수)."""
    return await repo.polling_status()


@app.get("/api/ops/forecast-rows")
async def api_forecast_rows(_: str = Depends(require_operator)) -> dict:
    """예보 3테이블 행수·만료시각 요약."""
    return {"tables": await repo.forecast_rows()}


@app.get("/api/ops/places-stats")
async def api_places_stats(_: str = Depends(require_operator)) -> dict:
    """장소 후보 출처별 집계."""
    return await repo.places_stats()


@app.get("/api/ops/health")
async def api_health(_: str = Depends(require_operator)) -> dict:
    """user/agent/hub 헬스 롤업."""
    return {"services": await health_client.rollup()}


@app.get("/api/ops/gemini")
async def api_gemini(_: str = Depends(require_operator)) -> dict:
    """Gemini 연결 상태(models.list 기반, 무료 메타 호출)."""
    return await gemini_client.check_gemini()


@app.get("/api/ops/monitoring")
async def api_monitoring(_: str = Depends(require_operator)) -> dict:
    """외부 모니터링 연동 슬롯 목록(Grafana 등, config 기반).

    admin 은 대상 도구를 기동하지 않고, env(MONITORING_PANELS)로 지정된
    URL 을 대시보드에서 iframe/링크로 연결만 한다. 미설정이면 빈 배열.
    """
    return {"panels": [p.model_dump() for p in settings.MONITORING_PANELS]}


# --- DB 뷰어 (hub_data 한정, Basic 보호) ---


@app.get("/api/db/tables")
async def api_db_tables(_: str = Depends(require_operator)) -> dict:
    """hub_data 테이블 목록 + 행수."""
    return {"schema": "hub_data", "tables": await repo.list_hub_tables()}


def _clamp_page(limit: int, offset: int) -> tuple[int, int]:
    """페이지 한도/오프셋을 안전 범위로 보정."""
    limit = max(1, min(limit, settings.DB_PAGE_SIZE_MAX))
    offset = max(0, offset)
    return limit, offset


async def _require_hub_table(table: str) -> None:
    """hub_data 실제 테이블만 허용(화이트리스트). 아니면 404."""
    if table not in await repo.hub_table_names():
        raise HTTPException(
            status_code=404, detail=f"hub_data table not found: {table}"
        )


@app.get("/api/db/tables/{table}")
async def api_db_rows(
    table: str,
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    _: str = Depends(require_operator),
) -> dict:
    """hub_data 특정 테이블의 행을 페이지네이션 조회(JSON)."""
    await _require_hub_table(table)
    lim, off = _clamp_page(limit, offset)
    return await repo.browse_table(table, lim, off)


# --- HTML 대시보드 (Basic 보호) ---


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request, operator: str = Depends(require_operator)
) -> HTMLResponse:
    """운영 모니터링 대시보드.

    hub_data 조회는 DB 미가용/빈 환경에서도 화면이 뜨도록 개별 try 로 감싸
    실패 섹션만 에러 메시지로 표시한다.
    """
    context: dict = {"operator": operator, "errors": {}}
    for key, coro in (
        ("polling", repo.polling_status()),
        ("forecast", repo.forecast_rows()),
        ("places", repo.places_stats()),
        ("db_tables", repo.list_hub_tables()),
    ):
        try:
            context[key] = await coro
        except Exception as exc:  # DB 미가용/권한 등 → 섹션만 에러 표시
            context[key] = None
            context["errors"][key] = f"{type(exc).__name__}: {exc}"
            logger.warning("dashboard %s query failed: %s", key, exc)
    # 헬스 롤업·Gemini 점검은 자체적으로 실패를 흡수하므로 그대로 사용
    context["health"] = await health_client.rollup()
    context["gemini"] = await gemini_client.check_gemini()
    # 외부 모니터링 연동 슬롯(Grafana 등)은 config 기반 — DB/네트워크 무관.
    context["monitoring"] = settings.MONITORING_PANELS
    return _TEMPLATES.TemplateResponse(request, "dashboard.html", context)


@app.get("/db/{table}", response_class=HTMLResponse, include_in_schema=False)
async def db_table_view(
    request: Request,
    table: str,
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    operator: str = Depends(require_operator),
) -> HTMLResponse:
    """hub_data 단일 테이블 행 브라우저(HTML, 페이지네이션)."""
    await _require_hub_table(table)
    lim, off = _clamp_page(limit, offset)
    data = await repo.browse_table(table, lim, off)
    ctx = {"operator": operator, **data}
    return _TEMPLATES.TemplateResponse(request, "table.html", ctx)
