"""map-service-admin — 운영 콘솔 JSON API 서버 (cut 2).

SPA(admin-web)가 소비하는 순수 JSON API 를 제공한다(UI 없음). 인증은
admin_accounts(bcrypt) + 서버측 세션(HttpOnly 쿠키). 데이터 경로:
  - hub_data 읽기전용 직접(app.repo)
  - admin_data 소유 RW(app.accounts / app.audit)
  - Redis 진단 RO(app.redis_probe)
  - hub/BFF `/internal` 위임(app.hub_client / app.bff_client) — 경계 B9

라우터: auth · ops · db · users · jobs · actions · audit (전부 /api/v1).
/health 는 인증 없음(compose healthcheck), /docs·/openapi 는 세션 보호.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app import accounts
from app.config import settings
from app.db import dispose_engine
from app.routers import (
    actions_router,
    audit_router,
    auth_router,
    db_router,
    jobs_router,
    ops_router,
    users_router,
)
from app.security import require_operator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """수명주기 — 시작 시 최초 계정 시드, 종료 시 DB 엔진 정리.

    스키마 마이그레이션(alembic upgrade head)은 컨테이너 엔트리포인트가
    uvicorn 기동 전에 이미 수행한다(entrypoint.sh).
    """
    logger.info("admin: startup")
    try:
        await accounts.bootstrap_if_empty()
    except Exception as exc:  # DB 일시 장애 등 — 기동은 계속(로그인만 지연)
        logger.error("admin: account bootstrap failed: %s", exc)
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("admin: db disposed")


app = FastAPI(
    title="map-service-admin",
    version="0.2.0-cut2",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# CORS — dev SPA(Vite) 교차출처 + 세션 쿠키. 프로덕션은 nginx same-origin 이라
# ADMIN_CORS_ORIGINS 를 비워 두면 교차출처를 허용하지 않는다.
if settings.ADMIN_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ADMIN_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Prometheus 계측 → GET /metrics (인증 없음, map-net 내부 Prometheus 스크레이프).
Instrumentator().instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)

# /api/v1 도메인 라우터.
app.include_router(auth_router.router)
app.include_router(ops_router.router)
app.include_router(db_router.router)
app.include_router(users_router.router)
app.include_router(jobs_router.router)
app.include_router(actions_router.router)
app.include_router(audit_router.router)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """liveness(인증 없음). DB 를 건드리지 않는 순수 liveness."""
    return {"status": "ok", "service": "admin"}


@app.get("/openapi.json", include_in_schema=False)
async def openapi(_: str = Depends(require_operator)) -> JSONResponse:
    """세션 보호 OpenAPI 스키마."""
    return JSONResponse(
        get_openapi(title=app.title, version=app.version, routes=app.routes)
    )


@app.get("/docs", include_in_schema=False)
async def docs(_: str = Depends(require_operator)) -> HTMLResponse:
    """세션 보호 Swagger UI."""
    return get_swagger_ui_html(
        openapi_url="/openapi.json", title=f"{app.title} · docs"
    )
