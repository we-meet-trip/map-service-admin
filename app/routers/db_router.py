"""DB 브라우저 라우터 (hub_data 한정, 읽기전용) — 강화판.

목록 + 스키마 + 행(정렬/검색/필터) + CSV 내보내기. 전 라우트 require_operator.
정렬/필터 컬럼은 repo 가 카탈로그와 대조 검증한다(무효 시 422).
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app import repo
from app.config import settings
from app.security import require_operator

router = APIRouter(
    prefix="/api/v1/db",
    tags=["db"],
    dependencies=[Depends(require_operator)],
)


def _clamp_page(limit: int, offset: int) -> tuple[int, int]:
    """페이지 한도/오프셋 보정."""
    limit = max(1, min(limit, settings.DB_PAGE_SIZE_MAX))
    offset = max(0, offset)
    return limit, offset


async def _require_hub_table(table: str) -> None:
    """hub_data 실제 테이블만 허용(화이트리스트). 아니면 404."""
    if table not in await repo.hub_table_names():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"hub_data table not found: {table}",
        )


def _extract_filters(request: Request) -> dict[str, str]:
    """쿼리스트링에서 filter.<col>=value 형태를 추출한다."""
    out: dict[str, str] = {}
    for key, val in request.query_params.items():
        if key.startswith("filter.") and len(key) > 7:
            out[key[7:]] = val
    return out


@router.get("/tables")
async def db_tables() -> dict:
    """hub_data 테이블 목록 + 행수."""
    return {"schema": "hub_data", "tables": await repo.list_hub_tables()}


@router.get("/tables/{table}/schema")
async def db_table_schema(table: str) -> dict:
    """테이블 컬럼 정의 + 인덱스 정의."""
    await _require_hub_table(table)
    return await repo.table_schema(table)


@router.get("/tables/{table}")
async def db_rows(
    table: str,
    request: Request,
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    sort: str | None = Query(None),
    q: str | None = Query(None),
) -> dict:
    """테이블 행 조회(정렬/검색/필터 + 페이지네이션)."""
    await _require_hub_table(table)
    lim, off = _clamp_page(limit, offset)
    filters = _extract_filters(request)
    try:
        return await repo.browse_table(table, lim, off, sort, q, filters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/tables/{table}/export.csv")
async def db_export_csv(
    table: str,
    request: Request,
    sort: str | None = Query(None),
    q: str | None = Query(None),
) -> StreamingResponse:
    """현재 필터/정렬을 반영한 CSV 스트림(상한 DB_EXPORT_MAX_ROWS)."""
    await _require_hub_table(table)
    filters = _extract_filters(request)

    async def _gen():
        header: list[str] | None = None
        buf = io.StringIO()
        writer = csv.writer(buf)
        try:
            async for item in repo.iter_export_rows(
                table, sort, q, filters, settings.DB_EXPORT_MAX_ROWS
            ):
                if header is None:
                    header = item  # 첫 yield 는 컬럼 헤더
                    writer.writerow(header)
                else:
                    writer.writerow([item.get(c) for c in header])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
        except ValueError:
            # 무효 컬럼 등 — 스트림 시작 후이므로 주석 라인만 남긴다.
            yield "# export aborted: invalid sort/filter\n"

    filename = f"{table}.csv"
    return StreamingResponse(
        _gen(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
