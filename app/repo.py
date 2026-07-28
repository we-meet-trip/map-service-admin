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


# --- DB 뷰어 강화: 스키마 조회 · 정렬/필터/검색 · CSV ---------------------
# 모든 컬럼명은 information_schema(카탈로그)에서 온 값을 화이트리스트로 검증한
# 뒤에만 식별자로 인용한다. 값은 항상 바인드 파라미터로 전달한다(주입 차단).


async def _column_meta(conn, table: str) -> list[dict[str, Any]]:
    """table 의 컬럼 메타(이름/타입/udt/nullable)를 ordinal 순으로 반환."""
    rows = (
        await conn.execute(
            text(
                "SELECT column_name AS name, data_type, udt_name, "
                "is_nullable FROM information_schema.columns "
                "WHERE table_schema='hub_data' AND table_name=:t "
                "ORDER BY ordinal_position"
            ),
            {"t": table},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def _select_expr(cols: list[dict[str, Any]]) -> str:
    """SELECT 리스트. geometry 컬럼은 ST_AsText 로 텍스트화(가독)."""
    parts: list[str] = []
    for c in cols:
        name = c["name"]
        if c["udt_name"] == "geometry":
            parts.append(f'ST_AsText("{name}") AS "{name}"')
        else:
            parts.append(f'"{name}"')
    return ", ".join(parts)


def _text_columns(cols: list[dict[str, Any]]) -> list[str]:
    """ILIKE 검색 대상(text/varchar/char) 컬럼명."""
    textish = {"text", "character varying", "character"}
    return [c["name"] for c in cols if c["data_type"] in textish]


def _build_filters(
    colnames: set[str],
    text_cols: list[str],
    q: str | None,
    filters: dict[str, str] | None,
) -> tuple[str, dict[str, Any]]:
    """WHERE 절과 파라미터를 만든다. 검증되지 않은 컬럼은 ValueError."""
    conds: list[str] = []
    params: dict[str, Any] = {}
    if q and text_cols:
        ors = [f'"{c}"::text ILIKE :q' for c in text_cols]
        conds.append("(" + " OR ".join(ors) + ")")
        params["q"] = f"%{q}%"
    for i, (col, val) in enumerate((filters or {}).items()):
        if col not in colnames:
            raise ValueError(f"unknown filter column: {col}")
        conds.append(f'"{col}"::text = :f{i}')
        params[f"f{i}"] = val
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def _build_order(colnames: set[str], sort: str | None) -> str:
    """ORDER BY 절. sort='col:asc|desc'. 미지정/무효면 첫 컬럼 오름차순."""
    if not sort:
        return " ORDER BY 1"
    col, _, direction = sort.partition(":")
    if col not in colnames:
        raise ValueError(f"unknown sort column: {col}")
    dir_sql = "DESC" if direction.lower() == "desc" else "ASC"
    return f' ORDER BY "{col}" {dir_sql}'


async def table_schema(table: str) -> dict[str, Any]:
    """table 의 컬럼 정의 + 인덱스 정의."""
    allowed = await hub_table_names()
    if table not in allowed:
        raise ValueError(f"unknown hub_data table: {table}")
    async with get_engine().connect() as conn:
        cols = await _column_meta(conn, table)
        idx = (
            await conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname='hub_data' AND tablename=:t "
                    "ORDER BY indexname"
                ),
                {"t": table},
            )
        ).mappings().all()
    return {
        "table": table,
        "columns": cols,
        "indexes": [dict(r) for r in idx],
    }


async def browse_table(
    table: str,
    limit: int,
    offset: int,
    sort: str | None = None,
    q: str | None = None,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """검증된 hub_data 테이블을 정렬/검색/필터 + 페이지네이션 조회.

    `table` 은 hub_table_names() 로 검증. 정렬/필터 컬럼은 카탈로그 컬럼과
    대조 검증한다(무효 시 ValueError → 라우터 422).
    """
    allowed = await hub_table_names()
    if table not in allowed:
        raise ValueError(f"unknown hub_data table: {table}")
    async with get_engine().connect() as conn:
        cols = await _column_meta(conn, table)
        colnames = {c["name"] for c in cols}
        where, params = _build_filters(
            colnames, _text_columns(cols), q, filters
        )
        order = _build_order(colnames, sort)
        select = _select_expr(cols)
        params.update({"lim": limit, "off": offset})
        result = await conn.execute(
            text(
                f'SELECT {select} FROM hub_data."{table}"'
                f"{where}{order} LIMIT :lim OFFSET :off"
            ),
            params,
        )
        out_cols = list(result.keys())
        rows = [
            {c: _cell(v) for c, v in dict(m).items()}
            for m in result.mappings().all()
        ]
        total = (
            await conn.execute(
                text(f'SELECT count(*) AS c FROM hub_data."{table}"{where}'),
                {k: v for k, v in params.items() if k not in ("lim", "off")},
            )
        ).scalar_one()
    return {
        "table": table,
        "columns": out_cols,
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort": sort,
        "q": q,
        "filters": filters or {},
    }


async def iter_export_rows(
    table: str,
    sort: str | None,
    q: str | None,
    filters: dict[str, str] | None,
    max_rows: int,
):
    """CSV 내보내기용 행 스트림. (header, then rows). 상한 max_rows.

    yield: 첫 항목은 컬럼 리스트, 이후 각 행 dict. 라우터가 CSV 로 직렬화.
    """
    allowed = await hub_table_names()
    if table not in allowed:
        raise ValueError(f"unknown hub_data table: {table}")
    async with get_engine().connect() as conn:
        cols = await _column_meta(conn, table)
        colnames = {c["name"] for c in cols}
        where, params = _build_filters(
            colnames, _text_columns(cols), q, filters
        )
        order = _build_order(colnames, sort)
        select = _select_expr(cols)
        params["lim"] = max_rows
        result = await conn.stream(
            text(
                f'SELECT {select} FROM hub_data."{table}"'
                f"{where}{order} LIMIT :lim"
            ),
            params,
        )
        yield [c["name"] for c in cols]
        async for m in result.mappings():
            yield dict(m)


def _cell(value: Any) -> Any:
    """JSON 표시용 셀 정규화. 지나치게 긴 문자열은 앞부분만 남긴다."""
    if isinstance(value, str) and len(value) > 200:
        return value[:197] + "…"
    return value
