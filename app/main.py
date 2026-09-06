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

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.exc import SQLAlchemyError

from app import accounts, audit
from app.config import settings, control_settings, select_environment, select_control, reset_environment
from app.db import dispose_engine
from app.routers import (
    actions_router,
    audit_router,
    auth_router,
    db_router,
    jobs_router,
    ops_router,
    users_router,
    operators_router,
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
    # Target configuration/outages cannot stop central authentication.
    await accounts.bootstrap_if_empty()
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


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request: Request, exc: SQLAlchemyError):
    # Exception text may include DSNs/query parameters. Never send it to clients.
    return JSONResponse({"detail": "database unavailable"}, status_code=503)


@app.middleware("http")
async def target_environment(request: Request, call_next):
    name = request.headers.get("X-Map-Environment") or request.query_params.get("environment") or control_settings.ADMIN_ENVIRONMENT
    control_request = (
        request.url.path.startswith(("/api/v1/auth/", "/api/v1/operators"))
        or request.url.path in {"/api/v1/environments", "/health", "/health/ready", "/metrics"}
    )
    if control_request:
        name = control_settings.ADMIN_ENVIRONMENT
    try:
        tokens = select_control() if control_request else select_environment(name)
    except ValueError:
        return JSONResponse({"detail": "unknown or incomplete environment"}, status_code=400)
    try:
        try:
            response = await call_next(request)
        except Exception:
            if request_id := getattr(request.state, "audit_id", None):
                await audit.finish(request_id, 500)
            raise
        if request_id := getattr(request.state, "audit_id", None):
            try:
                await audit.finish(request_id, response.status_code)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        response.headers["X-Map-Environment"] = name
        response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        reset_environment(tokens)

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
app.include_router(operators_router.router)
from app.routers import moderation_router
app.include_router(moderation_router.router)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """liveness(인증 없음). DB 를 건드리지 않는 순수 liveness."""
    return {"status": "ok", "service": "admin"}


@app.get("/health/ready", include_in_schema=False)
async def ready():
    from app.db import get_control_engine
    from sqlalchemy import text
    try:
        async with get_control_engine().connect() as conn:
            count = (await conn.execute(text("SELECT count(*) FROM admin_data.admin_accounts WHERE is_active AND role='owner'"))).scalar_one()
        return JSONResponse({"status": "ok" if count else "unavailable"}, status_code=200 if count else 503)
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)


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
