"""hub_data 읽기전용 조회 (cut 1 모니터링 소스).

모든 SQL 은 `hub_data.<table>` 로 완전수식하며 SELECT/집계만 수행한다.
컬럼·인덱스는 hub 마이그레이션(001_create_tables, 004_create_places)의
실제 정의를 근거로 한다:
  - subscribed_grids(is_active, ...)         — 폴링 대상 격자
  - short_term_forecast(base_at, expires_at) — 단기예보 raw
  - mid_land_forecast / mid_temp_forecast(tm_fc, expires_at) — 중기예보 raw
  - places(source, ...)                      — 장소 후보(kakao/durunubi)

빈 환경(키 미설정/폴링 전) 대비: 집계 결과가 0/NULL 이어도 정상 반환하며,
화면단에서 "데이터 없음/KMA 키 필요" 로 안내한다.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import get_engine


async def _row(conn, sql: str) -> dict[str, Any]:
    """단일 행 집계 SELECT 를 dict 로 반환(없으면 빈 dict)."""
    result = await conn.execute(text(sql))
    row = result.mappings().first()
    return dict(row) if row is not None else {}


async def _rows(conn, sql: str) -> list[dict[str, Any]]:
    """다중 행 SELECT 를 dict 리스트로 반환."""
    result = await conn.execute(text(sql))
    return [dict(r) for r in result.mappings().all()]


async def polling_status() -> dict[str, Any]:
    """KMA 폴링 현황: 활성/전체 격자 수 + 각 예보 테이블의 최신 발표시각·행수.

    - subscribed_grids: is_active=TRUE 격자가 폴링 대상.
    - short_term_forecast.base_at: 단기예보 마지막 발표분.
    - mid_*_forecast.tm_fc: 중기예보 마지막 발표분.
    """
    async with get_engine().connect() as conn:
        grids = await _row(
            conn,
            "SELECT count(*) FILTER (WHERE is_active) AS active_grids, "
            "count(*) AS total_grids FROM hub_data.subscribed_grids",
        )
        short = await _row(
            conn,
            "SELECT max(base_at) AS last_base_at, count(*) AS rows "
            "FROM hub_data.short_term_forecast",
        )
        mid_land = await _row(
            conn,
            "SELECT max(tm_fc) AS last_tm_fc, count(*) AS rows "
            "FROM hub_data.mid_land_forecast",
        )
        mid_temp = await _row(
            conn,
            "SELECT max(tm_fc) AS last_tm_fc, count(*) AS rows "
            "FROM hub_data.mid_temp_forecast",
        )
    return {
        "grids": grids,
        "short_term": short,
        "mid_land": mid_land,
        "mid_temp": mid_temp,
    }


async def forecast_rows() -> list[dict[str, Any]]:
    """예보 3테이블별 행수 + 만료시각(min/max) 요약.

    housekeeping 이 expires_at <= now() 를 지우므로, min(expires_at) 이
    과거면 곧 정리 대상이 남아있음을 뜻한다.
    """
    async with get_engine().connect() as conn:
        out: list[dict[str, Any]] = []
        for table in (
            "short_term_forecast",
            "mid_land_forecast",
            "mid_temp_forecast",
        ):
            r = await _row(
                conn,
                f"SELECT count(*) AS rows, min(expires_at) AS min_expires_at, "
                f"max(expires_at) AS max_expires_at "
                f"FROM hub_data.{table}",
            )
            out.append({"table": table, **r})
    return out


async def places_stats() -> dict[str, Any]:
    """장소 후보 출처별 집계.

    참고: kakao 결과는 Redis L1 캐시로만 다뤄져 places 에는 durunubi 만
    영속되는 것이 현재 hub 동작이다(빈 환경에서는 durunubi 시드 소량).
    """
    async with get_engine().connect() as conn:
        by_source = await _rows(
            conn,
            "SELECT source, count(*) AS rows FROM hub_data.places "
            "GROUP BY source ORDER BY source",
        )
        total = await _row(
            conn, "SELECT count(*) AS rows FROM hub_data.places"
        )
    return {"total": total.get("rows", 0), "by_source": by_source}


# --- DB 뷰어 (hub_data 한정, 읽기전용) ------------------------------------
# user_service(PII)·langgraph(SDK 전용)는 노출하지 않는다. map_admin 은
# hub_data 에만 SELECT 권한이 있어 권한 계층에서도 이중으로 차단된다.


async def hub_table_names() -> set[str]:
    """hub_data 의 BASE TABLE 이름 집합. 테이블명 화이트리스트 검증에 쓴다."""
    async with get_engine().connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'hub_data' AND table_type = 'BASE TABLE'"
            )
        )
        return set(result.scalars().all())


async def list_hub_tables() -> list[dict[str, Any]]:
    """hub_data 테이블 목록 + 각 행수."""
    async with get_engine().connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='hub_data' AND table_type='BASE TABLE' "
                "ORDER BY table_name"
            )
        )
        names = list(result.scalars().all())
        out: list[dict[str, Any]] = []
        for name in names:
            # name 은 information_schema 에서 온 실제 테이블명. 큰따옴표로
            # 식별자 인용(임의 SQL 주입 불가 — 값이 아닌 카탈로그 유래).
            cnt = await conn.execute(
                text(f'SELECT count(*) AS c FROM hub_data."{name}"')
            )
            out.append({"table": name, "rows": cnt.scalar_one()})
    return out


async def browse_table(
    table: str, limit: int, offset: int
) -> dict[str, Any]:
    """검증된 hub_data 테이블의 행을 페이지네이션 조회.

    `table` 은 반드시 hub_table_names() 로 사전 검증된 값이어야 한다(호출부
    책임). 방어적으로 여기서도 카탈로그와 재대조한 뒤에만 조회한다.
    """
    allowed = await hub_table_names()
    if table not in allowed:
        raise ValueError(f"unknown hub_data table: {table}")
    async with get_engine().connect() as conn:
        result = await conn.execute(
            text(
                f'SELECT * FROM hub_data."{table}" '
                f"ORDER BY 1 LIMIT :lim OFFSET :off"
            ),
            {"lim": limit, "off": offset},
        )
        columns = list(result.keys())
        rows = [
            {c: _cell(v) for c, v in dict(m).items()}
            for m in result.mappings().all()
        ]
        total = (
            await conn.execute(
                text(f'SELECT count(*) AS c FROM hub_data."{table}"')
            )
        ).scalar_one()
    return {
        "table": table,
        "columns": columns,
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _cell(value: Any) -> Any:
    """JSON/HTML 표시용 셀 정규화.

    datetime/Decimal 등은 FastAPI 인코더가 처리하지만, geometry(WKB hex 등)
    긴 값은 표에서 보기 좋게 앞부분만 남긴다.
    """
    if isinstance(value, str) and len(value) > 80:
        return value[:77] + "…"
    return value
