"""admin cut 1 스모크 테스트.

DB 를 건드리지 않는 경로(인증 게이팅 + liveness)만 검증한다. hub_data 조회
경로는 실제 DB/시드가 필요하므로 통합 검증(README §검증)에서 다룬다.

Settings 가 ADMIN_DATABASE_URL 을 필수로 요구하므로 app 임포트 전에 환경변수를
주입한다.
"""
from __future__ import annotations

import base64
import os

os.environ.setdefault(
    "ADMIN_DATABASE_URL", "postgresql+psycopg://map_admin:x@localhost:5432/map"
)
os.environ.setdefault("ADMIN_BASIC_USER", "admin")
os.environ.setdefault("ADMIN_BASIC_PASSWORD", "secret")

from fastapi.testclient import TestClient  # noqa: E402

from app import gemini_client, health_client, repo  # noqa: E402,F401
from app.main import app  # noqa: E402

client = TestClient(app)


def _basic(user: str, pw: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_health_no_auth() -> None:
    """/health 는 인증 없이 200 (liveness)."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "admin"}


def test_ops_requires_basic() -> None:
    """/api/ops/* 는 Basic 없으면 401."""
    r = client.get("/api/ops/health")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Basic"


def test_docs_requires_basic() -> None:
    """/docs 는 Basic 없으면 401."""
    assert client.get("/docs").status_code == 401


def test_wrong_credentials_rejected() -> None:
    """잘못된 자격은 401."""
    r = client.get("/api/ops/health", headers=_basic("admin", "wrong"))
    assert r.status_code == 401


def test_health_rollup_with_auth() -> None:
    """올바른 Basic + 헬스 롤업(다운스트림 미가용이어도 200, ok=false 집계)."""
    r = client.get("/api/ops/health", headers=_basic("admin", "secret"))
    assert r.status_code == 200
    services = {s["service"] for s in r.json()["services"]}
    assert services == {"user", "agent", "hub"}


def test_dashboard_renders_with_mocked_data(monkeypatch) -> None:
    """대시보드(/)가 hub_data 조회를 목킹한 상태에서 HTML 로 렌더된다(DB 불필요)."""
    from app import health_client, repo

    async def _polling():
        return {
            "grids": {"active_grids": 18, "total_grids": 18},
            "short_term": {"last_base_at": "2026-07-01T05:00", "rows": 42},
            "mid_land": {"last_tm_fc": None, "rows": 0},
            "mid_temp": {"last_tm_fc": None, "rows": 0},
        }

    async def _forecast():
        return [{"table": "short_term_forecast", "rows": 42,
                 "min_expires_at": None, "max_expires_at": None}]

    async def _places():
        return {"total": 2, "by_source": [{"source": "durunubi", "rows": 2}]}

    async def _tables():
        return [{"table": "places", "rows": 2},
                {"table": "subscribed_grids", "rows": 3}]

    async def _rollup():
        return [{"service": "hub", "url": "x", "ok": True,
                 "http_status": 200, "latency_ms": 5}]

    async def _gemini():
        return {"configured": True, "ok": True, "http_status": 200,
                "latency_ms": 42, "model_count": 47}

    from app import gemini_client
    monkeypatch.setattr(repo, "polling_status", _polling)
    monkeypatch.setattr(repo, "forecast_rows", _forecast)
    monkeypatch.setattr(repo, "places_stats", _places)
    monkeypatch.setattr(repo, "list_hub_tables", _tables)
    monkeypatch.setattr(health_client, "rollup", _rollup)
    monkeypatch.setattr(gemini_client, "check_gemini", _gemini)

    r = client.get("/", headers=_basic("admin", "secret"))
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "운영 모니터링" in r.text and "18 / 18" in r.text
    assert "DB 뷰어" in r.text and "subscribed_grids" in r.text
    assert "Gemini" in r.text and "모델 47종" in r.text


def test_dashboard_section_error_is_isolated(monkeypatch) -> None:
    """조회 실패 섹션이 페이지 전체를 죽이지 않고 에러 메시지로 격리 표시된다."""
    from app import health_client, repo

    async def _boom():
        raise RuntimeError("relation does not exist")

    async def _rollup():
        return []

    async def _gemini():
        return {"configured": False, "ok": False, "detail": "미설정"}

    from app import gemini_client
    monkeypatch.setattr(repo, "polling_status", _boom)
    monkeypatch.setattr(repo, "forecast_rows", _boom)
    monkeypatch.setattr(repo, "places_stats", _boom)
    monkeypatch.setattr(repo, "list_hub_tables", _boom)
    monkeypatch.setattr(health_client, "rollup", _rollup)
    monkeypatch.setattr(gemini_client, "check_gemini", _gemini)

    r = client.get("/", headers=_basic("admin", "secret"))
    assert r.status_code == 200
    assert "조회 실패" in r.text


def test_gemini_endpoint(monkeypatch) -> None:
    """/api/ops/gemini 가 점검 결과를 반환(네트워크 목킹)."""
    from app import gemini_client

    async def _gemini():
        return {"configured": True, "ok": True, "http_status": 200,
                "latency_ms": 30, "model_count": 40}

    monkeypatch.setattr(gemini_client, "check_gemini", _gemini)
    r = client.get("/api/ops/gemini", headers=_basic("admin", "secret"))
    assert r.status_code == 200
    assert r.json()["ok"] is True and r.json()["model_count"] == 40


def test_db_tables_endpoint(monkeypatch) -> None:
    """/api/db/tables 가 hub_data 테이블 목록을 반환."""
    async def _tables():
        return [{"table": "places", "rows": 2}]

    monkeypatch.setattr(repo, "list_hub_tables", _tables)
    r = client.get("/api/db/tables", headers=_basic("admin", "secret"))
    assert r.status_code == 200
    assert r.json()["schema"] == "hub_data"
    assert r.json()["tables"][0]["table"] == "places"


def test_db_rows_unknown_table_404(monkeypatch) -> None:
    """존재하지 않는 테이블명은 404(화이트리스트 검증)."""
    async def _names():
        return {"places", "subscribed_grids"}

    monkeypatch.setattr(repo, "hub_table_names", _names)
    r = client.get("/api/db/tables/user_accounts",
                   headers=_basic("admin", "secret"))
    assert r.status_code == 404


def test_db_rows_ok(monkeypatch) -> None:
    """검증된 테이블은 행 페이지를 반환."""
    async def _names():
        return {"places"}

    async def _browse(table, limit, offset):
        return {
            "table": table, "columns": ["content_id", "source"],
            "rows": [{"content_id": "durunubi:C001",
                      "source": "durunubi"}],
            "total": 2, "limit": limit, "offset": offset,
        }

    monkeypatch.setattr(repo, "hub_table_names", _names)
    monkeypatch.setattr(repo, "browse_table", _browse)
    r = client.get("/api/db/tables/places?limit=1&offset=0",
                   headers=_basic("admin", "secret"))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["columns"] == ["content_id", "source"]
